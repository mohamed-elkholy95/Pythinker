"""Contract tests for ToolInterceptor extension types.

Verifies that ToolCallContext and ToolInterceptorResult behave correctly from
the interceptor consumer's perspective.  The types themselves are defined in
app.domain.models.evidence and tested more exhaustively in test_evidence.py.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.domain.models.evidence import ToolCallContext, ToolInterceptorResult


class TestToolCallContext:
    """ToolCallContext — immutable context snapshot for one tool call."""

    def test_all_fields(self) -> None:
        ctx = ToolCallContext(
            tool_call_id="call-123",
            function_name="info_search_web",
            function_args={"query": "python asyncio"},
            step_id="step-1",
            session_id="session-abc",
            research_mode="deep",
        )
        assert ctx.tool_call_id == "call-123"
        assert ctx.function_name == "info_search_web"
        assert ctx.function_args == {"query": "python asyncio"}
        assert ctx.step_id == "step-1"
        assert ctx.session_id == "session-abc"
        assert ctx.research_mode == "deep"

    def test_optional_fields_accept_none(self) -> None:
        ctx = ToolCallContext(
            tool_call_id="call-456",
            function_name="browser_navigate",
            function_args={},
            step_id=None,
            session_id="session-xyz",
            research_mode=None,
        )
        assert ctx.step_id is None
        assert ctx.research_mode is None

    def test_frozen(self) -> None:
        """ToolCallContext must be immutable (frozen=True dataclass)."""
        ctx = ToolCallContext(
            tool_call_id="c1",
            function_name="fn",
            function_args={},
            step_id=None,
            session_id="s1",
            research_mode=None,
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            ctx.tool_call_id = "mutated"  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(ToolCallContext)


class TestToolInterceptorResult:
    """ToolInterceptorResult — mutable result from a ToolInterceptor."""

    def test_defaults(self) -> None:
        result = ToolInterceptorResult()
        assert result.override_memory_content is None
        assert result.extra_messages is None
        assert result.suppress_memory_content is False

    def test_override_content(self) -> None:
        result = ToolInterceptorResult(override_memory_content="enriched content")
        assert result.override_memory_content == "enriched content"
        assert not result.suppress_memory_content

    def test_suppress(self) -> None:
        result = ToolInterceptorResult(suppress_memory_content=True)
        assert result.suppress_memory_content is True
        assert result.override_memory_content is None

    def test_extra_messages(self) -> None:
        msgs = [{"role": "user", "content": "Enriched context"}]
        result = ToolInterceptorResult(extra_messages=msgs)
        assert result.extra_messages == msgs

    def test_mutable(self) -> None:
        """ToolInterceptorResult must be mutable (not frozen)."""
        result = ToolInterceptorResult()
        result.override_memory_content = "updated"
        assert result.override_memory_content == "updated"

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(ToolInterceptorResult)

    def test_all_fields_set(self) -> None:
        msgs = [{"role": "system", "content": "extra"}]
        result = ToolInterceptorResult(
            override_memory_content="new content",
            extra_messages=msgs,
            suppress_memory_content=False,
        )
        assert result.override_memory_content == "new content"
        assert result.extra_messages is msgs
        assert result.suppress_memory_content is False
