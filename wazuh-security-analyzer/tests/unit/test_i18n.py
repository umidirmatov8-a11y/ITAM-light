import re
import sys
from pathlib import Path

import pytest
import yaml

from app.i18n import get_language, n, num, set_language, severity_label, tr
from app.i18n.ru import RU
from app.utils.timeutil import fmt_duration

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def russian():
    previous = get_language()
    set_language("ru")
    yield
    set_language(previous)


def test_every_source_string_is_translated():
    from i18n_keys import collect
    missing = sorted(collect() - set(RU))
    assert not missing, f"missing Russian translations: {missing[:20]}"


def test_placeholders_match():
    for key, value in RU.items():
        assert set(re.findall(r"\{(\w+)\}", key)) == set(re.findall(r"\{(\w+)\}", value)), key


def test_tr_and_formatting(russian):
    assert tr("Settings") == "Настройки"
    assert tr("Possible brute-force attack from {ip}", ip="203.0.113.5") == "Возможный подбор пароля с 203.0.113.5"
    assert tr("not in catalog") == "not in catalog"  # untranslated strings fall back to English
    assert severity_label("critical") == "КРИТИЧЕСКИЙ"
    assert num(18421) == "18 421"
    assert n(1, "event") == "1 событие" and n(3, "event") == "3 события" and n(147, "event") == "147 событий"
    assert n(11, "host") == "11 хостов" and n(21, "host") == "21 хост" and n(22, "host") == "22 хоста"
    assert fmt_duration(1024) == "17 мин 4 с"


def test_english_defaults():
    set_language("en")
    assert tr("Settings") == "Settings"
    assert n(1, "event") == "1 event" and n(2, "event") == "2 events"
    assert num(18421) == "18,421"
    assert fmt_duration(1024) == "17m 4s"


def test_unknown_language_falls_back_to_english():
    set_language("de")
    assert get_language() == "en"


def test_russian_playbooks_mirror_english():
    en = yaml.safe_load((ROOT / "resources/knowledge/playbooks.yaml").read_text())["playbooks"]
    ru = yaml.safe_load((ROOT / "resources/knowledge/playbooks.ru.yaml").read_text(encoding="utf-8"))["playbooks"]
    assert en.keys() == ru.keys()
    for category in en:
        for section in ("immediate", "investigation", "remediation", "prevention"):
            a, b = en[category].get(section) or [], ru[category].get(section) or []
            assert len(a) == len(b), (category, section)
            for x, y in zip(a, b):
                assert set(re.findall(r"\{(\w+)\}", x["text"])) == set(re.findall(r"\{(\w+)\}", y["text"]))
                assert x.get("when") == y.get("when") and x.get("unless") == y.get("unless")


def test_russian_rule_knowledge(russian):
    from app.analyzers.rule_knowledge import default_rule_kb
    info = default_rule_kb().get("5710")
    assert "несуществующей" in info.explanation or "не существует" in info.explanation or "нет на хосте" in info.explanation
    assert info.description == "sshd: Attempt to login using a non-existent user"  # Wazuh rule text unchanged
    assert all(re.search("[а-яА-Я]", step) for step in info.investigation)
