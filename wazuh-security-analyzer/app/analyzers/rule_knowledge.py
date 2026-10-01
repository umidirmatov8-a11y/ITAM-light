"""Rule Intelligence: local knowledge base about Wazuh rules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.core import paths

log = logging.getLogger(__name__)


@dataclass
class RuleInfo:
    rule_id: str
    description: str
    category: str = "other"
    typical_level: int | None = None
    mitre: list[str] = field(default_factory=list)
    explanation: str = ""
    false_positives: list[str] = field(default_factory=list)
    investigation: list[str] = field(default_factory=list)
    remediation: list[str] = field(default_factory=list)
    source: str = "bundled"

    @property
    def typical_severity(self) -> str:
        level = self.typical_level or 0
        if level >= 12:
            return "high"
        if level >= 7:
            return "medium"
        if level >= 4:
            return "low"
        return "informational"


class RuleKnowledgeBase:
    def __init__(self, files: list[Path] | None = None, language: str = "en"):
        self._rules: dict[str, RuleInfo] = {}
        sources = files if files is not None else [
            paths.knowledge_dir() / "wazuh_rules.yaml",
            paths.user_data_dir() / "rule_knowledge.yaml",
        ]
        for idx, path in enumerate(sources):
            self._load(path, "bundled" if idx == 0 else "user")
        if files is None and language != "en":
            self._apply_translation(paths.knowledge_dir() / f"wazuh_rules.{language}.yaml")

    def _apply_translation(self, path: Path) -> None:
        """Overlay translated explanation / false positives / steps (rule descriptions stay as in Wazuh)."""
        if not path.exists():
            return
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            log.error("Cannot load rule translation %s: %s", path, exc)
            return
        for rule_id, info in (data.get("rules") or {}).items():
            rule = self._rules.get(str(rule_id))
            if rule is None or not isinstance(info, dict) or rule.source != "bundled":
                continue
            for key in ("explanation", "false_positives", "investigation", "remediation"):
                if info.get(key):
                    value = info[key]
                    setattr(rule, key, [str(v) for v in value] if isinstance(value, list) else str(value))

    def _load(self, path: Path, source: str) -> None:
        if not path.exists():
            return
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            log.error("Cannot load rule knowledge %s: %s", path, exc)
            return
        for rule_id, info in (data.get("rules") or {}).items():
            if not isinstance(info, dict):
                continue
            rid = str(rule_id)
            self._rules[rid] = RuleInfo(
                rule_id=rid,
                description=str(info.get("description", "")),
                category=str(info.get("category", "other")),
                typical_level=info.get("typical_level"),
                mitre=[str(m) for m in info.get("mitre", []) or []],
                explanation=str(info.get("explanation", "")),
                false_positives=[str(x) for x in info.get("false_positives", []) or []],
                investigation=[str(x) for x in info.get("investigation", []) or []],
                remediation=[str(x) for x in info.get("remediation", []) or []],
                source=source,
            )

    def get(self, rule_id: str) -> RuleInfo | None:
        return self._rules.get(str(rule_id))

    def __contains__(self, rule_id: str) -> bool:
        return str(rule_id) in self._rules

    def all(self) -> list[RuleInfo]:
        return sorted(self._rules.values(), key=lambda r: (len(r.rule_id), r.rule_id))


@lru_cache(maxsize=4)
def _rule_kb_for(language: str) -> RuleKnowledgeBase:
    return RuleKnowledgeBase(language=language)


def default_rule_kb() -> RuleKnowledgeBase:
    from app.i18n import get_language
    return _rule_kb_for(get_language())
