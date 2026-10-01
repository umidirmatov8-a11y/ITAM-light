"""XML alert exports.  Uses ``defusedxml`` (DTDs and entity expansion are forbidden)."""

from __future__ import annotations

from typing import Any, Iterator, TextIO

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from app.parsers.base import BaseParser, ParseContext

_RECORD_TAGS = {"alert", "event", "record", "entry", "item", "hit", "row", "log"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def element_to_dict(elem) -> Any:
    children = list(elem)
    attrs = {k.rsplit("}", 1)[-1]: v for k, v in elem.attrib.items()}
    text = (elem.text or "").strip()
    if not children and not attrs:
        return text
    result: dict[str, Any] = dict(attrs)
    for child in children:
        key = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else "node"
        # Windows Event XML: <Data Name="TargetUserName">bob</Data>
        if key == "Data" and "Name" in child.attrib:
            result[child.attrib["Name"]] = (child.text or "").strip()
            continue
        value = element_to_dict(child)
        if key in result:
            existing = result[key]
            if not isinstance(existing, list):
                result[key] = [existing]
            result[key].append(value)
        else:
            result[key] = value
    if text:
        result["#text"] = text
    return result


def _normalize_xml_alert(data: dict[str, Any]) -> dict[str, Any]:
    """Map common XML layouts to the Wazuh JSON shape."""
    rule = data.get("rule")
    if isinstance(rule, dict):
        if "#text" in rule and "description" not in rule:
            rule["description"] = rule.pop("#text")
        groups = rule.get("groups")
        if isinstance(groups, dict) and "group" in groups:
            g = groups["group"]
            rule["groups"] = g if isinstance(g, list) else [g]
        elif isinstance(groups, str):
            rule["groups"] = [x.strip() for x in groups.split(",") if x.strip()]
        mitre = rule.get("mitre")
        if isinstance(mitre, dict) and isinstance(mitre.get("id"), str):
            mitre["id"] = [mitre["id"]]
    # Windows <Event><System>..</System><EventData>..</EventData></Event>
    if "System" in data and "EventData" in data and "rule" not in data:
        system = data.get("System") or {}
        event_id = system.get("EventID")
        if isinstance(event_id, dict):
            event_id = event_id.get("#text", "")
        return {
            "timestamp": (system.get("TimeCreated") or {}).get("SystemTime") if isinstance(
                system.get("TimeCreated"), dict) else None,
            "rule": {"id": f"win:{event_id}", "level": 3, "description": f"Windows event {event_id}"},
            "agent": {"name": system.get("Computer", "")},
            "data": {"win": {"system": system, "eventdata": {
                k[0].lower() + k[1:]: v for k, v in (data.get("EventData") or {}).items() if isinstance(k, str) and k
            }}},
            "decoder": {"name": "windows_eventchannel"},
        }
    return data


class WazuhXMLParser(BaseParser):
    name = "wazuh_xml"
    description = "XML alert exports (Wazuh-like layout or Windows Event XML)"
    extensions = (".xml",)

    @classmethod
    def sniff(cls, head: str, filename: str) -> float:
        text = head.lstrip("﻿ \t\r\n")
        if not text.startswith("<"):
            return 0.0
        score = 0.7
        lowered = text[:4096].lower()
        if "<alert" in lowered or "<rule" in lowered or "<event" in lowered:
            score += 0.2
        return score

    def parse(self, stream: TextIO, ctx: ParseContext) -> Iterator[dict[str, Any]]:
        depth = 0
        root_tag = None
        try:
            for event, elem in SafeET.iterparse(stream, events=("start", "end"), forbid_dtd=True):
                if event == "start":
                    depth += 1
                    if depth == 1:
                        root_tag = _local(elem.tag)
                    continue
                depth -= 1
                tag = _local(elem.tag)
                is_record = (depth == 1 and (tag in _RECORD_TAGS or root_tag not in _RECORD_TAGS)) or \
                            (depth == 0 and tag in _RECORD_TAGS and ctx.records == 0 and len(elem))
                if is_record:
                    data = element_to_dict(elem)
                    if isinstance(data, dict) and data:
                        ctx.records += 1
                        yield _normalize_xml_alert(data)
                    elem.clear()
        except DefusedXmlException as exc:
            ctx.error(f"unsafe XML rejected: {type(exc).__name__}")
        except SafeET.ParseError as exc:
            ctx.error(f"XML parse error: {exc}")
