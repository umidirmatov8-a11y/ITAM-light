"""Shared data contracts between router, permission manager, executor and API."""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Risk(str, Enum):
    A = "A"  # safe
    B = "B"  # changes state
    C = "C"  # critical


class Source(str, Enum):
    UI = "ui"            # button in the interface
    TEXT = "text"        # typed command
    VOICE = "voice"      # recognized speech
    GESTURE = "gesture"  # camera gesture
    SCENARIO = "scenario"
    AI = "ai"            # plan proposed by a language model


class Status(str, Enum):
    DONE = "done"
    DRY_RUN = "dry_run"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CLARIFY = "clarify"
    DENIED = "denied"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    IGNORED = "ignored"
    ERROR = "error"
    REPLY = "reply"


class ActionRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    source: Source = Source.TEXT


class ActionResult(BaseModel):
    ok: bool
    status: Status
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    undo: Optional[ActionRequest] = None
    # Repeating the action is meaningful (volume +10 again, launch again).
    repeatable: bool = True


class ConfirmationInfo(BaseModel):
    id: str
    action: str
    title: str
    description: str
    risk: Risk
    expires_at: float
    requires_acknowledge: bool


class ClarifyInfo(BaseModel):
    question: str
    options: list[str] = Field(default_factory=list)


class CommandResponse(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = Field(default_factory=time.time)
    input: str = ""
    source: Source = Source.TEXT
    status: Status
    message: str
    intent: Optional[str] = None
    action: Optional[str] = None
    risk: Optional[Risk] = None
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation: Optional[ConfirmationInfo] = None
    clarify: Optional[ClarifyInfo] = None
    dry_run: bool = False
