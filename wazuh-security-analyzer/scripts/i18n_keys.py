"""Collect translatable English source strings (used by tests and when updating translations).

    python scripts/i18n_keys.py            # print keys missing from app/i18n/ru.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TEMPLATE = ROOT / "resources" / "templates" / "report.html.j2"

# Calls whose first string argument is translated at runtime (directly or by the callee).
_TRANSLATING_CALLS = {"tr", "h", "Card", "StatCard", "sheet", "section_title"}
# Technical values picked up by the heuristics that are never shown translated.
IGNORED = {"", "#", "configure_ai", "ID", "IP", "ASN", "CVE", "CVSS", "CWE", "IOC", "MITRE", "CSV", "HTML", "JSON",
           "PDF", "Excel", "OpenAI", "Anthropic", "CISA KEV", "MITRE ATT&CK", "FP", "Language / Язык"}
_HEADER_CALLS = {"table", "tbl", "sheet"}  # list-of-headers argument


def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def collect() -> set[str]:
    keys: set[str] = set()
    for path in APP.rglob("*.py"):
        if "i18n" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else "")
                if name in _TRANSLATING_CALLS and node.args and _const(node.args[0]):
                    keys.add(_const(node.args[0]))
                if name in _HEADER_CALLS:
                    for arg in node.args:
                        if isinstance(arg, ast.List):
                            keys.update(v for v in map(_const, arg.elts) if v)
                if name == "kv_table" and node.args and isinstance(node.args[0], ast.List):
                    for elt in node.args[0].elts:
                        if isinstance(elt, ast.Tuple) and elt.elts and _const(elt.elts[0]):
                            keys.add(_const(elt.elts[0]))
            # table column specs: ("key", "Header", formatter)
            if isinstance(node, ast.Tuple) and len(node.elts) == 3 and all(
                    _const(e) is not None for e in node.elts[:2]) and (
                    isinstance(node.elts[2], (ast.Lambda, ast.Constant)) and _const(node.elts[2]) is None):
                keys.add(_const(node.elts[1]))
            # ("Label", value) pairs used for report/statistics rows (translated with tr(k) at render time)
            if isinstance(node, ast.Tuple) and len(node.elts) == 2 and _const(node.elts[0]) and \
                    _const(node.elts[1]) is None and not isinstance(node.elts[1], ast.Constant) and \
                    ("reports" in path.parts or "ui" in path.parts) and re.match(r"^[A-Z][a-z]", _const(node.elts[0])):
                keys.add(_const(node.elts[0]))
            # class attributes title / subtitle of pages
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                    and node.targets[0].id in ("title", "subtitle") and _const(node.value):
                keys.add(_const(node.value))
    # dictionaries / tables of labels that are translated through tr(variable)
    from app.ai.providers.factory import PROVIDER_LABELS
    from app.core.secrets import KNOWN_SECRETS
    from app.correlation.chains import SCENARIO_TACTICS, STAGES
    from app.intelligence.mitre import default_catalog
    from app.models.analysis import IncidentStatus
    from app.models.categories import CATEGORY_LABELS
    from app.recommendations.engine import SECTION_TITLES
    from app.reports.summary import _KIND_PHRASES
    from app.analyzers.explainer import ASSESSMENTS
    from app.ai.engine import EXTERNAL_WARNING
    from app.i18n import _ENUM_LABELS
    from app.ui.onboarding import _INTRO, OnboardingDialog
    from app.ui.main_window import NAV
    from app.ui.pages.reports import FORMAT_LABELS, SECTION_LABELS

    from app.intelligence.mitre import _COMMAND_HEURISTICS
    keys.update(label for _, _, _, label in _COMMAND_HEURISTICS)
    keys.update(PROVIDER_LABELS.values())
    keys.update(KNOWN_SECRETS.values())
    keys.update(SCENARIO_TACTICS.values())
    keys.update(label for _, _, label in STAGES.values())
    keys.update(t["name"] for t in default_catalog().tactics.values())
    keys.update(s.value for s in IncidentStatus)
    keys.update(CATEGORY_LABELS.values())
    keys.update(SECTION_TITLES.values())
    keys.update(_KIND_PHRASES.values())
    keys.update(ASSESSMENTS)
    keys.update(["Exposure (actively exploited vulnerability)", "Exposure (vulnerable software)"])
    keys.add(EXTERNAL_WARNING)
    keys.update(_ENUM_LABELS.values())
    keys.add(_INTRO)
    keys.update(label for label, _, _ in OnboardingDialog._BUTTONS)
    keys.update(label for _, _, label in NAV)
    keys.update(label for _, label in FORMAT_LABELS)
    keys.update(SECTION_LABELS.values())
    # enumerated values translated with tr(value)
    keys.update(["malicious", "suspicious", "clean", "unknown", "high", "medium", "low", "critical",
                 "OFFLINE", "ONLINE", "internal", "external", "attack chain", "brute force", "web attack", "scan",
                 "malware", "vulnerability", "single", "ip", "cve", "mitre", "hash", "rule", "text",
                 "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    # Jinja template: t("...")
    for match in re.finditer(r'\bt\("((?:[^"\\]|\\.)*)"\)', TEMPLATE.read_text(encoding="utf-8")):
        keys.add(match.group(1).replace('\\"', '"'))
    return {k for k in keys if k not in IGNORED}


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from app.i18n.ru import RU
    missing = sorted(collect() - set(RU))
    print(f"{len(missing)} missing translations")
    for key in missing:
        print(repr(key))
