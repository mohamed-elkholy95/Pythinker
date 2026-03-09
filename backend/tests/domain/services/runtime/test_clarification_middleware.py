"""Tests for ClarificationMiddleware and ClarificationRequest."""

from __future__ import annotations

import pytest

from app.domain.models.clarification import ClarificationRequest, ClarificationType
from app.domain.services.runtime.clarification_middleware import ClarificationMiddleware
from app.domain.services.runtime.middleware import RuntimeContext


def _make_ctx(**metadata) -> RuntimeContext:
    return RuntimeContext(session_id="s1", agent_id="a1", metadata=dict(metadata))


class TestClarificationMiddleware:
    @pytest.mark.asyncio
    async def test_no_pending_clarification_passes_through(self) -> None:
        """Context without a pending clarification is returned unchanged."""
        middleware = ClarificationMiddleware()
        ctx = _make_ctx()
        result = await middleware.before_step(ctx)

        assert result is ctx
        assert result.events == []
        assert "awaiting_clarification" not in result.metadata

    @pytest.mark.asyncio
    async def test_pending_clarification_emits_wait_event(self) -> None:
        """A pending ClarificationRequest produces exactly one event with correct fields."""
        request = ClarificationRequest(
            question="Which database should I use?",
            clarification_type=ClarificationType.APPROACH_CHOICE,
            context="PostgreSQL vs SQLite",
            options=["PostgreSQL", "SQLite"],
        )
        middleware = ClarificationMiddleware()
        ctx = _make_ctx(pending_clarification=request)
        result = await middleware.before_step(ctx)

        assert result.metadata.get("awaiting_clarification") is True
        assert "pending_clarification" not in result.metadata
        assert len(result.events) == 1

        event = result.events[0]
        assert event["type"] == "clarification"
        assert event["question"] == "Which database should I use?"
        assert event["clarification_type"] == ClarificationType.APPROACH_CHOICE.value
        assert event["context"] == "PostgreSQL vs SQLite"
        assert event["options"] == ["PostgreSQL", "SQLite"]
        assert "formatted" in event
        assert "[>]" in event["formatted"]

    @pytest.mark.asyncio
    async def test_all_clarification_types(self) -> None:
        """Every ClarificationType value is handled without error."""
        middleware = ClarificationMiddleware()

        for clarification_type in ClarificationType:
            request = ClarificationRequest(
                question=f"Question for {clarification_type.value}",
                clarification_type=clarification_type,
            )
            ctx = _make_ctx(pending_clarification=request)
            result = await middleware.before_step(ctx)

            assert result.metadata.get("awaiting_clarification") is True
            assert len(result.events) == 1
            assert result.events[0]["clarification_type"] == clarification_type.value

    @pytest.mark.asyncio
    async def test_clarification_request_format(self) -> None:
        """format() includes the icon prefix and a numbered options list."""
        request = ClarificationRequest(
            question="How should I proceed?",
            clarification_type=ClarificationType.MISSING_INFO,
            options=["Option A", "Option B", "Option C"],
        )
        formatted = request.format()

        assert formatted.startswith("[?]")
        assert "How should I proceed?" in formatted
        assert "1. Option A" in formatted
        assert "2. Option B" in formatted
        assert "3. Option C" in formatted

    @pytest.mark.asyncio
    async def test_format_with_context_prefix(self) -> None:
        """When context is provided, it appears on the icon line before the question."""
        request = ClarificationRequest(
            question="Confirm before deleting?",
            clarification_type=ClarificationType.RISK_CONFIRMATION,
            context="This action is irreversible",
        )
        formatted = request.format()

        lines = formatted.splitlines()
        assert "[!]" in lines[0]
        assert "This action is irreversible" in lines[0]
        assert "Confirm before deleting?" in lines[1]

    @pytest.mark.asyncio
    async def test_format_suggestion_no_options(self) -> None:
        """SUGGESTION type without options produces a single-line formatted string."""
        request = ClarificationRequest(
            question="Consider adding a retry mechanism.",
            clarification_type=ClarificationType.SUGGESTION,
        )
        formatted = request.format()

        assert formatted.startswith("[*]")
        assert "Consider adding a retry mechanism." in formatted
        assert "\n" not in formatted
