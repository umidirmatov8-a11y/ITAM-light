"""Local IOC list (offline threat intelligence).

CSV columns: ``type,value,verdict,source,description``.  The bundled list contains only
demo indicators from documentation ranges; organisations add their own indicators to
``local_ioc.csv`` in the user data directory.
"""

from __future__ import annotations

import csv
import ipaddress
import logging
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

_VALID_TYPES = {"ip", "cidr", "domain", "url", "md5", "sha1", "sha256"}
_VALID_VERDICTS = {"malicious", "suspicious", "clean"}


class LocalIOCDatabase:
    def __init__(self, files: list[Path] | None = None):
        self.entries: dict[tuple[str, str], dict[str, str]] = {}
        self.networks: list[tuple[object, dict[str, str]]] = []
        sources = files if files is not None else [paths.resources_dir() / "ioc" / "local_ioc.csv",
                                                     paths.user_ioc_path()]
        for path in sources:
            self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(line for line in fh if not line.lstrip().startswith("#")):
                    ioc_type = (row.get("type") or "").strip().lower()
                    value = (row.get("value") or "").strip()
                    verdict = (row.get("verdict") or "suspicious").strip().lower()
                    if ioc_type not in _VALID_TYPES or not value or verdict not in _VALID_VERDICTS:
                        continue
                    info = {"verdict": verdict, "source": (row.get("source") or "local list").strip(),
                            "description": (row.get("description") or "").strip()}
                    if ioc_type == "cidr":
                        try:
                            self.networks.append((ipaddress.ip_network(value, strict=False), info))
                        except ValueError:
                            continue
                    else:
                        key_value = value if ioc_type == "url" else value.lower()
                        self.entries[(ioc_type, key_value)] = info
        except OSError as exc:
            log.error("Cannot read local IOC list %s: %s", path, exc)

    def lookup(self, ioc_type: str, value: str) -> dict[str, str] | None:
        key_value = value if ioc_type == "url" else value.lower()
        hit = self.entries.get((ioc_type, key_value))
        if hit:
            return hit
        if ioc_type == "domain":
            parts = key_value.split(".")
            for i in range(1, len(parts) - 1):
                hit = self.entries.get(("domain", ".".join(parts[i:])))
                if hit:
                    return hit
        if ioc_type == "ip" and self.networks:
            try:
                ip = ipaddress.ip_address(value)
            except ValueError:
                return None
            for net, info in self.networks:
                if ip.version == net.version and ip in net:
                    return info
        return None

    def __len__(self) -> int:
        return len(self.entries) + len(self.networks)
