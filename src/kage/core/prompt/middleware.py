"""Middleware primitives for prompt compilation lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .context import CompiledPrompt, PromptContext
from .layers import PromptLayer


class PromptMiddleware(Protocol):
    """Prompt compiler middleware contract."""

    def before_compile(self, context: PromptContext) -> list[PromptLayer] | None:
        """Mutate context and optionally inject layers before compilation."""
        ...

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        """Rewrite compiled prompt after layer assembly and budgeting."""
        ...


@dataclass(slots=True)
class PromptMiddlewareManager:
    """Manages middleware registration and lifecycle invocation."""

    middlewares: list[PromptMiddleware] = field(default_factory=list)

    def register(self, middleware: PromptMiddleware) -> None:
        """Register middleware in execution order."""
        self.middlewares.append(middleware)

    def apply_before_compile(self, context: PromptContext) -> list[PromptLayer]:
        """Run before-compile stage and collect injected layers."""
        injected: list[PromptLayer] = []
        for middleware in self.middlewares:
            maybe_layers = middleware.before_compile(context)
            if maybe_layers:
                injected.extend(maybe_layers)
        return injected

    def apply_after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        """Run after-compile stage with prompt rewriting support."""
        result = compiled_prompt
        for middleware in self.middlewares:
            result = middleware.after_compile(result)
        return result

