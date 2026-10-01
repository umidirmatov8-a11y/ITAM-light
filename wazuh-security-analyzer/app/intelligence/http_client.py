"""Hardened asynchronous HTTP client for external APIs.

* TLS verification always on (optionally with a corporate CA bundle) - it cannot be
  disabled from the GUI; ``verify_tls: false`` in config is honoured only with a warning.
* Explicit connect/read timeouts, optional proxy.
* Response bodies are streamed and capped (``max_response_mb``) before JSON decoding.
* No redirects to other hosts are followed.
"""

from __future__ import annotations

import json
import logging
import ssl
from typing import Any

import httpx

from app import __version__
from app.core.config import NetworkConfig
from app.core.errors import ProviderResponseError, ProviderUnavailableError

log = logging.getLogger(__name__)

USER_AGENT = f"WazuhSecurityAnalyzer/{__version__}"


def build_verify(network: NetworkConfig) -> bool | ssl.SSLContext:
    if not network.verify_tls:
        log.warning("TLS certificate verification is DISABLED by configuration - this is insecure")
        return False
    if network.ca_bundle:
        return ssl.create_default_context(cafile=network.ca_bundle)
    return True


class HttpClient:
    def __init__(self, network: NetworkConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.network = network
        self.max_bytes = network.max_response_mb * 1024 * 1024
        timeout = httpx.Timeout(network.timeout_seconds, connect=min(10.0, network.timeout_seconds))
        kwargs: dict[str, Any] = {
            "timeout": timeout,
            "headers": {"User-Agent": USER_AGENT, "Accept": "application/json"},
            "follow_redirects": False,
        }
        if transport is not None:
            kwargs["transport"] = transport
        else:
            kwargs["verify"] = build_verify(network)
            if network.proxy:
                kwargs["proxy"] = network.proxy
        self._client = httpx.AsyncClient(**kwargs)

    async def __aenter__(self) -> "HttpClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(self, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None,
                       max_bytes: int | None = None, allow_404: bool = True) -> tuple[int, Any]:
        limit = max_bytes or self.max_bytes
        try:
            async with self._client.stream("GET", url, headers=headers, params=params) as resp:
                status = resp.status_code
                if status == 404 and allow_404:
                    return status, None
                if status in (401, 403):
                    raise ProviderResponseError(f"{_host(url)}: authentication failed (HTTP {status}) - check the API key")
                if status == 429:
                    raise ProviderUnavailableError(f"{_host(url)}: rate limit exceeded (HTTP 429)")
                if status >= 400:
                    raise ProviderUnavailableError(f"{_host(url)}: HTTP {status}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise ProviderResponseError(f"{_host(url)}: response larger than {limit // (1024 * 1024)} MB")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"{_host(url)}: request timed out") from exc
        except (httpx.ConnectError, httpx.NetworkError, httpx.ProxyError) as exc:
            raise ProviderUnavailableError(f"{_host(url)}: network unavailable ({type(exc).__name__})") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"{_host(url)}: {type(exc).__name__}") from exc
        try:
            return status, json.loads(b"".join(chunks).decode("utf-8", "replace") or "null")
        except ValueError as exc:
            raise ProviderResponseError(f"{_host(url)}: invalid JSON response") from exc


def _host(url: str) -> str:
    return httpx.URL(url).host or url
