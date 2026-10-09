"""Network diagnostics with hard timeouts and real results: DNS (A/SRV), TCP ports, ICMP ping, LDAP/LDAPS/StartTLS.

Nothing here claims more than was measured: e.g. a failed ping only means ICMP echo was not answered (it is often
blocked by Windows Firewall), so TCP port checks are shown next to it.
"""
from __future__ import annotations

import concurrent.futures
import re
import socket
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass, field

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import UnsupportedFeatureError, ValidationError
from ..security.masking import mask_text

_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,252}[A-Za-z0-9])?$|^[0-9a-fA-F:]+$")

COMMON_COMPUTER_PORTS = [(135, "RPC"), (445, "SMB"), (3389, "RDP"), (5985, "WinRM HTTP"), (5986, "WinRM HTTPS")]
DC_PORTS = [(53, "DNS"), (88, "Kerberos"), (389, "LDAP"), (636, "LDAPS"), (3268, "Global Catalog"), (3269, "GC SSL"),
            (445, "SMB"), (135, "RPC")]


@dataclass
class ProbeResult:
    target: str
    check: str
    ok: bool | None            # None = not determinable / not available
    message: str
    duration_ms: int = 0
    details: dict = field(default_factory=dict)

    @property
    def status_text(self) -> str:
        return {True: "OK", False: "Ошибка", None: "Н/Д"}[self.ok]


def validate_host(host: str) -> str:
    host = (host or "").strip().rstrip(".")
    if not host or not _HOST_RE.match(host):
        raise ValidationError(f"Некорректное имя или адрес узла: {host!r}")
    return host


def _with_timeout(fn, timeout: float):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        return fut.result(timeout=timeout)


def resolve(host: str, timeout: float = 3.0) -> ProbeResult:
    host = validate_host(host)
    t = time.monotonic()
    try:
        infos = _with_timeout(lambda: socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP), timeout)
        addrs = sorted({i[4][0] for i in infos})
        return ProbeResult(host, "DNS (A/AAAA)", True, ", ".join(addrs), int((time.monotonic() - t) * 1000),
                           {"addresses": addrs})
    except concurrent.futures.TimeoutError:
        return ProbeResult(host, "DNS (A/AAAA)", False, f"Тайм-аут разрешения имени ({timeout:.0f} с)",
                           int((time.monotonic() - t) * 1000))
    except socket.gaierror as exc:
        return ProbeResult(host, "DNS (A/AAAA)", False, f"Имя не разрешено: {exc.strerror or exc}",
                           int((time.monotonic() - t) * 1000))


def reverse_lookup(ip: str, timeout: float = 3.0) -> ProbeResult:
    ip = validate_host(ip)
    t = time.monotonic()
    try:
        name = _with_timeout(lambda: socket.gethostbyaddr(ip)[0], timeout)
        return ProbeResult(ip, "DNS (PTR)", True, name, int((time.monotonic() - t) * 1000))
    except concurrent.futures.TimeoutError:
        return ProbeResult(ip, "DNS (PTR)", False, "Тайм-аут", int((time.monotonic() - t) * 1000))
    except (socket.herror, socket.gaierror) as exc:
        return ProbeResult(ip, "DNS (PTR)", False, f"Нет PTR-записи: {exc}", int((time.monotonic() - t) * 1000))


def tcp_check(host: str, port: int, timeout: float = 3.0, label: str = "") -> ProbeResult:
    host = validate_host(host)
    t = time.monotonic()
    name = f"TCP {port}" + (f" ({label})" if label else "")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return ProbeResult(host, name, True, "Порт открыт", int((time.monotonic() - t) * 1000))
    except socket.timeout:
        return ProbeResult(host, name, False, f"Нет ответа за {timeout:.0f} с (фильтруется или узел недоступен)",
                           int((time.monotonic() - t) * 1000))
    except ConnectionRefusedError:
        return ProbeResult(host, name, False, "Соединение отклонено (порт закрыт)", int((time.monotonic() - t) * 1000))
    except OSError as exc:
        return ProbeResult(host, name, False, mask_text(str(exc)), int((time.monotonic() - t) * 1000))


def ping(host: str, timeout: float = 3.0) -> ProbeResult:
    host = validate_host(host)
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host]
        flags = 0
    t = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 3, creationflags=flags, shell=False)
    except FileNotFoundError:
        return ProbeResult(host, "ICMP ping", None, "Утилита ping недоступна в системе")
    except subprocess.TimeoutExpired:
        return ProbeResult(host, "ICMP ping", False, "Тайм-аут", int((time.monotonic() - t) * 1000))
    except PermissionError:
        return ProbeResult(host, "ICMP ping", None, "Нет прав на выполнение ping")
    out = proc.stdout.decode("cp866" if sys.platform == "win32" else "utf-8", "replace")
    ok = proc.returncode == 0 and ("TTL=" in out.upper())
    if sys.platform != "win32":
        ok = proc.returncode == 0
    msg = "Ответ получен" if ok else "Нет ответа на ICMP (может блокироваться брандмауэром)"
    return ProbeResult(host, "ICMP ping", ok, msg, int((time.monotonic() - t) * 1000))


def srv_lookup(name: str, timeout: float = 3.0) -> ProbeResult:
    try:
        import dns.resolver  # dnspython
    except ImportError:
        raise UnsupportedFeatureError("Для SRV-запросов требуется пакет dnspython") from None
    t = time.monotonic()
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout
    try:
        answer = resolver.resolve(name, "SRV")
        records = sorted(((r.priority, r.weight, r.port, str(r.target).rstrip(".")) for r in answer))
        text = "; ".join(f"{tgt}:{port} (prio {p}, weight {w})" for p, w, port, tgt in records)
        return ProbeResult(name, "DNS SRV", True, text, int((time.monotonic() - t) * 1000), {"records": records})
    except dns.resolver.NXDOMAIN:
        return ProbeResult(name, "DNS SRV", False, "Запись не существует (NXDOMAIN)", int((time.monotonic() - t) * 1000))
    except dns.resolver.NoAnswer:
        return ProbeResult(name, "DNS SRV", False, "Нет SRV-записей", int((time.monotonic() - t) * 1000))
    except dns.exception.Timeout:
        return ProbeResult(name, "DNS SRV", False, f"Тайм-аут DNS ({timeout:.0f} с)", int((time.monotonic() - t) * 1000))
    except Exception as exc:  # noqa: BLE001 - dnspython raises a variety of errors (no nameservers, etc.)
        return ProbeResult(name, "DNS SRV", False, mask_text(str(exc)), int((time.monotonic() - t) * 1000))


def domain_dns_checks(domain: str, timeout: float = 3.0, cancel: CancelToken | None = None,
                      progress: Progress = NULL_PROGRESS) -> list[ProbeResult]:
    domain = validate_host(domain)
    names = [f"_ldap._tcp.{domain}", f"_ldap._tcp.dc._msdcs.{domain}", f"_kerberos._tcp.{domain}",
             f"_kpasswd._tcp.{domain}", f"_gc._tcp.{domain}", f"_ldap._tcp.pdc._msdcs.{domain}"]
    out = []
    for i, n in enumerate(names):
        if cancel:
            cancel.raise_if_cancelled()
        progress(int(i * 100 / (len(names) + 1)), f"SRV {n}")
        try:
            out.append(srv_lookup(n, timeout))
        except UnsupportedFeatureError as exc:
            out.append(ProbeResult(n, "DNS SRV", None, exc.message))
    out.append(resolve(domain, timeout))
    progress(100, "DNS-проверки завершены")
    return out


def tls_probe(host: str, port: int = 636, timeout: float = 5.0, ca_file: str | None = None,
              server_name: str | None = None, starttls: bool = False) -> ProbeResult:
    """TLS handshake with full certificate validation (CERT_REQUIRED + host name check)."""
    host = validate_host(host)
    name = "StartTLS (389)" if starttls else f"LDAPS ({port})"
    t = time.monotonic()
    ctx = ssl.create_default_context(cafile=ca_file or None)
    try:
        if starttls:
            import ldap3
            tls = ldap3.Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT, ca_certs_file=ca_file or None,
                            valid_names=[server_name] if server_name else None)
            server = ldap3.Server(host, port=port, use_ssl=False, tls=tls, get_info=ldap3.NONE, connect_timeout=int(timeout))
            conn = ldap3.Connection(server, receive_timeout=int(timeout), raise_exceptions=False)
            conn.open()
            ok = conn.start_tls()
            cert = conn.socket.getpeercert() if ok else None
            conn.unbind()
            if not ok:
                return ProbeResult(host, name, False, f"StartTLS не установлен: {conn.result}", int((time.monotonic() - t) * 1000))
        else:
            with socket.create_connection((host, port), timeout=timeout) as raw:
                with ctx.wrap_socket(raw, server_hostname=server_name or host) as tls_sock:
                    cert = tls_sock.getpeercert()
        subject = ", ".join("=".join(x) for rdn in cert.get("subject", ()) for x in rdn)
        issuer = ", ".join("=".join(x) for rdn in cert.get("issuer", ()) for x in rdn)
        not_after = cert.get("notAfter", "")
        days_left = None
        try:
            days_left = int((ssl.cert_time_to_seconds(not_after) - time.time()) // 86400)
        except (ValueError, TypeError):
            pass
        msg = f"Сертификат действителен: {subject}; издатель: {issuer}; до {not_after}"
        if days_left is not None and days_left < 30:
            msg += f" — истекает через {days_left} дн.!"
        return ProbeResult(host, name, True, msg, int((time.monotonic() - t) * 1000),
                           {"subject": subject, "issuer": issuer, "not_after": not_after, "days_left": days_left})
    except ssl.SSLCertVerificationError as exc:
        return ProbeResult(host, name, False, f"Сертификат НЕ прошёл проверку: {exc.verify_message or exc}",
                           int((time.monotonic() - t) * 1000))
    except (socket.timeout, TimeoutError):
        return ProbeResult(host, name, False, "Тайм-аут TLS-подключения", int((time.monotonic() - t) * 1000))
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(host, name, False, mask_text(f"{type(exc).__name__}: {exc}"), int((time.monotonic() - t) * 1000))


def ldap_rootdse_probe(host: str, port: int = 389, timeout: float = 5.0) -> ProbeResult:
    """Anonymous RootDSE read (permitted by AD without authentication; no credentials are sent)."""
    host = validate_host(host)
    t = time.monotonic()
    try:
        import ldap3
        server = ldap3.Server(host, port=port, get_info=ldap3.NONE, connect_timeout=int(timeout))
        conn = ldap3.Connection(server, receive_timeout=int(timeout), raise_exceptions=False, auto_bind=ldap3.AUTO_BIND_NONE)
        if not conn.open() and conn.closed:
            return ProbeResult(host, f"LDAP {port} RootDSE", False, "Не удалось открыть соединение",
                               int((time.monotonic() - t) * 1000))
        ok = conn.search("", "(objectClass=*)", ldap3.BASE, attributes=["dnsHostName", "defaultNamingContext", "isSynchronized"])
        entry = conn.response[0]["attributes"] if ok and conn.response else {}
        conn.unbind()
        if not ok:
            return ProbeResult(host, f"LDAP {port} RootDSE", False, f"RootDSE не прочитан: {conn.result.get('description')}",
                               int((time.monotonic() - t) * 1000))
        dns = entry.get("dnsHostName")
        nc = entry.get("defaultNamingContext")
        sync = entry.get("isSynchronized")
        return ProbeResult(host, f"LDAP {port} RootDSE", True, f"Служба LDAP отвечает: {dns}; {nc}; isSynchronized={sync}",
                           int((time.monotonic() - t) * 1000), {"dnsHostName": str(dns), "defaultNamingContext": str(nc)})
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(host, f"LDAP {port} RootDSE", False, mask_text(f"{type(exc).__name__}: {exc}"),
                           int((time.monotonic() - t) * 1000))


def ldap_service_checks(host: str, timeout: float = 5.0, ca_file: str | None = None,
                        cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> list[ProbeResult]:
    steps = [
        ("DNS", lambda: resolve(host, timeout)),
        ("TCP 389", lambda: tcp_check(host, 389, timeout, "LDAP")),
        ("TCP 636", lambda: tcp_check(host, 636, timeout, "LDAPS")),
        ("RootDSE", lambda: ldap_rootdse_probe(host, 389, timeout)),
        ("LDAPS", lambda: tls_probe(host, 636, timeout, ca_file)),
        ("StartTLS", lambda: tls_probe(host, 389, timeout, ca_file, starttls=True)),
        ("TCP 3268", lambda: tcp_check(host, 3268, timeout, "Global Catalog")),
    ]
    out = []
    for i, (name, fn) in enumerate(steps):
        if cancel:
            cancel.raise_if_cancelled()
        progress(int(i * 100 / len(steps)), f"{name}: {host}")
        out.append(fn())
    progress(100, "Проверка LDAP завершена")
    return out


def computer_reachability(host: str, timeout: float = 3.0, cancel: CancelToken | None = None,
                          progress: Progress = NULL_PROGRESS) -> list[ProbeResult]:
    out = [resolve(host, timeout)]
    progress(15, f"ping {host}")
    out.append(ping(host, timeout))
    for i, (port, label) in enumerate(COMMON_COMPUTER_PORTS):
        if cancel:
            cancel.raise_if_cancelled()
        progress(30 + i * 14, f"TCP {port} {host}")
        out.append(tcp_check(host, port, timeout, label))
    progress(100, "Готово")
    return out


def batch_reachability(hosts: list[str], timeout: float = 2.0, workers: int = 16, cancel: CancelToken | None = None,
                       progress: Progress = NULL_PROGRESS) -> list[dict]:
    """Parallel quick check for a list of computers: DNS, ping, TCP 445/3389."""
    results: list[dict] = []

    def one(h: str) -> dict:
        row = {"host": h, "dns": "", "ping": "", "smb_445": "", "rdp_3389": "", "summary": ""}
        try:
            r = resolve(h, timeout)
        except ValidationError as exc:
            row["summary"] = exc.message
            return row
        row["dns"] = r.message if r.ok else f"нет: {r.message}"
        if not r.ok:
            row["summary"] = "Имя не разрешается"
            return row
        p = ping(h, timeout)
        row["ping"] = p.status_text
        s = tcp_check(h, 445, timeout)
        row["smb_445"] = s.status_text
        d = tcp_check(h, 3389, timeout)
        row["rdp_3389"] = d.status_text
        any_ok = p.ok or s.ok or d.ok
        row["summary"] = "Отвечает" if any_ok else "Не отвечает (ICMP/445/3389)"
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(one, h): h for h in hosts}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            if cancel and cancel.cancelled:
                for f in futures:
                    f.cancel()
                cancel.raise_if_cancelled()
            results.append(fut.result())
            done += 1
            progress(int(done * 100 / max(1, len(hosts))), f"Проверено {done}/{len(hosts)}")
    return sorted(results, key=lambda r: r["host"].lower())
