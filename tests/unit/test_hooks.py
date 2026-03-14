"""Unit tests for hook lifecycle manager."""

from __future__ import annotations

from kage.core.hooks import HookEvent, HookManager


class TestHookManager:
    async def test_dispatch_order_by_priority_then_registration(self) -> None:
        manager = HookManager()
        order: list[str] = []

        def low(_payload: dict) -> dict:
            order.append("low")
            return {"continue_pipeline": True}

        def high_a(_payload: dict) -> dict:
            order.append("high_a")
            return {"continue_pipeline": True}

        def high_b(_payload: dict) -> dict:
            order.append("high_b")
            return {"continue_pipeline": True}

        manager.register(event=HookEvent.PRE_LLM_CALL, callback=low, name="low", priority=50)
        manager.register(event=HookEvent.PRE_LLM_CALL, callback=high_a, name="high_a", priority=10)
        manager.register(event=HookEvent.PRE_LLM_CALL, callback=high_b, name="high_b", priority=10)

        result = await manager.dispatch(HookEvent.PRE_LLM_CALL, {"session_id": "s1"})

        assert result.continue_pipeline is True
        assert order == ["high_a", "high_b", "low"]

    async def test_fail_open_keeps_pipeline_running(self) -> None:
        manager = HookManager()

        def broken(_payload: dict) -> dict:
            raise RuntimeError("hook failed")

        def follower(payload: dict) -> dict:
            return {
                "continue_pipeline": True,
                "payload_updates": {"seen": payload.get("session_id", "")},
            }

        manager.register(
            event=HookEvent.USER_PROMPT_SUBMIT,
            callback=broken,
            name="broken",
            fail_open=True,
        )
        manager.register(
            event=HookEvent.USER_PROMPT_SUBMIT,
            callback=follower,
            name="follower",
        )

        result = await manager.dispatch(
            HookEvent.USER_PROMPT_SUBMIT,
            {"session_id": "s2", "user_input": "hello"},
        )

        assert result.continue_pipeline is True
        assert len(result.errors) == 1
        assert result.payload["seen"] == "s2"

    async def test_fail_closed_stops_pipeline(self) -> None:
        manager = HookManager()

        def broken(_payload: dict) -> dict:
            raise RuntimeError("hard fail")

        def never_called(payload: dict) -> dict:
            return {"payload_updates": {"after": payload.get("session_id", "")}}

        manager.register(
            event=HookEvent.PRE_COMMAND_RUN,
            callback=broken,
            name="broken_closed",
            fail_open=False,
        )
        manager.register(
            event=HookEvent.PRE_COMMAND_RUN,
            callback=never_called,
            name="never_called",
        )

        result = await manager.dispatch(
            HookEvent.PRE_COMMAND_RUN,
            {"session_id": "s3", "command": "echo ok"},
        )

        assert result.continue_pipeline is False
        assert result.stopped_by == "broken_closed"
        assert "after" not in result.payload

    async def test_payload_merging_across_hooks(self) -> None:
        manager = HookManager()

        async def add_context(payload: dict) -> dict:
            return {
                "continue_pipeline": True,
                "payload_updates": {
                    "additional_context": f"context:{payload.get('user_input', '')}"
                },
            }

        def override_input(_payload: dict) -> dict:
            return {
                "continue_pipeline": True,
                "payload_updates": {"user_input": "rewritten input"},
            }

        manager.register(event=HookEvent.PRE_LLM_CALL, callback=add_context, name="add_context")
        manager.register(event=HookEvent.PRE_LLM_CALL, callback=override_input, name="override")

        result = await manager.dispatch(
            HookEvent.PRE_LLM_CALL,
            {"session_id": "s4", "user_input": "original input"},
        )

        assert result.continue_pipeline is True
        assert result.payload["user_input"] == "rewritten input"
        assert result.payload["additional_context"] == "context:original input"

