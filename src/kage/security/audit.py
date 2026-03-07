"""Audit logging for Kage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiofiles

from kage.core.models import AuditEntry
from kage.persistence.config import get_data_dir


class AuditLogger:
    """Tamper-evident audit logger with hash chain."""

    def __init__(
        self,
        session_id: str,
        log_dir: Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.log_dir = log_dir or get_data_dir() / "audit"
        self.log_file = self.log_dir / f"{session_id}.audit.jsonl"
        self._last_hash: str | None = None
        self._entry_count = 0

    async def initialize(self) -> None:
        """Initialize the audit log, loading existing hash chain."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

        if self.log_file.exists():
            # Load last hash from existing file
            async with aiofiles.open(self.log_file) as f:
                last_line = None
                async for line in f:
                    if line.strip():
                        last_line = line
                        self._entry_count += 1

                if last_line:
                    try:
                        data = json.loads(last_line)
                        self._last_hash = data.get("entry_hash")
                    except json.JSONDecodeError:
                        pass

    async def log(
        self,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Log an action with automatic hash chaining."""
        entry = AuditEntry(
            session_id=self.session_id,
            action=action,
            details=details or {},
        )

        # Finalize with hash chain
        entry.finalize(self._last_hash)
        self._last_hash = entry.entry_hash
        self._entry_count += 1

        # Append to log file
        async with aiofiles.open(self.log_file, "a") as f:
            line = json.dumps(entry.model_dump(mode="json"), default=str)
            await f.write(line + "\n")

        return entry

    async def log_command_suggested(
        self,
        command: str,
        suggested_by: str = "ai",
    ) -> AuditEntry:
        """Log a command suggestion."""
        return await self.log(
            "command_suggested",
            {
                "command": command,
                "suggested_by": suggested_by,
            },
        )

    async def log_command_approved(
        self,
        command: str,
        approved_by: str = "user",
    ) -> AuditEntry:
        """Log command approval."""
        return await self.log(
            "command_approved",
            {
                "command": command,
                "approved_by": approved_by,
            },
        )

    async def log_command_rejected(
        self,
        command: str,
        reason: str | None = None,
    ) -> AuditEntry:
        """Log command rejection."""
        return await self.log(
            "command_rejected",
            {
                "command": command,
                "reason": reason,
            },
        )

    async def log_command_executed(
        self,
        command: str,
        exit_code: int,
        duration: float,
        output_preview: str | None = None,
    ) -> AuditEntry:
        """Log command execution."""
        return await self.log(
            "command_executed",
            {
                "command": command,
                "exit_code": exit_code,
                "duration_seconds": duration,
                "output_preview": (output_preview or "")[:500],
            },
        )

    async def log_scope_violation(
        self,
        command: str,
        target: str,
        action_taken: str,
    ) -> AuditEntry:
        """Log a scope violation."""
        return await self.log(
            "scope_violation",
            {
                "command": command,
                "target": target,
                "action_taken": action_taken,
            },
        )

    async def log_safe_mode_block(
        self,
        command: str,
        reason: str,
        overridden: bool = False,
    ) -> AuditEntry:
        """Log a safe mode block."""
        return await self.log(
            "safe_mode_block",
            {
                "command": command,
                "reason": reason,
                "overridden": overridden,
            },
        )

    async def log_finding_added(
        self,
        finding_id: str,
        title: str,
        severity: str,
        auto_detected: bool,
    ) -> AuditEntry:
        """Log a new finding."""
        return await self.log(
            "finding_added",
            {
                "finding_id": finding_id,
                "title": title,
                "severity": severity,
                "auto_detected": auto_detected,
            },
        )

    async def log_session_event(
        self,
        event: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Log a session event."""
        return await self.log(f"session_{event}", details)

    async def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify the integrity of the audit log.

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        if not self.log_file.exists():
            return True, []

        errors = []
        previous_hash = None
        line_number = 0

        async with aiofiles.open(self.log_file) as f:
            async for line in f:
                line_number += 1
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    entry = AuditEntry(**data)

                    # Check hash chain
                    if entry.previous_hash != previous_hash:
                        errors.append(
                            f"Line {line_number}: Hash chain broken - "
                            f"expected previous_hash={previous_hash}, "
                            f"got {entry.previous_hash}"
                        )

                    # Verify entry hash
                    if not entry.verify():
                        errors.append(f"Line {line_number}: Entry hash verification failed")

                    previous_hash = entry.entry_hash

                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_number}: Invalid JSON - {e}")
                except Exception as e:
                    errors.append(f"Line {line_number}: Error - {e}")

        return len(errors) == 0, errors

    async def get_entries(
        self,
        action_filter: str | None = None,
        limit: int | None = None,
    ) -> list[AuditEntry]:
        """Get audit entries, optionally filtered."""
        if not self.log_file.exists():
            return []

        entries = []
        async with aiofiles.open(self.log_file) as f:
            async for line in f:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    entry = AuditEntry(**data)

                    if action_filter and not entry.action.startswith(action_filter):
                        continue

                    entries.append(entry)

                    if limit and len(entries) >= limit:
                        break

                except (json.JSONDecodeError, Exception):
                    continue

        return entries

    @property
    def entry_count(self) -> int:
        """Get the number of entries in the log."""
        return self._entry_count
