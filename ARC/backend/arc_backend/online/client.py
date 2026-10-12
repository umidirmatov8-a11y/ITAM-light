"""The only way A.R.C. code reaches the internet.

Every request re-checks, at the moment it is made, that the user switched A.R.C. to ONLINE
(defence in depth on top of the Permission Manager), honours a per-minute request limit and a
timeout, accepts only https (or a SearXNG instance on this computer), caps the response size and
is recorded in the activity list shown in the interface and in the audit log.
"""
from __future__ import annotations

import collections
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import httpx

from ..ai.ollama import is_loopback_url
from ..storage.journal import Journal
from ..storage.settings import NetworkMode, Settings

log = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = "A.R.C./0.5 (local voice assistant; +https://github.com/umidirmatov8-a11y/ITAM-light)"


class OnlineError(RuntimeError):
    """User-facing reason why an online request was not made or failed."""


@dataclass
class Fetched:
    status_code: int
    url: str
    content: bytes
    content_type: str = ""

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.content)
        except ValueError:
            raise OnlineError("Сервис вернул ответ неверного формата")


@dataclass
class Activity:
    ts: float
    provider: str
    host: str
    status: str  # ok | error | refused
    ms: int
    detail: str = ""


class OnlineClient:
    def __init__(self, settings: Callable[[], Settings], journal: Optional[Journal] = None,
                 transport: Optional[httpx.BaseTransport] = None, clock: Callable[[], float] = time.monotonic):
        self._settings = settings
        self._journal = journal
        self._transport = transport
        self._clock = clock
        self._lock = threading.Lock()
        self._stamps: collections.deque[float] = collections.deque()
        self._recent: collections.deque[Activity] = collections.deque(maxlen=50)
        self._active = 0

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"active": self._active, "recent": [asdict(a) for a in reversed(self._recent)],
                    "used_last_minute": self._used(self._clock())}

    def _used(self, now: float) -> int:
        while self._stamps and now - self._stamps[0] > 60.0:
            self._stamps.popleft()
        return len(self._stamps)

    def _record(self, provider: str, host: str, status: str, started: float, detail: str = "") -> None:
        ms = int((self._clock() - started) * 1000)
        with self._lock:
            self._recent.append(Activity(time.time(), provider, host, status, ms, detail[:200]))
        if self._journal is not None:
            self._journal.audit(action="net.request", params={"provider": provider, "host": host}, risk="A",
                                source="online", decision="refused" if status == "refused" else "allow",
                                status=status, message=detail[:300] or host)

    # ------------------------------------------------------------------ checks
    def check_allowed(self) -> Settings:
        settings = self._settings()
        if not settings.network.online_allowed:
            raise OnlineError("Онлайн-функции полностью отключены в настройках")
        if settings.network.mode != NetworkMode.ONLINE:
            raise OnlineError("A.R.C. в режиме LOCAL и не обращается к интернету. "
                              "Скажите «переключись в онлайн-режим».")
        return settings

    @staticmethod
    def _check_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname:
            return parsed.hostname
        if parsed.scheme == "http" and is_loopback_url(url):
            return parsed.hostname or "localhost"
        raise OnlineError("Разрешены только адреса https://")

    # ------------------------------------------------------------------ request
    def request(self, provider: str, method: str, url: str, *, params: Optional[dict[str, Any]] = None,
                data: Optional[dict[str, Any]] = None, headers: Optional[dict[str, str]] = None) -> Fetched:
        host = urlparse(url).hostname or "?"
        started = self._clock()
        try:
            settings = self.check_allowed()
            host = self._check_url(url)
            with self._lock:
                now = self._clock()
                if self._used(now) >= settings.online.requests_per_minute:
                    raise OnlineError(f"Превышен лимит: {settings.online.requests_per_minute} запросов в минуту. "
                                      "Подождите немного.")
                self._stamps.append(now)
                self._active += 1
        except OnlineError as exc:
            self._record(provider, host, "refused", started, str(exc))
            raise
        try:
            response = self._send(method, url, params, data, headers, settings.online.timeout_s)
        except OnlineError as exc:
            self._record(provider, host, "error", started, str(exc))
            raise
        finally:
            with self._lock:
                self._active -= 1
        self._record(provider, host, "ok", started, f"HTTP {response.status_code}")
        return response

    def _send(self, method: str, url: str, params: Optional[dict[str, Any]], data: Optional[dict[str, Any]],
              headers: Optional[dict[str, str]], timeout_s: float) -> Fetched:
        all_headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.7"}
        all_headers.update(headers or {})
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout_s, connect=min(5.0, timeout_s)), follow_redirects=True,
                              max_redirects=3, transport=self._transport) as client:
                with client.stream(method, url, params=params, data=data, headers=all_headers) as response:
                    self._check_url(str(response.url))  # a redirect must not leave https
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise OnlineError("Ответ сервера слишком большой")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    result = Fetched(response.status_code, str(response.url), body,
                                     response.headers.get("content-type", ""))
        except httpx.TimeoutException:
            raise OnlineError(f"Сервер не ответил за {timeout_s:g} с")
        except httpx.TooManyRedirects:
            raise OnlineError("Слишком много перенаправлений")
        except httpx.HTTPError as exc:
            raise OnlineError(f"Нет связи с сервером ({type(exc).__name__})")
        if result.status_code == 429:
            raise OnlineError("Сервис временно ограничил число запросов (HTTP 429)")
        if result.status_code in (401, 403):
            raise OnlineError(f"Сервис отказал в доступе (HTTP {result.status_code}). Проверьте ключ API.")
        if result.status_code >= 400:
            raise OnlineError(f"Сервис вернул ошибку HTTP {result.status_code}")
        return result
