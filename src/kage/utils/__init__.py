"""Utilities module for Kage."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Get current UTC time as a naive datetime (no tzinfo).

    Replaces deprecated datetime.utcnow() while maintaining
    compatibility with existing naive datetime fields.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
