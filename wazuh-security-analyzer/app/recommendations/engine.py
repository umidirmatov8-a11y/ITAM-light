"""Recommendations Engine.

Playbooks (``resources/knowledge/playbooks.yaml``) contain templated steps.  A step is
rendered only when every placeholder is known and every condition holds, so the output
always refers to the concrete IP, account, host, file or CVE of the finding.  Steps from
the rule knowledge base are appended.  Output is split into immediate actions,
investigation, remediation and prevention.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

import yaml

from app.core import paths
from app.i18n import get_language, tr
from app.models.analysis import AlertGroup, Incident
from app.models.categories import Category
from app.utils.text import truncate_list
from app.utils.timeutil import fmt_ts

log = logging.getLogger(__name__)

SECTIONS = ("immediate", "investigation", "remediation", "prevention")
SECTION_TITLES = {
    "immediate": "Immediate actions",
    "investigation": "Investigation",
    "remediation": "Remediation",
    "prevention": "Prevention",
}


def section_title(key: str) -> str:
    return tr(SECTION_TITLES[key])
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
MAX_PER_SECTION = 8


@lru_cache(maxsize=4)
def _load_playbooks(lang: str = "en") -> dict[str, Any]:
    localized = paths.knowledge_dir() / f"playbooks.{lang}.yaml"
    path = localized if lang != "en" and localized.exists() else paths.knowledge_dir() / "playbooks.yaml"
    try:
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("playbooks", {})
    except (OSError, yaml.YAMLError) as exc:
        log.error("Cannot load playbooks: %s", exc)
        return {}


class RecommendationEngine:
    def __init__(self, rule_kb=None, high_risk_threshold: float = 60.0):
        self.rule_kb = rule_kb
        self.playbooks = _load_playbooks(get_language())
        self.high_risk = high_risk_threshold

    def values_for(self, g: AlertGroup) -> dict[str, str]:
        domain = next((v for t, v, _ in g.ioc_items() if t == "domain"), "")
        return {
            "src_ip": g.src_ip,
            # Only name an account when the finding concerns exactly one account.
            "user": g.users[0] if len(g.users) == 1 else ("" if g.users else g.user),
            "users": truncate_list(g.users, 10) if g.users else "",
            "agent": g.agent_name,
            "hosts": g.agent_name,
            "rule_id": g.rule_id,
            "cve": g.cve,
            "package": g.packages[0] if g.packages else "",
            "file_path": g.file_paths[0] if g.file_paths else "",
            "hash": g.file_hash,
            "process": g.processes[0] if g.processes else "",
            "command_line": (g.command_lines[0][:200] if g.command_lines else ""),
            "domain": domain,
            "count": f"{g.count:,}",
            "first_seen": fmt_ts(g.first_ts) if g.first_ts else "",
            "last_seen": fmt_ts(g.last_ts) if g.last_ts else "",
            "window": tr("30 minutes"),
        }

    def conditions_for(self, g: AlertGroup) -> set[str]:
        cond: set[str] = set()
        if g.src_ip and g.src_external:
            cond.add("external_source")
        if g.src_ip and not g.src_external:
            cond.add("internal_source")
        if g.success_after_failures:
            cond.add("success_after_failures")
        if g.category == Category.AUTH_SUCCESS.value:
            cond.add("auth_success")
        if g.kev:
            cond.add("kev")
        if g.ioc_verdict == "malicious" or (g.vt_positives or 0) >= 3:
            cond.add("malicious_ioc")
        if len(g.users) > 1:
            cond.add("multiple_users")
        if g.chain_ids:
            cond.add("in_chain")
        if g.risk_score >= self.high_risk:
            cond.add("high_risk")
        if any("ssh" in grp.lower() for grp in g.rule_groups) or "sshd" in g.rule_description.lower():
            cond.add("ssh")
        return cond

    def _render(self, steps: list[dict[str, Any]], values: dict[str, str], conditions: set[str]) -> list[str]:
        rendered: list[str] = []
        for step in steps or []:
            if not isinstance(step, dict) or "text" not in step:
                continue
            when = step.get("when") or []
            unless = step.get("unless") or []
            if any(c not in conditions for c in when) or any(c in conditions for c in unless):
                continue
            text = str(step["text"])
            names = _PLACEHOLDER.findall(text)
            if any(not values.get(n) for n in names):
                continue
            rendered.append(_PLACEHOLDER.sub(lambda m: values[m.group(1)], text))
        return rendered

    def for_group(self, g: AlertGroup) -> dict[str, list[str]]:
        playbook = self.playbooks.get(g.category) or self.playbooks.get("other", {})
        values = self.values_for(g)
        conditions = self.conditions_for(g)
        result: dict[str, list[str]] = {}
        for section in SECTIONS:
            result[section] = self._render(playbook.get(section, []), values, conditions)
        info = self.rule_kb.get(g.rule_id) if self.rule_kb else None
        if info:
            # Rule-specific knowledge complements generic playbooks that produced few concrete steps.
            for section, steps in (("investigation", info.investigation), ("remediation", info.remediation)):
                if len(result[section]) < 3:
                    for step in steps:
                        if step not in result[section]:
                            result[section].append(step)
        if g.chain_ids and not any("attack chain" in s for s in result["immediate"]):
            result["immediate"].insert(0, tr("Review the full correlated attack chain on {host} - treat the related "
                                             "alerts as one incident.", host=g.agent_name or tr("the host")))
        if g.fp_probability >= 0.6:
            result["investigation"].insert(0, tr("Confirm the benign explanation (scanner, scheduled job, maintenance) "
                                                 "and tune the rule if it is confirmed."))
        if g.severity in ("informational", "low") and not g.chain_ids:
            result["immediate"] = []
        return {k: v[:MAX_PER_SECTION] for k, v in result.items()}

    @staticmethod
    def merge(recommendation_sets: list[dict[str, list[str]]], limit: int = MAX_PER_SECTION) -> dict[str, list[str]]:
        merged: dict[str, list[str]] = {s: [] for s in SECTIONS}
        for rec in recommendation_sets:
            for section in SECTIONS:
                for step in rec.get(section, []):
                    if step not in merged[section] and len(merged[section]) < limit:
                        merged[section].append(step)
        return merged

    def for_incident(self, incident: Incident, groups: list[AlertGroup]) -> dict[str, list[str]]:
        ordered = sorted(groups, key=lambda g: -g.risk_score)
        return self.merge([g.recommendations or self.for_group(g) for g in ordered[:10]], limit=10)
