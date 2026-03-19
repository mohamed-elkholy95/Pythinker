"""Tests for middleware data types."""

import pytest

from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)


class TestMiddlewareSignal:
    def test_signal_values(self):
        assert MiddlewareSignal.CONTINUE == "continue"
        assert MiddlewareSignal.SKIP_TOOL == "skip_tool"
        assert MiddlewareSignal.INJECT == "inject"
        assert MiddlewareSignal.FORCE == "force"
        assert MiddlewareSignal.ABORT == "abort"

    def test_signal_is_str_enum(self):
        assert isinstance(MiddlewareSignal.CONTINUE, str)


class TestMiddlewareContext:
    def test_default_construction(self):
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        assert ctx.agent_id == "a1"
        assert ctx.iteration_count == 0
        assert ctx.injected_messages == []
        assert ctx.emitted_events == []
        assert ctx.metadata == {}
        assert ctx.step_start_time == 0.0
        assert ctx.stuck_recovery_exhausted is False

    def test_mutable_fields(self):
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        ctx.iteration_count = 5
        ctx.stuck_recovery_exhausted = True
        assert ctx.iteration_count == 5
        assert ctx.stuck_recovery_exhausted is True


class TestToolCallInfo:
    def test_frozen(self):
        info = ToolCallInfo(call_id="c1", function_name="file_read", arguments={"path": "/tmp"})
        assert info.function_name == "file_read"
        with pytest.raises(AttributeError):
            info.function_name = "changed"  # type: ignore[misc]


class TestMiddlewareResult:
    def test_ok_factory(self):
        result = MiddlewareResult.ok()
        assert result.signal == MiddlewareSignal.CONTINUE
        assert result.message is None

    def test_frozen(self):
        result = MiddlewareResult(signal=MiddlewareSignal.FORCE, message="stop")
        with pytest.raises(AttributeError):
            result.signal = MiddlewareSignal.CONTINUE  # type: ignore[misc]

    def test_with_metadata(self):
        result = MiddlewareResult(
            signal=MiddlewareSignal.SKIP_TOOL,
            message="blocked",
            metadata={"reason": "security"},
        )
        assert result.metadata["reason"] == "security"
