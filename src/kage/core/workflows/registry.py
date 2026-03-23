"""Registry for workflow templates with dependency validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kage.core.prompt import MiddlewareRegistry
from kage.core.tools import ToolRegistry

from .template import WorkflowTemplate


class WorkflowRegistryError(Exception):
    """Raised for workflow registry validation failures."""


@dataclass(slots=True)
class WorkflowRegistry:
    """In-memory registry of named workflow templates."""

    tool_registry: ToolRegistry
    middleware_registry: MiddlewareRegistry | None = None
    _templates: dict[str, WorkflowTemplate] = field(default_factory=dict, init=False, repr=False)

    def register(self, template: WorkflowTemplate) -> None:
        """Register or replace a template by name."""
        self._templates[template.name] = template

    def unregister(self, name: str) -> bool:
        """Remove one template by name."""
        return self._templates.pop(name, None) is not None

    def get(self, name: str) -> WorkflowTemplate | None:
        """Get one template by name."""
        return self._templates.get(name)

    def validate_dependencies(self, template: WorkflowTemplate) -> list[str]:
        """Validate required tools and middleware names for one template."""
        errors: list[str] = []

        for tool_name in template.required_tools:
            if self.tool_registry.get(tool_name) is None:
                errors.append(f"Missing required tool: {tool_name}")

        if template.required_middleware:
            if self.middleware_registry is None:
                errors.append("Middleware registry unavailable")
            else:
                available = {item.name for item in self.middleware_registry.list()}
                for middleware_name in template.required_middleware:
                    if middleware_name not in available:
                        errors.append(f"Missing required middleware: {middleware_name}")

        return errors

    def ensure_valid(self, template: WorkflowTemplate) -> None:
        """Raise when template dependency validation fails."""
        errors = self.validate_dependencies(template)
        if errors:
            raise WorkflowRegistryError("; ".join(errors))

    def resolve_middleware_requirements(
        self, template: WorkflowTemplate, *, parameters: dict[str, Any] | None = None
    ) -> list[str]:
        """Resolve middleware requirements for diagnostics/execution metadata."""
        _ = parameters or {}
        return list(template.required_middleware)

    def list(self) -> list[WorkflowTemplate]:
        """List templates in deterministic sorted order."""
        return [self._templates[name] for name in sorted(self._templates)]

