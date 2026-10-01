"""Raw event dictionary -> :class:`NormalizedAlert`.

Understands native Wazuh alerts (sshd/PAM, Windows eventchannel, Sysmon, syscheck,
vulnerability-detector, VirusTotal integration, web access logs, AWS), flattened exports
and the generic events produced by the CEF / text parsers.  Missing fields never raise.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.analyzers.ioc_extractor import (
    extract_cves,
    extract_iocs,
    domain_from_url,
    is_valid_hash,
    MD5_RE,
    SHA1_RE,
    SHA256_RE,
)
from app.intelligence.mitre import TECHNIQUE_RE
from app.models.alert import NormalizedAlert
from app.parsers.base import unflatten
from app.utils.text import clean
from app.utils.timeutil import parse_timestamp

_EMPTY = {"", "-", "null", "none", "n/a", "(null)", "unknown"}
_FULL_LOG_MAX = 4096


def _get(d: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
        if d is None:
            return None
    return d


def _first(d: dict[str, Any], *paths: tuple[str, ...]) -> str:
    for path in paths:
        value = _get(d, *path)
        if value is None or isinstance(value, (dict, list)):
            continue
        text = clean(value, 512)
        if text and text.lower() not in _EMPTY:
            return text
    return ""


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean(v, 200) for v in value if v not in (None, "")]
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [clean(v, 200) for v in parsed if v]
            except ValueError:
                pass
        return [p.strip().strip("'\"") for p in text.split(",") if p.strip()]
    return [clean(value, 200)]


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if 0.0 <= result <= 10.0 else None
    except (TypeError, ValueError):
        return None


def _parse_win_hashes(value: str) -> dict[str, str]:
    """Sysmon 'Hashes' field: 'SHA1=..,MD5=..,SHA256=..,IMPHASH=..'."""
    result: dict[str, str] = {}
    for part in value.split(","):
        key, _, hv = part.partition("=")
        key = key.strip().lower()
        hv = hv.strip().lower()
        if key in ("md5", "sha1", "sha256") and hv and is_valid_hash(hv):
            result[key] = hv
    return result


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1] if path else ""


class Normalizer:
    def __init__(self, store_raw: bool = True, max_raw_bytes: int = 16 * 1024, internal_domains: list[str] | None = None):
        self.store_raw = store_raw
        self.max_raw_bytes = max_raw_bytes
        self.internal_domains = [d.lower() for d in (internal_domains or [])]

    def normalize(self, raw: dict[str, Any], source_file: str = "", parser: str = "") -> NormalizedAlert:
        if not isinstance(raw, dict):
            raw = {"full_log": clean(raw, _FULL_LOG_MAX)}
        if "rule" not in raw and any("." in str(k) for k in raw):
            raw = unflatten(raw)
        rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
        win = _get(data, "win") or {}
        eventdata = win.get("eventdata") if isinstance(win, dict) and isinstance(win.get("eventdata"), dict) else {}
        system = win.get("system") if isinstance(win, dict) and isinstance(win.get("system"), dict) else {}
        syscheck = raw.get("syscheck") if isinstance(raw.get("syscheck"), dict) else {}
        vuln = data.get("vulnerability") if isinstance(data.get("vulnerability"), dict) else {}
        vt = data.get("virustotal") if isinstance(data.get("virustotal"), dict) else {}

        timestamp = parse_timestamp(raw.get("timestamp") or raw.get("@timestamp") or _get(system, "systemTime")
                                    or raw.get("time"))
        rule_id = clean(rule.get("id"), 64) or clean(raw.get("rule_id"), 64) or "unknown"
        level = _to_int(rule.get("level", raw.get("level")), 0)
        level = max(0, min(level, 15))
        description = clean(rule.get("description") or raw.get("description") or raw.get("message") or "", 512)
        groups = tuple(_as_list(rule.get("groups")))
        mitre = rule.get("mitre") if isinstance(rule.get("mitre"), dict) else {}
        mitre_ids = tuple(t.upper() for t in _as_list(mitre.get("id")) if TECHNIQUE_RE.match(t.upper()))

        full_log = clean(raw.get("full_log") or raw.get("message") or "", _FULL_LOG_MAX)
        if not description:
            description = full_log[:160] or "Event without description"

        src_ip = _first(data, ("srcip",), ("src_ip",), ("source_ip",), ("aws", "sourceIPAddress"),
                        ("client_ip",), ("remote_ip",))
        if not src_ip:
            src_ip = _first(eventdata, ("ipAddress",), ("sourceIp",), ("sourceAddress",), ("clientAddress",))
        if src_ip.startswith("::ffff:"):
            src_ip = src_ip[7:]
        dst_ip = _first(data, ("dstip",), ("dst_ip",), ("destination_ip",)) or \
            _first(eventdata, ("destinationIp",), ("destAddress",))
        src_port = _first(data, ("srcport",), ("src_port",)) or _first(eventdata, ("sourcePort", "ipPort"))
        dst_port = _first(data, ("dstport",), ("dst_port",)) or _first(eventdata, ("destinationPort",))

        user = _first(data, ("dstuser",), ("user",), ("username",), ("audit", "acct"), ("aws", "userIdentity", "userName")) \
            or _first(eventdata, ("targetUserName",), ("user",)) or _first(syscheck, ("uname_after",))
        src_user = _first(data, ("srcuser",)) or _first(eventdata, ("subjectUserName",))
        if user.endswith("$") and src_user and not src_user.endswith("$"):
            user, src_user = src_user, user
        if "\\" in user and len(user) < 128:
            user = user.split("\\", 1)[1] or user

        process = _first(eventdata, ("image",), ("newProcessName",), ("processName",)) or \
            _first(data, ("process",), ("program_name",), ("audit", "exe")) or clean(raw.get("program_name"), 256)
        command_line = clean(eventdata.get("commandLine") or eventdata.get("scriptBlockText") or
                             data.get("command") or _get(data, "audit", "execve", "a0") or "", 4096)
        parent = _first(eventdata, ("parentImage",), ("parentProcessName",))

        file_path = _first(syscheck, ("path",)) or _first(eventdata, ("targetFilename",)) or \
            _first(vt, ("source", "file")) or _first(data, ("file",), ("filename",))

        hashes: dict[str, str] = {}
        for algo in ("md5", "sha1", "sha256"):
            hv = _first(syscheck, (f"{algo}_after",)) or _first(vt, ("source", algo)) or _first(data, (algo,))
            if hv and is_valid_hash(hv):
                hashes[algo] = hv.lower()
        if eventdata.get("hashes"):
            hashes.update(_parse_win_hashes(str(eventdata["hashes"])))
        file_hash = _first(data, ("file_hash",))
        if file_hash:
            if SHA256_RE.fullmatch(file_hash):
                hashes.setdefault("sha256", file_hash.lower())
            elif SHA1_RE.fullmatch(file_hash):
                hashes.setdefault("sha1", file_hash.lower())
            elif MD5_RE.fullmatch(file_hash):
                hashes.setdefault("md5", file_hash.lower())

        urls: list[str] = []
        url = _first(data, ("url",), ("http", "url"))
        if url:
            urls.append(url)
        domains: list[str] = []
        query = _first(eventdata, ("queryName",)) or _first(data, ("dns", "question", "name"))
        if query:
            domains.append(query.lower())

        # Vulnerability detector (Wazuh 4.x and 4.8+ layouts)
        cvss = None
        vuln_sev = ""
        package = ""
        cves: list[str] = []
        if vuln:
            cve = _first(vuln, ("cve",), ("id",))
            if cve:
                cves.append(cve.upper())
            cvss = _to_float(_get(vuln, "cvss", "cvss3", "base_score")) or _to_float(_get(vuln, "score", "base")) \
                or _to_float(_get(vuln, "cvss", "cvss2", "base_score"))
            vuln_sev = _first(vuln, ("severity",)).lower()
            name = _first(vuln, ("package", "name"))
            version = _first(vuln, ("package", "version"))
            package = f"{name} {version}".strip()
        for cve in extract_cves(description, full_log[:2048]):
            if cve not in cves:
                cves.append(cve)

        vt_positives = vt_total = None
        if vt:
            vt_positives = _to_int(vt.get("positives"), 0) if vt.get("positives") is not None else None
            vt_total = _to_int(vt.get("total"), 0) if vt.get("total") is not None else None
            if vt.get("permalink"):
                urls.append(clean(vt["permalink"], 512))

        # IOC extraction from structured fields and free text
        iocs: dict[tuple[str, str], None] = {}
        for ip in (src_ip, dst_ip):
            if ip:
                iocs[("ip", ip)] = None
        for algo, hv in hashes.items():
            iocs[(algo, hv)] = None
        for u in urls[:1]:
            iocs[("url", u)] = None
            host = domain_from_url(u)
            if host:
                iocs[("domain", host)] = None
        for dom in domains:
            iocs[("domain", dom)] = None
        agent_name = _first(agent, ("name",)) or clean(raw.get("hostname") or raw.get("host") or "", 256)
        exclude = [agent_name.lower()] + self.internal_domains if agent_name else self.internal_domains
        free_text = f"{command_line} {full_log}" if command_line else full_log
        for item in extract_iocs(free_text[:_FULL_LOG_MAX], exclude):
            if item[0] == "url" and "virustotal.com" in item[1]:
                continue
            iocs[item] = None

        win_event_id = _first(system, ("eventID",))
        uid_source = clean(raw.get("id"), 128)
        if uid_source:
            uid = f"{uid_source}:{rule_id}:{agent_name}"
        else:
            digest = hashlib.blake2b(f"{timestamp}|{rule_id}|{agent_name}|{full_log[:512]}|{src_ip}|{user}".encode(
                "utf-8", "replace"), digest_size=12).hexdigest()
            uid = digest

        raw_copy = None
        if self.store_raw:
            raw_copy = raw
            if win_event_id:
                raw_copy = dict(raw)
                raw_copy["_win_event_id"] = win_event_id
        elif win_event_id:
            raw_copy = {"_win_event_id": win_event_id}

        vendor = clean(raw.get("_vendor"), 64) or ("wazuh" if rule and not rule_id.startswith(("generic:", "cef:"))
                                                    else "generic")
        return NormalizedAlert(
            uid=uid,
            timestamp=timestamp,
            rule_id=rule_id,
            rule_level=level,
            rule_description=description,
            rule_groups=groups,
            rule_mitre_ids=mitre_ids,
            agent_id=_first(agent, ("id",)),
            agent_name=agent_name,
            agent_ip=_first(agent, ("ip",)),
            manager=_first(raw, ("manager", "name")),
            src_ip=src_ip,
            src_port=src_port,
            dst_ip=dst_ip,
            dst_port=dst_port,
            src_user=src_user,
            user=user,
            process=process,
            command_line=command_line,
            parent_process=parent,
            file_path=file_path,
            hashes=hashes,
            urls=tuple(urls[:5]),
            domains=tuple(domains[:5]),
            cves=tuple(cves[:20]),
            cvss=cvss,
            vuln_severity=vuln_sev,
            package=package,
            vt_positives=vt_positives,
            vt_total=vt_total,
            location=clean(raw.get("location"), 256),
            decoder=_first(raw, ("decoder", "name")),
            full_log=full_log,
            iocs=tuple(iocs),
            source_file=source_file,
            vendor=vendor,
            parser=parser,
            raw=raw_copy,
        )


def process_basename(path: str) -> str:
    return _basename(path)
