"""Prompt middleware registry with deterministic priority execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from kage.core.observability import recorder_for_session

from .context import CompiledPrompt, PromptContext
from .layers import PromptLayer


class PromptMiddleware(Protocol):
    """Prompt middleware contract."""

    name: str
    priority: int

    def before_compile(self, context: PromptContext) -> list[PromptLayer] | None:
        """Mutate context and optionally inject layers before compilation."""
        ...

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        """Rewrite compiled prompt after layer assembly and budgeting."""
        ...


@dataclass(slots=True)
class ReconContextMiddleware:
    """Inject recon findings from workflow memory into prompt runtime context."""

    name: str = "recon_context_injector"
    priority: int = 30

    def before_compile(self, context: PromptContext) -> list[PromptLayer] | None:
        findings = context.workflow_memory.findings[-5:]
        if not findings:
            return None
        recon_lines = []
        for finding in findings:
            if isinstance(finding, dict):
                title = str(finding.get("title", "finding"))
                severity = str(finding.get("severity", "info"))
                recon_lines.append(f"{title} ({severity})")
            else:
                recon_lines.append(str(finding))
        if recon_lines:
            context.metadata["runtime_context"] = (
                f"{context.metadata.get('runtime_context', '').strip()} "
                f"Recon findings: {', '.join(recon_lines)}"
            ).strip()
        return None

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        return compiled_prompt


@dataclass(slots=True)
class MiddlewareRegistry:
    """Registry for prompt middlewares with deterministic lifecycle execution."""

    _middlewares: list[PromptMiddleware] = field(default_factory=list)
    _registration_index: int = 0
    _registration_order: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def _middleware_name(middleware: PromptMiddleware) -> str:
        value = getattr(middleware, "name", "")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return middleware.__class__.__name__

    @staticmethod
    def _middleware_priority(middleware: PromptMiddleware) -> int:
        value = getattr(middleware, "priority", 100)
        return value if isinstance(value, int) else 100

    def register(self, middleware: PromptMiddleware) -> None:
        """Register middleware and keep deterministic priority order."""
        name = self._middleware_name(middleware)
        self._middlewares = [item for item in self._middlewares if self._middleware_name(item) != name]
        self._registration_order[name] = self._registration_index
        self._registration_index += 1
        self._middlewares.append(middleware)
        self._middlewares.sort(
            key=lambda item: (
                self._middleware_priority(item),
                self._registration_order.get(self._middleware_name(item), 0),
            )
        )

    def unregister(self, middleware_name: str) -> bool:
        """Unregister middleware by name."""
        before = len(self._middlewares)
        self._middlewares = [
            item for item in self._middlewares if self._middleware_name(item) != middleware_name
        ]
        self._registration_order.pop(middleware_name, None)
        return len(self._middlewares) < before

    def apply_before(self, context: PromptContext) -> list[PromptLayer]:
        """Apply before-compile middlewares and collect injected layers."""
        recorder = recorder_for_session(context.session, component="prompt_middleware_registry")
        turn_id = int(context.metadata.get("turn_id", 0))
        injected: list[PromptLayer] = []
        for middleware in self._middlewares:
            middleware_name = self._middleware_name(middleware)
            before_snapshot = dict(context.metadata)
            maybe_layers = middleware.before_compile(context)
            recorder.record(
                event_type="middleware_applied",
                turn_id=turn_id,
                payload={"middleware": middleware_name, "phase": "before_compile"},
            )
            if maybe_layers:
                injected.extend(maybe_layers)
            if context.metadata != before_snapshot:
                recorder.record(
                    event_type="middleware_modified_context",
                    turn_id=turn_id,
                    payload={"middleware": middleware_name, "phase": "before_compile"},
                )
        return injected

    def apply_after(self, compiled_prompt: CompiledPrompt, *, context: PromptContext) -> CompiledPrompt:
        """Apply after-compile middlewares sequentially."""
        recorder = recorder_for_session(context.session, component="prompt_middleware_registry")
        turn_id = int(context.metadata.get("turn_id", 0))
        result = compiled_prompt
        for middleware in self._middlewares:
            middleware_name = self._middleware_name(middleware)
            before_prompt = result.system_prompt
            result = middleware.after_compile(result)
            recorder.record(
                event_type="middleware_applied",
                turn_id=turn_id,
                payload={"middleware": middleware_name, "phase": "after_compile"},
            )
            if result.system_prompt != before_prompt:
                recorder.record(
                    event_type="middleware_modified_prompt",
                    turn_id=turn_id,
                    payload={"middleware": middleware_name, "phase": "after_compile"},
                )
        return result

    def list(self) -> list[PromptMiddleware]:
        """List middlewares in execution order."""
        return list(self._middlewares)

