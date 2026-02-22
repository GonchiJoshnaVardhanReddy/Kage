"""Session persistence for Kage."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from kage.core.models import Session
from kage.persistence.config import get_data_dir


class SessionStorage:
    """Handles session persistence to filesystem."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or get_data_dir() / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.storage_dir / f"{session_id}.json"

    def _get_index_path(self) -> Path:
        """Get the session index file path."""
        return self.storage_dir / "index.json"

    async def save(self, session: Session) -> Path:
        """Save a session to disk."""
        session.updated_at = datetime.utcnow()
        path = self._get_session_path(session.id)

        # Serialize session
        data = session.model_dump(mode="json")

        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, indent=2, default=str))

        # Update index
        await self._update_index(session)

        return path

    async def load(self, session_id: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(session_id)

        if not path.exists():
            return None

        try:
            async with aiofiles.open(path) as f:
                data = json.loads(await f.read())
            return Session(**data)
        except Exception:
            return None

    async def delete(self, session_id: str) -> bool:
        """Delete a session from disk."""
        path = self._get_session_path(session_id)

        if not path.exists():
            return False

        try:
            os.remove(path)
            await self._remove_from_index(session_id)
            return True
        except Exception:
            return False

    async def list_sessions(
        self,
        limit: int | None = None,
        sort_by: str = "updated_at",
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        """List all sessions with metadata."""
        index_path = self._get_index_path()

        if not index_path.exists():
            return []

        try:
            async with aiofiles.open(index_path) as f:
                index = json.loads(await f.read())

            sessions = list(index.get("sessions", {}).values())

            # Sort
            sessions.sort(
                key=lambda s: s.get(sort_by, ""),
                reverse=descending,
            )

            # Limit
            if limit:
                sessions = sessions[:limit]

            return sessions

        except Exception:
            return []

    async def _update_index(self, session: Session) -> None:
        """Update the session index."""
        index_path = self._get_index_path()

        # Load existing index
        index = {"sessions": {}}
        if index_path.exists():
            try:
                async with aiofiles.open(index_path) as f:
                    index = json.loads(await f.read())
            except Exception:
                pass

        # Update entry
        scope_summary = ""
        if session.scope.targets:
            targets = [t.value for t in session.scope.targets[:3]]
            scope_summary = ", ".join(targets)
            if len(session.scope.targets) > 3:
                scope_summary += f" (+{len(session.scope.targets) - 3} more)"

        index["sessions"][session.id] = {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "scope_summary": scope_summary,
            "message_count": len(session.messages),
            "command_count": len(session.commands),
            "finding_count": len(session.findings),
        }

        # Save index
        async with aiofiles.open(index_path, "w") as f:
            await f.write(json.dumps(index, indent=2))

    async def _remove_from_index(self, session_id: str) -> None:
        """Remove a session from the index."""
        index_path = self._get_index_path()

        if not index_path.exists():
            return

        try:
            async with aiofiles.open(index_path) as f:
                index = json.loads(await f.read())

            if session_id in index.get("sessions", {}):
                del index["sessions"][session_id]

            async with aiofiles.open(index_path, "w") as f:
                await f.write(json.dumps(index, indent=2))

        except Exception:
            pass

    def get_session_file(self, session_id: str) -> Path | None:
        """Get the path to a session file if it exists."""
        path = self._get_session_path(session_id)
        return path if path.exists() else None

    async def export_session(
        self,
        session_id: str,
        output_path: Path,
        format: str = "json",
    ) -> bool:
        """Export a session to a file."""
        session = await self.load(session_id)
        if not session:
            return False

        try:
            if format == "json":
                data = session.model_dump(mode="json")
                async with aiofiles.open(output_path, "w") as f:
                    await f.write(json.dumps(data, indent=2, default=str))

            elif format == "markdown":
                md_content = self._session_to_markdown(session)
                async with aiofiles.open(output_path, "w") as f:
                    await f.write(md_content)

            return True

        except Exception:
            return False

    def _session_to_markdown(self, session: Session) -> str:
        """Convert session to markdown format."""
        lines = [
            f"# Session: {session.id[:8]}",
            "",
            f"**Created:** {session.created_at.isoformat()}",
            f"**Updated:** {session.updated_at.isoformat()}",
            f"**Safe Mode:** {'Enabled' if session.safe_mode else 'Disabled'}",
            "",
        ]

        # Scope
        if session.scope.targets:
            lines.append("## Scope")
            lines.append("")
            for target in session.scope.targets:
                lines.append(f"- {target.target_type}: `{target.value}`")
            lines.append("")

        # Commands
        if session.commands:
            lines.append("## Commands Executed")
            lines.append("")
            for cmd in session.commands:
                status_emoji = "✅" if cmd.status.value == "completed" else "❌"
                lines.append(f"### {status_emoji} `{cmd.command}`")
                lines.append("")
                lines.append(f"- **Status:** {cmd.status.value}")
                if cmd.exit_code is not None:
                    lines.append(f"- **Exit Code:** {cmd.exit_code}")
                if cmd.stdout:
                    lines.append("")
                    lines.append("**Output:**")
                    lines.append("```")
                    lines.append(cmd.stdout[:1000])
                    lines.append("```")
                lines.append("")

        # Findings
        if session.findings:
            lines.append("## Findings")
            lines.append("")
            for finding in session.findings:
                severity_map = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🔵",
                    "info": "⚪",
                }
                emoji = severity_map.get(finding.severity.value, "⚪")
                lines.append(f"### {emoji} {finding.title}")
                lines.append("")
                lines.append(f"**Severity:** {finding.severity.value.upper()}")
                if finding.cvss_score:
                    lines.append(f"**CVSS:** {finding.cvss_score}")
                lines.append("")
                lines.append(finding.description)
                lines.append("")

        return "\n".join(lines)


class AutoSaveSession:
    """Context manager for auto-saving sessions."""

    def __init__(
        self,
        session: Session,
        storage: SessionStorage,
        save_interval: int = 60,
    ) -> None:
        self.session = session
        self.storage = storage
        self.save_interval = save_interval
        self._last_save = datetime.utcnow()
        self._dirty = False

    def mark_dirty(self) -> None:
        """Mark session as having unsaved changes."""
        self._dirty = True

    async def maybe_save(self) -> bool:
        """Save if dirty and enough time has passed."""
        if not self._dirty:
            return False

        now = datetime.utcnow()
        elapsed = (now - self._last_save).total_seconds()

        if elapsed >= self.save_interval:
            await self.storage.save(self.session)
            self._last_save = now
            self._dirty = False
            return True

        return False

    async def force_save(self) -> Path:
        """Force immediate save."""
        path = await self.storage.save(self.session)
        self._last_save = datetime.utcnow()
        self._dirty = False
        return path
