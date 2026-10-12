"""Typed document content. Whatever produced it (local model, template, web search), the content is
validated against these limits before anything is written to disk."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Kind = Literal["pptx", "docx", "xlsx", "pdf", "txt"]
KIND_TITLES = {"pptx": "презентация PowerPoint", "docx": "документ Word", "xlsx": "таблица Excel",
               "pdf": "документ PDF", "txt": "текстовый файл"}
KIND_SHORT = {"pptx": "презентацию", "docx": "документ", "xlsx": "таблицу", "pdf": "PDF", "txt": "текстовый файл"}


def _clean(value: str) -> str:
    # control characters break XML-based formats; keep tabs/newlines only where they make sense
    return "".join(ch for ch in value if ch.isprintable() or ch in "\n\t").strip()


class Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Section(Strict):
    heading: str = Field(min_length=1, max_length=160)
    paragraphs: list[str] = Field(default_factory=list, max_length=8)
    bullets: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("heading")
    @classmethod
    def _heading(cls, value: str) -> str:
        return " ".join(_clean(value).split())[:160]

    @field_validator("paragraphs", "bullets", mode="before")
    @classmethod
    def _texts(cls, value: object, info) -> object:
        if not isinstance(value, list):
            return value
        limit = 8 if info.field_name == "paragraphs" else 12  # a talkative model is trimmed, not rejected
        return [_clean(v)[:1500] for v in value if isinstance(v, str) and _clean(v)][:limit]


class Table(Strict):
    columns: list[str] = Field(min_length=1, max_length=10)
    rows: list[list[str]] = Field(default_factory=list, max_length=200)

    @field_validator("columns", mode="before")
    @classmethod
    def _columns(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [" ".join(_clean(str(v)).split())[:80] or f"Столбец {i + 1}" for i, v in enumerate(value)][:10]

    @field_validator("rows", mode="before")
    @classmethod
    def _rows(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [[_clean(str(cell))[:300] for cell in row][:10] for row in value if isinstance(row, list)][:200]

    def normalized_rows(self) -> list[list[str]]:
        width = len(self.columns)
        return [(row + [""] * width)[:width] for row in self.rows]


class SourceRef(Strict):
    title: str = Field(max_length=200)
    url: str = Field(max_length=2048)


class DocumentContent(Strict):
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = Field("", max_length=300)
    sections: list[Section] = Field(default_factory=list, max_length=14)
    table: Optional[Table] = None
    sources: list[SourceRef] = Field(default_factory=list, max_length=12)
    note: str = Field("", max_length=300)  # e.g. "шаблон: локальная модель недоступна"

    @field_validator("title", "subtitle")
    @classmethod
    def _line(cls, value: str) -> str:
        return " ".join(_clean(value).split())

    @field_validator("sections", mode="before")
    @classmethod
    def _sections(cls, value: object) -> object:
        return value[:14] if isinstance(value, list) else value

    @field_validator("sources", mode="before")
    @classmethod
    def _sources(cls, value: object) -> object:
        return value[:12] if isinstance(value, list) else value


def content_schema() -> dict:
    """JSON schema handed to Ollama (structured outputs)."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "subtitle": {"type": "string"},
            "sections": {"type": "array", "items": {
                "type": "object",
                "properties": {"heading": {"type": "string"},
                               "paragraphs": {"type": "array", "items": {"type": "string"}},
                               "bullets": {"type": "array", "items": {"type": "string"}}},
                "required": ["heading", "paragraphs", "bullets"]}},
            "table": {"type": "object", "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}}},
        },
        "required": ["title", "subtitle", "sections"],
    }
