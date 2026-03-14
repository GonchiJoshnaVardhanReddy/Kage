"""Builtin runtime tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kage.core.tools.models import (
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolExecutorBinding,
    ToolExecutorKind,
    ToolPermissionMetadata,
    ToolSchema,
    ToolValidationError,
)
from kage.core.tools.registry import ToolRegistry


def _resolve_workspace_path(workspace_root: Path, user_path: str) -> Path:
    raw_path = Path(user_path).expanduser()
    candidate = (raw_path if raw_path.is_absolute() else workspace_root / raw_path).resolve()
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise ToolValidationError(f"Path outside workspace is blocked: {candidate}") from exc
    return candidate


def _exec_shell(_plan: ToolExecutionPlan, _context: dict[str, Any]) -> ToolExecutionResult:
    return ToolExecutionResult(
        success=True,
        data={"defer": "chat-command-pipeline"},
        metadata={"dispatch": "shell"},
    )


def _exec_fs_read(plan: ToolExecutionPlan, context: dict[str, Any]) -> ToolExecutionResult:
    workspace = context.get("workspace_root")
    if not isinstance(workspace, Path):
        raise ToolValidationError("workspace_root context is required for fs.read")
    path_value = plan.arguments.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ToolValidationError("fs.read requires string argument: path")

    file_path = _resolve_workspace_path(workspace, path_value)
    if not file_path.exists() or not file_path.is_file():
        raise ToolValidationError(f"File not found: {file_path}")

    content = file_path.read_text(encoding="utf-8", errors="replace")
    return ToolExecutionResult(
        success=True,
        output=content,
        data={"path": str(file_path), "content": content},
    )


def _exec_fs_write(plan: ToolExecutionPlan, context: dict[str, Any]) -> ToolExecutionResult:
    workspace = context.get("workspace_root")
    if not isinstance(workspace, Path):
        raise ToolValidationError("workspace_root context is required for fs.write")
    path_value = plan.arguments.get("path")
    content_value = plan.arguments.get("content")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ToolValidationError("fs.write requires string argument: path")
    if not isinstance(content_value, str):
        raise ToolValidationError("fs.write requires string argument: content")

    file_path = _resolve_workspace_path(workspace, path_value)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content_value, encoding="utf-8")
    return ToolExecutionResult(
        success=True,
        output=f"Wrote {len(content_value.encode('utf-8'))} bytes",
        data={"path": str(file_path), "bytes_written": len(content_value.encode('utf-8'))},
    )


def _exec_session_note(plan: ToolExecutionPlan, context: dict[str, Any]) -> ToolExecutionResult:
    text = plan.arguments.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ToolValidationError("session.note requires string argument: text")
    metadata = context.get("session_metadata")
    if not isinstance(metadata, dict):
        raise ToolValidationError("session_metadata context is required for session.note")

    notes = metadata.setdefault("notes", [])
    if not isinstance(notes, list):
        notes = []
        metadata["notes"] = notes
    notes.append(text.strip())
    if len(notes) > 100:
        del notes[:-100]

    return ToolExecutionResult(
        success=True,
        output="Session note added",
        data={"note_count": len(notes)},
    )


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register default builtin tools used by chat runtime."""
    schemas = [
        ToolSchema(
            name="builtin.shell.run",
            description="Run a shell command through Kage command pipeline",
            parameter_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            executor_binding=ToolExecutorBinding(kind=ToolExecutorKind.BUILTIN, route="local", executor=_exec_shell),
            permissions=ToolPermissionMetadata(
                dangerous=True,
                requires_approval=True,
                scopes=["shell", "execution"],
                tags=["builtin", "shell"],
            ),
        ),
        ToolSchema(
            name="builtin.fs.read",
            description="Read a file from workspace",
            parameter_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path relative to workspace"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            executor_binding=ToolExecutorBinding(kind=ToolExecutorKind.BUILTIN, route="local", executor=_exec_fs_read),
            permissions=ToolPermissionMetadata(
                dangerous=False,
                requires_approval=False,
                scopes=["filesystem", "read"],
                tags=["builtin", "fs"],
            ),
        ),
        ToolSchema(
            name="builtin.fs.write",
            description="Write file content in workspace",
            parameter_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to workspace"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            executor_binding=ToolExecutorBinding(
                kind=ToolExecutorKind.BUILTIN,
                route="local",
                executor=_exec_fs_write,
            ),
            permissions=ToolPermissionMetadata(
                dangerous=True,
                requires_approval=True,
                scopes=["filesystem", "write"],
                tags=["builtin", "fs"],
            ),
        ),
        ToolSchema(
            name="builtin.session.note",
            description="Add an operator note to active session metadata",
            parameter_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "Note text"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            executor_binding=ToolExecutorBinding(
                kind=ToolExecutorKind.BUILTIN,
                route="inmemory",
                executor=_exec_session_note,
            ),
            permissions=ToolPermissionMetadata(
                dangerous=False,
                requires_approval=False,
                scopes=["session"],
                tags=["builtin", "session"],
            ),
        ),
    ]
    for schema in schemas:
        registry.register(schema)

