"""Strict Pydantic schema for AI analyst responses."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TECH = re.compile(r"^T\d{4}(?:\.\d{3})?$")


class AIMitreItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    technique_id: str
    name: str = ""
    tactic: str = ""
    confidence: Literal["high", "medium", "low"] = "low"
    evidence: str = ""

    @field_validator("technique_id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        value = value.strip().upper()
        if not _TECH.match(value):
            raise ValueError(f"invalid MITRE technique id {value!r}")
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, value: Any) -> str:
        v = str(value or "low").lower()
        return v if v in ("high", "medium", "low") else "low"


def _str_list(value: Any, limit: int = 15, item_len: int = 500) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("expected a list of strings")
    out = []
    for item in value[:limit]:
        if isinstance(item, dict):
            item = item.get("text") or item.get("action") or item.get("step") or str(item)
        text = str(item).strip()
        if text:
            out.append(text[:item_len])
    return out


class AIAnalysisResult(BaseModel):
    """Structure the AI analyst must return (see :mod:`app.ai.prompts`)."""

    model_config = ConfigDict(extra="ignore")

    severity: Literal["critical", "high", "medium", "low", "informational"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(max_length=4000)
    what_happened: str = Field(default="unknown", max_length=6000)
    why_it_matters: str = Field(default="unknown", max_length=6000)
    possible_attack: str = Field(default="unknown", max_length=3000)
    false_positive_probability: float = Field(ge=0.0, le=1.0)
    false_positive_reasoning: str = Field(default="", max_length=3000)
    mitre: list[AIMitreItem] = Field(default_factory=list)
    iocs: list[str] = Field(default_factory=list)
    cves: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    investigation_steps: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)
    prevention: list[str] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def _severity(cls, value: Any) -> str:
        v = str(value or "").strip().lower()
        return {"info": "informational", "information": "informational", "none": "informational"}.get(v, v)

    @field_validator("confidence", "false_positive_probability", mode="before")
    @classmethod
    def _probability(cls, value: Any) -> float:
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            value = float(value) / (100.0 if float(value) > 1.0 else 1.0)
        value = float(value)
        if 1.0 < value <= 100.0:
            value /= 100.0
        return value

    @field_validator("mitre", mode="before")
    @classmethod
    def _mitre(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("mitre must be a list")
        items = []
        for item in value[:20]:
            if isinstance(item, str):
                items.append({"technique_id": item.split()[0] if item.strip() else item})
            elif isinstance(item, dict):
                if "technique_id" not in item:
                    item = dict(item, technique_id=item.get("id") or item.get("technique") or "")
                items.append(item)
        return items

    @field_validator("iocs", "cves", mode="before")
    @classmethod
    def _short_lists(cls, value: Any) -> list[str]:
        return _str_list(value, limit=50, item_len=300)

    @field_validator("immediate_actions", "investigation_steps", "remediation", "prevention", mode="before")
    @classmethod
    def _steps(cls, value: Any) -> list[str]:
        return _str_list(value)


AI_JSON_TEMPLATE = {
    "severity": "critical|high|medium|low|informational",
    "confidence": 0.0,
    "summary": "",
    "what_happened": "",
    "why_it_matters": "",
    "possible_attack": "",
    "false_positive_probability": 0.0,
    "false_positive_reasoning": "",
    "mitre": [{"technique_id": "T0000", "name": "", "tactic": "", "confidence": "high|medium|low", "evidence": ""}],
    "iocs": [],
    "cves": [],
    "immediate_actions": [],
    "investigation_steps": [],
    "remediation": [],
    "prevention": [],
}
