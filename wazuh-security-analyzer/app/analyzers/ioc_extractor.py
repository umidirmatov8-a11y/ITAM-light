"""Indicator of Compromise extraction (IP, domain, URL, file hashes, CVE)."""

from __future__ import annotations

import re
from typing import Iterable

CVE_RE = re.compile(r"\bCVE-(?:19|20)\d{2}-\d{4,7}\b", re.I)
IPV4_RE = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\w.])")
URL_RE = re.compile(r"\b(?:https?|hxxps?|ftp)://[^\s\"'<>\\)\]]{3,2048}", re.I)
MD5_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")
SHA1_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?![0-9a-fA-F])")
SHA256_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
DOMAIN_RE = re.compile(r"(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,24})(?![\w-])", re.I)

# TLDs accepted for free-text domain extraction.  Ambiguous TLDs that collide with file
# extensions (sh, py, zip, mov, md, rs, ps, pl, so) are excluded to avoid false IOCs.
_TLDS = frozenset("""
com net org info biz io co ru cn uk de fr nl jp br in xyz top online site club shop app dev cloud me tv cc pw su ua
uz kz by eu us ca au es it ch se no fi dk at be cz sk hu ro bg gr tr ir kr tw hk sg my id th vn ph pk bd ng za eg
ar mx cl pe ve tk ml ga cf gq ws link live icu vip work press space tech store fun buzz monster rest bar cyou today
best world life news email website host win bid loan download stream review trade date racing party science gdn
""".split())

_DEFANG = (("[.]", "."), ("(.)", "."), ("{.}", "."), ("hxxp", "http"), ("[:]", ":"))
_ZERO_HASHES = {"0" * 32, "0" * 40, "0" * 64, "d41d8cd98f00b204e9800998ecf8427e",
                "da39a3ee5e6b4b0d3255bfef95601890afd80709",
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}  # empty-file hashes


def refang(text: str) -> str:
    for old, new in _DEFANG:
        if old in text:
            text = text.replace(old, new)
    return text


def extract_cves(*texts: str) -> list[str]:
    found: dict[str, None] = {}
    for text in texts:
        if text and "CVE-" in text.upper():
            for match in CVE_RE.findall(text):
                found[match.upper()] = None
    return list(found)


def domain_from_url(url: str) -> str:
    match = re.match(r"^[a-z]+://(?:[^@/]*@)?([^/:?#]+)", url, re.I)
    return match.group(1).lower() if match else ""


def is_valid_hash(value: str) -> bool:
    return value.lower() not in _ZERO_HASHES and len(set(value.lower())) > 4


def extract_iocs(text: str, exclude_domains: Iterable[str] = ()) -> list[tuple[str, str]]:
    """Extract IOCs from free text. Returns (type, value) pairs, de-duplicated, order preserved."""
    if not text:
        return []
    if "[.]" in text or "hxxp" in text.lower():
        text = refang(text)
    seen: dict[tuple[str, str], None] = {}
    excluded = {d.lower() for d in exclude_domains if d}
    urls = URL_RE.findall(text) if "://" in text else []
    for url in urls[:20]:
        url = url.rstrip(".,;")
        seen[("url", url)] = None
        host = domain_from_url(url)
        if host and not IPV4_RE.fullmatch(host):
            seen[("domain", host)] = None
    for ip in IPV4_RE.findall(text)[:50]:
        seen[("ip", ip)] = None
    if len(text) >= 32:
        for value in SHA256_RE.findall(text)[:10]:
            if is_valid_hash(value):
                seen[("sha256", value.lower())] = None
        for value in SHA1_RE.findall(text)[:10]:
            if is_valid_hash(value):
                seen[("sha1", value.lower())] = None
        for value in MD5_RE.findall(text)[:10]:
            if is_valid_hash(value):
                seen[("md5", value.lower())] = None
    if "." in text:
        for match in DOMAIN_RE.finditer(text):
            tld = match.group(1).lower()
            domain = match.group(0).lower().rstrip(".")
            if tld not in _TLDS or domain in excluded:
                continue
            if any(domain.endswith("." + ex) or domain == ex for ex in excluded):
                continue
            seen[("domain", domain)] = None
            if len(seen) > 100:
                break
    return list(seen)
