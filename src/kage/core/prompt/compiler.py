"""Prompt layer compiler runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from kage.core.observability import recorder_for_session

from .budget import TokenBudget, apply_budget_to_layers
from .context import CompiledPrompt, PromptContext, PromptLayerOutput
from .layers import (
    CommandLayer,
    PluginLayer,
    PolicyLayer,
    PromptLayer,
    RuntimeContextLayer,
    SessionMemoryLayer,
    SystemLayer,
)
from .middleware_registry import MiddlewareRegistry


@dataclass(slots=True)
class PromptCompiler:
    """Compiles modular prompt layers into provider-ready system prompt."""

    budget: TokenBudget = field(default_factory=TokenBudget)
    middleware: MiddlewareRegistry = field(default_factory=MiddlewareRegistry)
    _layers: list[PromptLayer] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self._layers:
            self._layers = [
                SystemLayer(priority=10),
                PolicyLayer(priority=20),
                CommandLayer(priority=30),
                SessionMemoryLayer(priority=40),
                PluginLayer(priority=50),
                RuntimeContextLayer(priority=60),
            ]

    def register_layer(self, layer: PromptLayer) -> None:
        """Register an additional layer."""
        self._layers.append(layer)

    def compile(self, context: PromptContext) -> CompiledPrompt:
        """Compile all enabled layers into a provider-ready prompt."""
        recorder = recorder_for_session(context.session, component="prompt_compiler")
        turn_id = int(context.metadata.get("turn_id", 0))
        injected = self.middleware.apply_before(context)
        if injected:
            recorder.record(
                event_type="middleware_modified_prompt",
                turn_id=turn_id,
                payload={"injected_layers": [layer.name for layer in injected]},
            )
        active_layers = [layer for layer in [*self._layers, *injected] if layer.enabled]
        active_layers.sort(key=lambda item: item.priority)

        rendered: list[PromptLayerOutput] = []
        for layer in active_layers:
            content = layer.content(context).strip()
            if not content:
                recorder.record(
                    event_type="layer_dropped",
                    turn_id=turn_id,
                    payload={"layer": layer.name, "reason": "empty_content"},
                )
                continue
            recorder.record(
                event_type="layer_applied",
                turn_id=turn_id,
                payload={"layer": layer.name, "priority": layer.priority},
            )
            rendered.append(
                PromptLayerOutput(
                    name=layer.name,
                    priority=layer.priority,
                    content=content,
                )
            )

        budgeted_layers, dropped_layers, token_count = apply_budget_to_layers(rendered, self.budget)
        for dropped in dropped_layers:
            recorder.record(
                event_type="layer_dropped",
                turn_id=turn_id,
                payload={"layer": dropped, "reason": "token_budget"},
            )
        system_prompt = "\n\n".join(layer.content for layer in budgeted_layers).strip()

        compiled = CompiledPrompt(
            system_prompt=system_prompt,
            layers=budgeted_layers,
            dropped_layers=dropped_layers,
            token_count_estimate=token_count,
        )
        final_compiled = self.middleware.apply_after(compiled, context=context)
        recorder.record(
            event_type="prompt_compiled",
            turn_id=turn_id,
            payload={
                "layer_count": len(final_compiled.layers),
                "dropped_layers": list(final_compiled.dropped_layers),
                "token_count_estimate": final_compiled.token_count_estimate,
            },
        )
        return final_compiled

