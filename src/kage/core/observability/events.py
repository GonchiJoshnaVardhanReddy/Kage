"""Structured observability event models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from kage.utils import utcnow


class TraceSeverity(str, Enum):
    """Severity levels for runtime trace events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TraceEvent(BaseModel):
    """One structured runtime event in the execution trace."""

    event_type: str
    timestamp: datetime = Field(default_factory=utcnow)
    session_id: str
    turn_id: int = 0
    component: str
    payload: dict[str, Any] = Field(default_factory=dict)
    severity: TraceSeverity = TraceSeverity.INFO
    duration_ms: float | None = None

