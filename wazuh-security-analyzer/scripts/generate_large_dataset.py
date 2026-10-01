"""Generate a large synthetic Wazuh alerts.json (JSON lines) for performance testing.

    python scripts/generate_large_dataset.py --count 100000 --out big_alerts.json
    python scripts/generate_large_dataset.py --count 1000000 --out huge.json.gz --gzip
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2026, 9, 1, tzinfo=timezone.utc)

TEMPLATES = [
    (0.30, "5501", 3, "PAM: Login session opened.", ["pam", "syslog", "authentication_success"]),
    (0.25, "5502", 3, "PAM: Login session closed.", ["pam", "syslog"]),
    (0.12, "5710", 5, "sshd: Attempt to login using a non-existent user",
     ["syslog", "sshd", "authentication_failed", "invalid_login"]),
    (0.08, "5402", 3, "Successful sudo to ROOT executed.", ["syslog", "sudo"]),
    (0.08, "550", 7, "Integrity checksum changed.", ["ossec", "syscheck"]),
    (0.06, "4101", 5, "Firewall drop event.", ["firewall"]),
    (0.04, "60122", 5, "Logon Failure - Unknown user or bad password", ["windows", "authentication_failed"]),
    (0.03, "31103", 7, "SQL injection attempt.", ["web", "accesslog", "attack", "sql_injection"]),
    (0.02, "23505", 10, "Vulnerability detected", ["vulnerability-detector"]),
    (0.02, "100210", 12, "Sysmon - PowerShell executed with an encoded command", ["windows", "sysmon", "sysmon_event1"]),
]


def generate(count: int, seed: int = 7):
    rng = random.Random(seed)
    agents = [f"host-{i:03d}" for i in range(200)]
    users = [f"user{i:03d}" for i in range(300)]
    weights = [t[0] for t in TEMPLATES]
    span = 30 * 86400
    for i in range(count):
        _, rule_id, level, desc, groups = rng.choices(TEMPLATES, weights)[0]
        ts = START + timedelta(seconds=rng.randint(0, span))
        agent = rng.choice(agents)
        data: dict = {}
        if rule_id in ("5710", "4101", "31103", "60122"):
            data["srcip"] = f"198.51.100.{rng.randint(1, 254)}" if rng.random() < 0.7 else f"10.{rng.randint(0, 9)}.0.{rng.randint(1, 254)}"
        if rule_id in ("5501", "5502", "5710", "5402", "60122"):
            data["dstuser"] = rng.choice(users)
        if rule_id == "23505":
            data["vulnerability"] = {"cve": f"CVE-2024-{rng.randint(1000, 1100)}", "severity": "High",
                                     "cvss": {"cvss3": {"base_score": "7.5"}}, "package": {"name": "pkg", "version": "1"}}
        if rule_id == "100210":
            data["win"] = {"eventdata": {"image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                                         "commandLine": "powershell -nop -w hidden -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoA"}}
        yield {"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
               "rule": {"id": rule_id, "level": level, "description": desc, "groups": groups},
               "agent": {"id": f"{agents.index(agent):03d}", "name": agent, "ip": f"10.50.{i % 200}.{i % 250 + 1}"},
               "id": f"{1790000000 + i}.{i}", "data": data,
               "full_log": f"{desc} on {agent} {json.dumps(data)[:200]}"}


def write(path: Path, count: int, use_gzip: bool = False) -> Path:
    opener = gzip.open if use_gzip else open
    with opener(path, "wt", encoding="utf-8") as fh:
        for doc in generate(count):
            fh.write(json.dumps(doc) + "\n")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100_000)
    ap.add_argument("--out", default="big_alerts.json")
    ap.add_argument("--gzip", action="store_true")
    args = ap.parse_args()
    print(write(Path(args.out), args.count, args.gzip))
