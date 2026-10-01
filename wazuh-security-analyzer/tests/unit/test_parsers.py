import io
import json

import pytest

from app.parsers.base import ParseContext, iter_alert_dicts, unflatten
from app.parsers.cef import CEFParser, parse_extension
from app.parsers.generic_log import GenericLogParser
from app.parsers.registry import detect_encoding, detect_parser
from app.parsers.wazuh_csv import WazuhCSVParser
from app.parsers.wazuh_json import WazuhJSONParser
from app.parsers.wazuh_jsonl import WazuhJSONLParser
from app.parsers.wazuh_text import WazuhAlertsLogParser
from app.parsers.wazuh_xml import WazuhXMLParser


def parse(parser, text, name="x"):
    ctx = ParseContext(name)
    return list(parser.parse(io.StringIO(text), ctx)), ctx


ALERT = {"timestamp": "2026-09-30T10:00:00.000+0000", "rule": {"id": "5710", "level": 5, "description": "x"},
         "agent": {"name": "web-01"}}


def test_json_array_streaming():
    text = json.dumps([ALERT] * 3)
    records, ctx = parse(WazuhJSONParser(), text)
    assert len(records) == 3 and ctx.errors == 0


def test_json_pretty_concatenated_objects():
    text = "\n".join(json.dumps(ALERT, indent=2) for _ in range(4))
    records, ctx = parse(WazuhJSONParser(), text)
    assert len(records) == 4


def test_json_opensearch_wrapper():
    text = json.dumps({"hits": {"hits": [{"_source": ALERT}, {"_source": ALERT}]}})
    records, _ = parse(WazuhJSONParser(), text)
    assert len(records) == 2 and records[0]["rule"]["id"] == "5710"


def test_json_wazuh_api_wrapper():
    text = json.dumps({"data": {"affected_items": [ALERT], "total_affected_items": 1}, "error": 0})
    records, _ = parse(WazuhJSONParser(), text)
    assert len(records) == 1


def test_corrupted_json_array_recovers():
    good = json.dumps(ALERT)
    text = "[" + good + ",\n{\"rule\": {\"id\": \"1\", BROKEN\n," + good + "]"
    records, ctx = parse(WazuhJSONParser(), text)
    assert len(records) == 2
    assert ctx.errors >= 1


def test_json_large_object_spanning_chunks():
    big = dict(ALERT, full_log="A" * (3 * 1024 * 1024))
    records, ctx = parse(WazuhJSONParser(), json.dumps([big, ALERT]))
    assert len(records) == 2 and ctx.errors == 0


def test_jsonl_skips_corrupted_lines():
    text = json.dumps(ALERT) + "\n{not json}\n\n" + json.dumps(ALERT) + "\n[1,2\n"
    records, ctx = parse(WazuhJSONLParser(), text)
    assert len(records) == 2 and ctx.errors == 2


def test_csv_dotted_columns_and_lists():
    text = ("timestamp,rule.id,rule.level,rule.description,agent.name,rule.groups,data.srcip\n"
            "2026-09-30T10:00:00Z,5710,5,sshd: test,web-01,\"syslog, sshd\",203.0.113.5\n")
    records, ctx = parse(WazuhCSVParser(), text)
    assert records[0]["rule"]["id"] == "5710"
    assert records[0]["agent"]["name"] == "web-01"
    assert records[0]["data"]["srcip"] == "203.0.113.5"
    assert ctx.errors == 0


def test_csv_source_prefix_and_semicolon():
    text = "_source.rule.id;_source.agent.name\n100;host-a\n"
    records, _ = parse(WazuhCSVParser(), text)
    assert records[0] == {"rule": {"id": "100"}, "agent": {"name": "host-a"}}


def test_invalid_csv_rows_counted_not_fatal():
    text = "rule.id,rule.level,agent.name\n5710,5,web\n1,2\n\"unterminated,3,4\n5715,3,web\n"
    records, ctx = parse(WazuhCSVParser(), text)
    assert ctx.errors >= 1
    assert any(r.get("rule", {}).get("id") == "5710" for r in records)


def test_csv_with_line_split_across_sample_boundary():
    header = "rule.id,rule.level,full_log\n"
    rows = "".join(f"{i},5,{'x' * 200}\n" for i in range(800))
    records, ctx = parse(WazuhCSVParser(), header + rows)
    assert len(records) == 800 and ctx.errors == 0


def test_xml_alerts():
    text = ("<alerts><alert><timestamp>2026-09-30T10:00:00Z</timestamp><rule id='5402' level='3'>"
            "<description>sudo</description><groups><group>sudo</group></groups></rule>"
            "<agent name='db-01'/></alert></alerts>")
    records, ctx = parse(WazuhXMLParser(), text)
    assert records[0]["rule"]["id"] == "5402"
    assert records[0]["rule"]["groups"] == ["sudo"]
    assert records[0]["agent"]["name"] == "db-01"


def test_xml_entity_expansion_rejected():
    text = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
            "<alerts><alert><rule id='1'>&lol2;</rule></alert></alerts>")
    records, ctx = parse(WazuhXMLParser(), text)
    assert records == [] and ctx.errors == 1


def test_xml_external_entity_rejected():
    text = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            "<alerts><alert><full_log>&xxe;</full_log></alert></alerts>")
    records, ctx = parse(WazuhXMLParser(), text)
    assert records == [] and ctx.errors == 1


def test_windows_event_xml():
    text = ("<Events><Event><System><EventID>4625</EventID><Computer>WS1</Computer></System>"
            "<EventData><Data Name='TargetUserName'>bob</Data><Data Name='IpAddress'>203.0.113.9</Data>"
            "</EventData></Event></Events>")
    records, _ = parse(WazuhXMLParser(), text)
    assert records[0]["rule"]["id"] == "win:4625"
    assert records[0]["data"]["win"]["eventdata"]["targetUserName"] == "bob"


def test_alerts_log_text():
    text = ("** Alert 1727690400.1234: - syslog,sshd,authentication_failed,\n"
            "2024 Sep 30 10:00:00 (web-01) 10.0.0.5->/var/log/auth.log\n"
            "Rule: 5710 (level 5) -> 'sshd: Attempt to login using a non-existent user'\n"
            "Src IP: 203.0.113.10\nUser: admin\n"
            "Sep 30 10:00:00 web-01 sshd[1]: Invalid user admin from 203.0.113.10 port 4\n\n"
            "** Alert 1727690401.1: - ossec,\n2024 Sep 30 10:00:01 web-01->ossec\n"
            "Rule: 503 (level 3) -> 'Wazuh agent started.'\nossec: Agent started\n")
    records, ctx = parse(WazuhAlertsLogParser(), text)
    assert len(records) == 2 and ctx.errors == 0
    assert records[0]["rule"]["level"] == 5
    assert records[0]["data"]["srcip"] == "203.0.113.10"
    assert records[0]["agent"]["name"] == "web-01"
    assert records[1]["agent"]["name"] == "web-01"


def test_cef_parsing():
    line = ("Sep 30 10:00:00 fw1 CEF:0|Vendor|FW|1.0|100|Port scan|8|src=192.0.2.1 dst=10.0.0.1 dpt=22 "
            "msg=Multiple ports probed suser=bob\n")
    records, ctx = parse(CEFParser(), line)
    r = records[0]
    assert r["data"]["srcip"] == "192.0.2.1"
    assert r["data"]["msg"] == "Multiple ports probed"
    assert r["rule"]["level"] == 12
    assert r["rule"]["id"] == "cef:Vendor:100"


def test_cef_escaped_pipe_and_equals():
    assert parse_extension(r"msg=a\=b c=d") == {"msg": "a=b", "c": "d"}


def test_generic_syslog_patterns():
    rec = GenericLogParser.parse_line("Sep 30 10:00:00 host1 sshd[22]: Failed password for root from 198.51.100.4 port 22 ssh2")
    assert rec["rule"]["id"] == "generic:ssh_failed_password"
    assert rec["data"]["dstuser"] == "root"
    assert rec["data"]["srcip"] == "198.51.100.4"
    assert rec["agent"]["name"] == "host1"


@pytest.mark.parametrize("head,name,expected", [
    (json.dumps(ALERT) + "\n" + json.dumps(ALERT) + "\n", "alerts.json", "wazuh_jsonl"),
    ("[\n " + json.dumps(ALERT, indent=2), "x.json", "wazuh_json"),
    ("rule.id,rule.level,agent.name\n1,2,3\n", "export.txt", "wazuh_csv"),
    ("<alerts><alert/></alerts>", "a.log", "wazuh_xml"),
    ("** Alert 1.1: - x\n2024 Sep 30 10:00:00 h->l\nRule: 1 (level 1) -> 'x'\n", "a.json", "wazuh_alerts_log"),
    ("CEF:0|a|b|c|d|e|5|src=1.2.3.4\n", "x.txt", "cef"),
    ("Sep 30 10:00:00 host sshd[1]: hello\n", "x.log", "generic_log"),
])
def test_detection_by_content_not_extension(head, name, expected):
    cls, score = detect_parser(head, name)
    assert cls.name == expected and score > 0


def test_encoding_detection():
    assert detect_encoding(b"\xef\xbb\xbf{") == "utf-8-sig"
    assert detect_encoding("{}".encode("utf-16")) == "utf-16"
    assert detect_encoding(b"{\"a\":1}") == "utf-8"


def test_unflatten_and_iter_helpers():
    assert unflatten({"rule.id": 1, "rule.level": 2, "_index": "x"}) == {"rule": {"id": 1, "level": 2}}
    assert list(iter_alert_dicts({"alerts": [ALERT, ALERT]})) == [ALERT, ALERT]
    assert list(iter_alert_dicts([{"_source": ALERT}])) == [ALERT]
    generic = {"message": "app started", "level": "info"}
    assert list(iter_alert_dicts(generic)) == [generic]
