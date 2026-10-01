"""AIProvider interface and shared HTTP handling."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import AIConfig, NetworkConfig
from app.core.errors import ProviderResponseError, ProviderUnavailableError
from app.intelligence.http_client import USER_AGENT, build_verify

log = logging.getLogger(__name__)


class AIProvider(ABC):
    name: str = "provider"
    #: True when data leaves the organisation (cloud API). External providers always get sanitized data.
    is_external: bool = True

    def __init__(self, ai: AIConfig, network: NetworkConfig, api_key: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.ai = ai
        self.network = network
        self.api_key = api_key
        self.transport = transport

    @property
    @abstractmethod
    def model(self) -> str:
        """Model identifier used for requests."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Send one system+user prompt and return the raw text answer."""

    def test_connection(self) -> str:
        """Return a short status string or raise ProviderUnavailableError / ProviderResponseError."""
        return "ok"

    def list_models(self) -> list[str]:
        return []

    # -------------------------------------------------------------- HTTP helpers
    def _client(self, local: bool = False) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(self.ai.timeout_seconds, connect=min(10.0, self.ai.timeout_seconds)),
            "headers": {"User-Agent": USER_AGENT},
            "follow_redirects": False,
        }
        if self.transport is not None:
            kwargs["transport"] = self.transport
        else:
            kwargs["verify"] = build_verify(self.network)
            if local:
                kwargs["trust_env"] = False  # never route local LLM traffic through a proxy
            elif self.network.proxy:
                kwargs["proxy"] = self.network.proxy
        return httpx.Client(**kwargs)

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None,
                   local: bool = False) -> Any:
        return self._request("POST", url, payload, headers, local)

    def _get_json(self, url: str, headers: dict[str, str] | None = None, local: bool = False) -> Any:
        return self._request("GET", url, None, headers, local)

    def _request(self, method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str] | None,
                 local: bool) -> Any:
        try:
            with self._client(local) as client:
                response = client.request(method, url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"{self.name}: request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"{self.name}: cannot connect ({type(exc).__name__})") from exc
        if response.status_code in (401, 403):
            raise ProviderResponseError(f"{self.name}: authentication failed (HTTP {response.status_code})")
        if response.status_code == 404:
            raise ProviderResponseError(f"{self.name}: endpoint or model not found (HTTP 404)")
        if response.status_code == 429:
            raise ProviderUnavailableError(f"{self.name}: rate limited (HTTP 429)")
        if response.status_code >= 400:
            detail = response.text[:200].replace("\n", " ")
            raise ProviderUnavailableError(f"{self.name}: HTTP {response.status_code} {detail}")
        if len(response.content) > 10 * 1024 * 1024:
            raise ProviderResponseError(f"{self.name}: response too large")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderResponseError(f"{self.name}: invalid JSON from API") from exc
