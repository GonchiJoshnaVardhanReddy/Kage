"""Plugin middleware auto-registration helpers."""

from __future__ import annotations

from kage.core.observability import recorder_for_session
from kage.core.prompt.middleware_registry import MiddlewareRegistry, ReconContextMiddleware
from kage.plugins.schema import PluginSchema


def register_plugin_middlewares(
    *,
    schema: PluginSchema,
    registry: MiddlewareRegistry,
    session: object | None = None,
    turn_id: int = 0,
) -> list[str]:
    """Auto-register supported prompt middlewares declared by plugin schema."""
    registered: list[str] = []
    for middleware_name in schema.middleware:
        normalized = middleware_name.strip().lower()
        if normalized == "recon_context_injector":
            registry.register(ReconContextMiddleware())
            registered.append(normalized)
        else:
            continue
        if session is not None:
            recorder = recorder_for_session(session, component="prompt_middleware_registry")
            recorder.record(
                event_type="middleware_registered",
                turn_id=turn_id,
                payload={"middleware": normalized, "plugin": schema.name},
            )
    return registered

