"""Workflow template loader from builtins, plugins, and user config directories."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kage.core.observability import recorder_for_session

from .registry import WorkflowRegistry
from .schema import WorkflowTemplateSchema
from .template import WorkflowTemplate

if TYPE_CHECKING:
    from kage.plugins.schema import PluginSchema


_DEFAULT_BUILTIN_WORKFLOW = """\
name: builtin_recon
description: Builtin reconnaissance workflow template
required_tools:
  - builtin.session.note
default_parameters:
  planned_command: echo builtin-recon
pipeline:
  - PlannerAgent
  - parallel:
      - ReconAgent
      - EnumAgent
  - ReporterAgent
"""


def ensure_builtin_workflow_templates(directory: Path) -> list[Path]:
    """Ensure built-in workflow templates exist and return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "builtin_recon.yaml"
    if not target.exists():
        target.write_text(_DEFAULT_BUILTIN_WORKFLOW, encoding="utf-8")
    return [target]


class WorkflowLoaderError(Exception):
    """Raised when workflow templates cannot be loaded."""


class WorkflowLoader:
    """Loads workflow templates from declarative YAML definitions."""

    def __init__(
        self,
        *,
        builtin_dir: Path | None = None,
        plugin_dirs: list[Path] | None = None,
        user_dir: Path | None = None,
    ) -> None:
        self.builtin_dir = builtin_dir
        self.plugin_dirs = plugin_dirs or []
        self.user_dir = user_dir

    def _iter_workflow_files(self) -> list[tuple[Path, str]]:
        files: list[tuple[Path, str]] = []
        if self.builtin_dir and self.builtin_dir.exists():
            for candidate in sorted(self.builtin_dir.glob("*.yaml")):
                files.append((candidate, "builtins"))
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
            for candidate in sorted((plugin_dir / "workflows").glob("*.yaml")):
                files.append((candidate, "plugins"))
        if self.user_dir and self.user_dir.exists():
            for candidate in sorted(self.user_dir.glob("*.yaml")):
                files.append((candidate, "user"))
        return files

    def load_all(self) -> list[WorkflowTemplate]:
        """Load all templates from configured directories."""
        templates: list[WorkflowTemplate] = []
        for path, _source in self._iter_workflow_files():
            schema = WorkflowTemplateSchema.from_yaml(path)
            templates.append(WorkflowTemplate.from_schema(schema, source=str(path)))
        return templates

    def load(self, name: str) -> WorkflowTemplate:
        """Load one template by name."""
        for template in self.load_all():
            if template.name == name:
                return template
        raise WorkflowLoaderError(f"Workflow template not found: {name}")

    def load_from_file(self, path: Path) -> WorkflowTemplate:
        """Load one template directly from a YAML file path."""
        if not path.exists():
            raise WorkflowLoaderError(f"Workflow file not found: {path}")
        schema = WorkflowTemplateSchema.from_yaml(path)
        return WorkflowTemplate.from_schema(schema, source=str(path))


def register_plugin_workflows(
    *,
    schema: PluginSchema,
    plugin_dir: Path,
    registry: WorkflowRegistry,
    session: object | None = None,
    turn_id: int = 0,
) -> list[str]:
    """Load and register workflow templates declared by a plugin manifest."""
    registered: list[str] = []
    for workflow_file in schema.workflows:
        relative = workflow_file.strip()
        if not relative:
            continue
        path = (plugin_dir / relative).resolve()
        template = WorkflowLoader().load_from_file(path)
        registry.register(template)
        registered.append(template.name)
        if session is not None:
            recorder = recorder_for_session(session, component="workflow_loader")
            recorder.record(
                event_type="workflow_loaded",
                turn_id=turn_id,
                payload={"workflow_name": template.name, "source": str(path), "plugin": schema.name},
            )
    return registered

