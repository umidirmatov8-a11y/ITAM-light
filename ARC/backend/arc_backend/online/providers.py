"""Search providers. Each turns a query into a list of SearchResult using OnlineClient only.

Page contents are never executed or rendered: titles and snippets are reduced to plain text and
URLs are kept only if they are http(s).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Optional, Protocol
from urllib.parse import parse_qs, urlparse

from ..storage.settings import Settings
from .client import OnlineClient, OnlineError

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def plain(text: str, limit: int) -> str:
    text = html.unescape(_TAGS.sub("", text or ""))
    text = _SPACES.sub(" ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def safe_url(url: str) -> Optional[str]:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc and len(url) <= 2048 and not re.search(r"[\s\"'<>`]", url):
        return url
    return None


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    provider: str

    def as_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "snippet": self.snippet, "provider": self.provider}


def make_result(title: str, url: str, snippet: str, provider: str) -> Optional[SearchResult]:
    clean = safe_url(url)
    title = plain(title, 200)
    if not clean or not title:
        return None
    return SearchResult(title, clean, plain(snippet, 700), provider)


class Provider(Protocol):
    id: str
    title: str
    needs_key: bool

    def search(self, client: OnlineClient, query: str, settings: Settings, limit: int) -> list[SearchResult]: ...


class WikipediaProvider:
    id = "wikipedia"
    title = "Википедия"
    needs_key = False

    def search(self, client: OnlineClient, query: str, settings: Settings, limit: int) -> list[SearchResult]:
        lang = settings.online.language
        response = client.request(self.id, "GET", f"https://{lang}.wikipedia.org/w/api.php", params={
            "action": "query", "format": "json", "formatversion": "2", "utf8": "1",
            "generator": "search", "gsrsearch": query, "gsrlimit": str(limit), "gsrnamespace": "0",
            "prop": "extracts|info", "inprop": "url", "exintro": "1", "explaintext": "1", "exchars": "700",
            "exlimit": str(limit)})
        data = response.json()
        pages = ((data.get("query") or {}).get("pages") or []) if isinstance(data, dict) else []
        pages = sorted((p for p in pages if isinstance(p, dict)), key=lambda p: p.get("index", 99))
        results = []
        for page in pages:
            item = make_result(str(page.get("title", "")), str(page.get("fullurl", "")),
                               str(page.get("extract", "")), self.id)
            if item:
                results.append(item)
        return results[:limit]


class _DuckParser(HTMLParser):
    """Extracts results from html.duckduckgo.com (result__a links and result__snippet blocks)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._field: Optional[str] = None
        self._depth = 0
        self._ad = False
        self.blocked = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        a = {k: v or "" for k, v in attrs}
        classes = a.get("class", "").split()
        if "result--ad" in classes:
            self._ad = True
        if "result" in classes and "result--ad" not in classes and tag == "div":
            self._ad = False
        if "anomaly-modal__modal" in classes or a.get("id") == "challenge-form":
            self.blocked = True
        if self._field:
            self._depth += 1
            return
        if tag == "a" and "result__a" in classes and not self._ad:
            self.items.append({"title": "", "href": a.get("href", ""), "snippet": ""})
            self._field, self._depth = "title", 0
        elif "result__snippet" in classes and self.items and not self._ad:
            self._field, self._depth = "snippet", 0

    def handle_endtag(self, tag: str) -> None:
        if self._field:
            if self._depth == 0:
                self._field = None
            else:
                self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._field and self.items:
            self.items[-1][self._field] += data


def duck_target(href: str) -> str:
    """DuckDuckGo wraps links as //duckduckgo.com/l/?uddg=<encoded target>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return target
    return href


class DuckDuckGoProvider:
    id = "duckduckgo"
    title = "DuckDuckGo"
    needs_key = False

    def search(self, client: OnlineClient, query: str, settings: Settings, limit: int) -> list[SearchResult]:
        region = "ru-ru" if settings.online.language == "ru" else "us-en"
        response = client.request(self.id, "POST", "https://html.duckduckgo.com/html/",
                                  data={"q": query, "kl": region})
        parser = _DuckParser()
        parser.feed(response.text)
        if parser.blocked and not parser.items:
            raise OnlineError("DuckDuckGo попросил подтвердить, что запрос от человека; попробуйте позже")
        results = []
        for item in parser.items:
            result = make_result(item["title"], duck_target(item["href"]), item["snippet"], self.id)
            if result:
                results.append(result)
            if len(results) >= limit:
                break
        return results


class BraveProvider:
    id = "brave"
    title = "Brave Search API"
    needs_key = True

    def __init__(self, key: Callable[[], Optional[str]]):
        self._key = key

    def search(self, client: OnlineClient, query: str, settings: Settings, limit: int) -> list[SearchResult]:
        key = self._key()
        if not key:
            raise OnlineError("для Brave Search нужен ключ API (Настройки → Интернет)")
        response = client.request(self.id, "GET", "https://api.search.brave.com/res/v1/web/search",
                                  params={"q": query, "count": str(limit), "search_lang": settings.online.language},
                                  headers={"Accept": "application/json", "X-Subscription-Token": key})
        data = response.json()
        items = ((data.get("web") or {}).get("results") or []) if isinstance(data, dict) else []
        results = []
        for item in items:
            if isinstance(item, dict):
                result = make_result(str(item.get("title", "")), str(item.get("url", "")),
                                     str(item.get("description", "")), self.id)
                if result:
                    results.append(result)
        return results[:limit]


class SearxngProvider:
    id = "searxng"
    title = "SearXNG (свой сервер)"
    needs_key = False

    def search(self, client: OnlineClient, query: str, settings: Settings, limit: int) -> list[SearchResult]:
        base = settings.online.searxng_url
        if not base:
            raise OnlineError("не указан адрес сервера SearXNG")
        response = client.request(self.id, "GET", f"{base}/search",
                                  params={"q": query, "format": "json", "language": settings.online.language})
        data = response.json()
        items = (data.get("results") or []) if isinstance(data, dict) else []
        results = []
        for item in items:
            if isinstance(item, dict):
                result = make_result(str(item.get("title", "")), str(item.get("url", "")),
                                     str(item.get("content", "")), self.id)
                if result:
                    results.append(result)
        return results[:limit]
