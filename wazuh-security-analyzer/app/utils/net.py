"""IP address classification (internal vs. external) with configurable internal ranges."""

from __future__ import annotations

import ipaddress
from functools import lru_cache

# RFC1918, loopback, link-local, CGNAT, unique-local IPv6, unspecified.
# Documentation ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) are deliberately
# treated as *external* so that demo data can emulate Internet sources.
_DEFAULT_INTERNAL = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "100.64.0.0/10",
    "0.0.0.0/8",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
    "::/128",
]


class NetworkClassifier:
    def __init__(self, internal_networks: list[str] | None = None, known_scanners: list[str] | None = None):
        nets = list(_DEFAULT_INTERNAL) + list(internal_networks or [])
        self._internal = [ipaddress.ip_network(n, strict=False) for n in nets]
        self._scanners = [ipaddress.ip_network(n, strict=False) for n in (known_scanners or [])]
        self._cache: dict[str, bool | None] = {}

    @staticmethod
    @lru_cache(maxsize=200_000)
    def parse(value: str):
        try:
            return ipaddress.ip_address(value.strip().strip("[]"))
        except ValueError:
            return None

    def is_valid(self, value: str) -> bool:
        return bool(value) and self.parse(value) is not None

    def is_internal(self, value: str) -> bool | None:
        """True for internal, False for external, None when not an IP address."""
        if not value:
            return None
        cached = self._cache.get(value)
        if cached is not None or value in self._cache:
            return cached
        ip = self.parse(value)
        if ip is None:
            result = None
        else:
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            result = any(ip in net for net in self._internal if net.version == ip.version)
            if ip.is_multicast or ip.is_reserved:
                result = True
        if len(self._cache) < 500_000:
            self._cache[value] = result
        return result

    def is_external(self, value: str) -> bool:
        return self.is_internal(value) is False

    def is_known_scanner(self, value: str) -> bool:
        ip = self.parse(value) if value else None
        if ip is None:
            return False
        return any(ip in net for net in self._scanners if net.version == ip.version)
