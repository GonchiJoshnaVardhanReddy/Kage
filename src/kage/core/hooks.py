"""Hook lifecycle primitives for runtime event interception."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypedDict, cast

from kage.core.observability import (
    TraceEvent,
    TraceSeverity,
    queue_event_for_session,
    recorder_for_session_id,
)
from kage.utils import utcnow


class HookEvent(str, Enum):
    """Supported runtime hook events."""

    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_LLM_CALL = "PreLLMCall"
    POST_LLM_CALL = "PostLLMCall"
    PRE_COMMAND_RUN = "PreCommandRun"
    POST_COMMAND_RUN = "PostCommandRun"
    PRE_FILE_WRITE = "PreFileWrite"
    POST_FILE_WRITE = "PostFileWrite"
    STOP = "Stop"
    POST_TURN_PERSIST = "PostTurnPersist"


class HookBasePayload(TypedDict, total=False):
    """Shared hook payload fields."""

    event: str
    session_id: str
    turn_id: int
    timestamp: str
    metadata: dict[str, Any]
    extensions: dict[str, Any]


class SessionStartPayload(HookBasePayload, total=False):
    provider: str
    model: str
    safe_mode: bool
    scope_targets: list[str]


class UserPromptSubmitPayload(HookBasePayload, total=False):
    user_input: str


class PreLLMCallPayload(HookBasePayload, total=False):
    user_input: str
    intent: str
    safe_mode: bool
    scope_targets: list[str]
    additional_context: str


class PostLLMCallPayload(HookBasePayload, total=False):
    user_input: str
    response_text: str
    suggested_commands: list[str]
    suggested_count: int


class PreCommandRunPayload(HookBasePayload, total=False):
    command: str
    description: str
    route_tool: str
    route_reasoning: str
    phase: str
    step_index: int
    total_steps: int


class PostCommandRunPayload(HookBasePayload, total=False):
    command: str
    route_tool: str
    status: str
    exit_code: int
    timed_out: bool
    duration_s: float
    stdout_chars: int
    stderr_chars: int


class PreFileWritePayload(HookBasePayload, total=False):
    path: str
    action: str
    content: str
    byte_count: int


class PostFileWritePayload(HookBasePayload, total=False):
    path: str
    action: str
    bytes_written: int


class StopPayload(HookBasePayload, total=False):
    reason: str
    message_count: int
    command_count: int


class PostTurnPersistPayload(HookBasePayload, total=False):
    user_input: str
    llm_called: bool
    suggested_count: int
    message_count: int
    command_count: int


HookPayload = (
    HookBasePayload
    | SessionStartPayload
    | UserPromptSubmitPayload
    | PreLLMCallPayload
    | PostLLMCallPayload
    | PreCommandRunPayload
    | PostCommandRunPayload
    | PreFileWritePayload
    | PostFileWritePayload
    | StopPayload
    | PostTurnPersistPayload
)


EVENT_PAYLOAD_FIELDS: dict[HookEvent, set[str]] = {
    HookEvent.SESSION_START: {"provider", "model", "safe_mode", "scope_targets"},
    HookEvent.USER_PROMPT_SUBMIT: {"user_input"},
    HookEvent.PRE_LLM_CALL: {"user_input", "intent", "safe_mode", "scope_targets"},
    HookEvent.POST_LLM_CALL: {"user_input", "response_text", "suggested_commands", "suggested_count"},
    HookEvent.PRE_COMMAND_RUN: {
        "command",
        "description",
        "route_tool",
        "route_reasoning",
        "phase",
        "step_index",
        "total_steps",
    },
    HookEvent.POST_COMMAND_RUN: {
        "command",
        "route_tool",
        "status",
        "exit_code",
        "timed_out",
        "duration_s",
        "stdout_chars",
        "stderr_chars",
    },
    HookEvent.PRE_FILE_WRITE: {"path", "action", "content", "byte_count"},
    HookEvent.POST_FILE_WRITE: {"path", "action", "bytes_written"},
    HookEvent.STOP: {"reason", "message_count", "command_count"},
    HookEvent.POST_TURN_PERSIST: {
        "user_input",
        "llm_called",
        "suggested_count",
        "message_count",
        "command_count",
    },
}


class HookResult(TypedDict, total=False):
    """Structured result returned by a hook callback."""

    continue_pipeline: bool
    payload_updates: dict[str, Any]
    warnings: list[str]


HookCallback = Callable[[HookPayload], HookResult | None | Awaitable[HookResult | None]]
ContextProvider = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class HookRegistration:
    """Registered hook metadata."""

    name: str
    event: HookEvent
    callback: HookCallback
    priority: int = 100
    fail_open: bool = True
    timeout_s: float = 1.0
    enabled: bool = True
    _order: int = field(default=0, repr=False)


@dataclass(slots=True)
class HookDispatchResult:
    """Aggregated result for an event dispatch call."""

    event: HookEvent
    continue_pipeline: bool
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stopped_by: str | None = None
    dispatched_at: datetime = field(default_factory=utcnow)


class HookManager:
    """Framework-agnostic runtime hook manager with async-native dispatch."""

    def __init__(self) -> None:
        self._hooks: dict[HookEvent, list[HookRegistration]] = {event: [] for event in HookEvent}
        self._order_counter = 0
        self._context_providers: dict[str, ContextProvider] = {}

    def register(
        self,
        *,
        event: HookEvent,
        callback: HookCallback,
        name: str | None = None,
        priority: int = 100,
        fail_open: bool = True,
        timeout_s: float = 1.0,
        enabled: bool = True,
    ) -> HookRegistration:
        """Register a callback for an event."""
        self._order_counter += 1
        hook_name = name if name is not None else str(getattr(callback, "__name__", "anonymous_hook"))
        registration = HookRegistration(
            name=hook_name,
            event=event,
            callback=callback,
            priority=priority,
            fail_open=fail_open,
            timeout_s=timeout_s,
            enabled=enabled,
            _order=self._order_counter,
        )
        hooks = self._hooks[event]
        hooks.append(registration)
        hooks.sort(key=lambda item: (item.priority, item._order))
        return registration

    def on(
        self,
        event: HookEvent,
        *,
        name: str | None = None,
        priority: int = 100,
        fail_open: bool = True,
        timeout_s: float = 1.0,
        enabled: bool = True,
    ) -> Callable[[HookCallback], HookCallback]:
        """Decorator-based hook registration."""

        def decorator(callback: HookCallback) -> HookCallback:
            self.register(
                event=event,
                callback=callback,
                name=name,
                priority=priority,
                fail_open=fail_open,
                timeout_s=timeout_s,
                enabled=enabled,
            )
            return callback

        return decorator

    def register_context_provider(self, name: str, provider: ContextProvider) -> None:
        """Register a context provider for extension payloads.

        Providers are merged under payload["extensions"][name], enabling future
        ToolRegistry, plugin, agent, and MCP middleware context injection.
        """
        self._context_providers[name] = provider

    def unregister(
        self,
        *,
        event: HookEvent,
        name: str,
    ) -> bool:
        """Unregister a hook by event and name."""
        hooks = self._hooks[event]
        before = len(hooks)
        self._hooks[event] = [hook for hook in hooks if hook.name != name]
        return len(self._hooks[event]) < before

    def clear(self, event: HookEvent | None = None) -> None:
        """Clear all hooks for one event or the full registry."""
        if event is None:
            self._hooks = {evt: [] for evt in HookEvent}
            return
        self._hooks[event] = []

    def list_hooks(self, event: HookEvent | None = None) -> list[HookRegistration]:
        """Return registered hooks in effective dispatch order."""
        if event is None:
            hooks: list[HookRegistration] = []
            for evt in HookEvent:
                hooks.extend(self._hooks[evt])
            return hooks
        return list(self._hooks[event])

    @staticmethod
    def payload_schema(event: HookEvent) -> set[str]:
        """Return allowed event-specific payload fields."""
        return EVENT_PAYLOAD_FIELDS.get(event, set()).copy()

    async def dispatch(
        self,
        event: HookEvent,
        payload: HookPayload,
    ) -> HookDispatchResult:
        """Dispatch an event to registered hooks."""
        merged_payload = dict(payload)
        merged_payload.setdefault("event", event.value)
        merged_payload.setdefault("timestamp", utcnow().isoformat())
        merged_payload.setdefault("extensions", {})
        extensions = merged_payload["extensions"]
        if isinstance(extensions, dict):
            provider_ctx = await self._resolve_context_provider_payloads()
            for key, value in provider_ctx.items():
                extensions.setdefault(key, value)

        result = HookDispatchResult(
            event=event,
            continue_pipeline=True,
            payload=merged_payload,
        )

        for hook in self._hooks[event]:
            if not hook.enabled:
                continue
            session_id = merged_payload.get("session_id")
            raw_turn_id = merged_payload.get("turn_id", 0)
            if isinstance(raw_turn_id, int):
                turn_id = raw_turn_id
            elif isinstance(raw_turn_id, str) and raw_turn_id.isdigit():
                turn_id = int(raw_turn_id)
            else:
                turn_id = 0
            if isinstance(session_id, str):
                hook_recorder = recorder_for_session_id(session_id, component="hook_manager")
                if hook_recorder is not None:
                    hook_recorder.record(
                        event_type="hook_triggered",
                        turn_id=turn_id,
                        payload={"hook": hook.name, "event": event.value},
                    )
                else:
                    queue_event_for_session(
                        TraceEvent(
                            event_type="hook_triggered",
                            session_id=session_id,
                            turn_id=turn_id,
                            component="hook_manager",
                            payload={"hook": hook.name, "event": event.value},
                        )
                    )

            try:
                hook_result = await self._call_hook(hook, cast(HookPayload, merged_payload))
                if not hook_result:
                    continue

                warnings = hook_result.get("warnings", [])
                if warnings:
                    result.warnings.extend(warnings)

                updates = hook_result.get("payload_updates", {})
                if updates:
                    merged_payload.update(updates)
                    result.payload = merged_payload
                    if isinstance(session_id, str):
                        hook_recorder = recorder_for_session_id(session_id, component="hook_manager")
                        if hook_recorder is not None:
                            hook_recorder.record(
                                event_type="hook_modified_payload",
                                turn_id=turn_id,
                                payload={
                                    "hook": hook.name,
                                    "event": event.value,
                                    "updated_keys": sorted(updates.keys()),
                                },
                            )
                        else:
                            queue_event_for_session(
                                TraceEvent(
                                    event_type="hook_modified_payload",
                                    session_id=session_id,
                                    turn_id=turn_id,
                                    component="hook_manager",
                                    payload={
                                        "hook": hook.name,
                                        "event": event.value,
                                        "updated_keys": sorted(updates.keys()),
                                    },
                                )
                            )

                should_continue = hook_result.get("continue_pipeline", True)
                if not should_continue:
                    result.continue_pipeline = False
                    result.stopped_by = hook.name
                    if isinstance(session_id, str):
                        hook_recorder = recorder_for_session_id(session_id, component="hook_manager")
                        if hook_recorder is not None:
                            hook_recorder.record(
                                event_type="hook_blocked_execution",
                                turn_id=turn_id,
                                severity=TraceSeverity.WARNING,
                                payload={"hook": hook.name, "event": event.value},
                            )
                            hook_recorder.record(
                                event_type="policy_decision",
                                turn_id=turn_id,
                                severity=TraceSeverity.WARNING,
                                payload={
                                    "decision": "blocked",
                                    "source": "hook",
                                    "hook": hook.name,
                                    "event": event.value,
                                },
                            )
                        else:
                            queue_event_for_session(
                                TraceEvent(
                                    event_type="hook_blocked_execution",
                                    session_id=session_id,
                                    turn_id=turn_id,
                                    component="hook_manager",
                                    severity=TraceSeverity.WARNING,
                                    payload={"hook": hook.name, "event": event.value},
                                )
                            )
                            queue_event_for_session(
                                TraceEvent(
                                    event_type="policy_decision",
                                    session_id=session_id,
                                    turn_id=turn_id,
                                    component="hook_manager",
                                    severity=TraceSeverity.WARNING,
                                    payload={
                                        "decision": "blocked",
                                        "source": "hook",
                                        "hook": hook.name,
                                        "event": event.value,
                                    },
                                )
                            )
                    break

            except Exception as exc:
                result.errors.append(f"{hook.name}: {exc}")
                if not hook.fail_open:
                    result.continue_pipeline = False
                    result.stopped_by = hook.name
                    if isinstance(session_id, str):
                        hook_recorder = recorder_for_session_id(session_id, component="hook_manager")
                        if hook_recorder is not None:
                            hook_recorder.record(
                                event_type="policy_decision",
                                turn_id=turn_id,
                                severity=TraceSeverity.ERROR,
                                payload={
                                    "decision": "blocked",
                                    "source": "hook_error",
                                    "hook": hook.name,
                                    "event": event.value,
                                    "error": str(exc),
                                },
                            )
                        else:
                            queue_event_for_session(
                                TraceEvent(
                                    event_type="policy_decision",
                                    session_id=session_id,
                                    turn_id=turn_id,
                                    component="hook_manager",
                                    severity=TraceSeverity.ERROR,
                                    payload={
                                        "decision": "blocked",
                                        "source": "hook_error",
                                        "hook": hook.name,
                                        "event": event.value,
                                        "error": str(exc),
                                    },
                                )
                            )
                    break

        return result

    async def _call_hook(
        self,
        hook: HookRegistration,
        payload: HookPayload,
    ) -> HookResult | None:
        callback_result = hook.callback(payload)
        if inspect.isawaitable(callback_result):
            resolved = await asyncio.wait_for(callback_result, timeout=hook.timeout_s)
            return resolved
        return callback_result

    async def _resolve_context_provider_payloads(self) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for name, provider in self._context_providers.items():
            provided = provider()
            if inspect.isawaitable(provided):
                provided = await provided
            resolved[name] = provided
        return resolved

