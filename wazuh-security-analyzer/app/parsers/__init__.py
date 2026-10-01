"""Input parsers.

Layout::

    parsers/
        base.py            parser interface and wrapper helpers
        registry.py        registration + automatic format detection
        sources.py         files / folders / ZIP / GZIP discovery with safety limits
        wazuh_json.py      JSON arrays, pretty-printed objects, export wrappers
        wazuh_jsonl.py     alerts.json (JSON lines / NDJSON)
        wazuh_csv.py       CSV / TSV exports
        wazuh_xml.py       XML exports, Windows Event XML
        wazuh_text.py      classic alerts.log
        cef.py             Common Event Format
        generic_log.py     unknown line-based logs

Future vendors (ESET, Kaspersky, FortiGate, SecureTower, Windows, Linux auditd, Sysmon)
are added as new ``BaseParser`` subclasses with their own ``vendor`` attribute and
registered through :func:`app.parsers.registry.register_parser`.
"""

from app.parsers.registry import detect_parser, get_parser, register_parser, registered_parsers

__all__ = ["detect_parser", "get_parser", "register_parser", "registered_parsers"]
