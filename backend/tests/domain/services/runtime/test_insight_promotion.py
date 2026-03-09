"""Tests for InsightPromotionMiddleware — ContextGraph → Qdrant promotion logic."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.services.agents.context_manager import InsightType, StepInsight
from app.domain.services.runtime.insight_promotion_middleware import (
    InsightPromotionMiddleware,
)
from app.domain.services.runtime.middleware import RuntimeContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    session_id: str = "sess-test",
    user_id: str = "user-42",
    insights: list[StepInsight] | None = None,
) -> RuntimeContext:
    ctx = RuntimeContext(session_id=session_id, agent_id="agent-test")
    ctx.metadata["user_id"] = user_id
    if insights is not None:
        ctx.metadata["new_insights"] = insights
    return ctx


def _make_insight(
    insight_type: InsightType,
    confidence: float,
    content: str = "test insight content",
    step_id: str = "step-1",
) -> StepInsight:
    return StepInsight(
        step_id=step_id,
        insight_type=insight_type,
        content=content,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_confidence_insight_promoted() -> None:
    """A DISCOVERY insight with confidence >= threshold is promoted to memory."""
    memory_service = AsyncMock()
    middleware = InsightPromotionMiddleware(memory_service, confidence_threshold=0.85)

    insight = _make_insight(InsightType.DISCOVERY, confidence=0.95)
    ctx = _make_ctx(insights=[insight])

    result = await middleware.after_step(ctx)

    memory_service.store_memory.assert_awaited_once()
    call_kwargs = memory_service.store_memory.call_args.kwargs
    assert call_kwargs["user_id"] == "user-42"
    assert call_kwargs["content"] == insight.content
    assert call_kwargs["memory_type"] == "FACT"
    assert call_kwargs["importance"] == 0.95
    assert InsightType.DISCOVERY.value in call_kwargs["tags"]
    assert call_kwargs["session_id"] == "sess-test"
    assert call_kwargs["generate_embedding"] is True

    # new_insights is removed from metadata after processing.
    assert "new_insights" not in result.metadata


@pytest.mark.asyncio
async def test_low_confidence_insight_not_promoted() -> None:
    """An ASSUMPTION insight below threshold is NOT promoted."""
    memory_service = AsyncMock()
    middleware = InsightPromotionMiddleware(memory_service, confidence_threshold=0.85)

    insight = _make_insight(InsightType.ASSUMPTION, confidence=0.5)
    ctx = _make_ctx(insights=[insight])

    await middleware.after_step(ctx)

    memory_service.store_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_error_learning_always_promoted() -> None:
    """ERROR_LEARNING is always promoted even when confidence is below threshold."""
    memory_service = AsyncMock()
    middleware = InsightPromotionMiddleware(memory_service, confidence_threshold=0.85)

    # confidence=0.7 is well below the 0.85 threshold.
    insight = _make_insight(InsightType.ERROR_LEARNING, confidence=0.7)
    ctx = _make_ctx(insights=[insight])

    await middleware.after_step(ctx)

    memory_service.store_memory.assert_awaited_once()
    call_kwargs = memory_service.store_memory.call_args.kwargs
    assert call_kwargs["memory_type"] == "EXPERIENCE"
    assert call_kwargs["importance"] == 0.7


@pytest.mark.asyncio
async def test_no_insights_no_action() -> None:
    """When new_insights is absent from metadata, store_memory is never called."""
    memory_service = AsyncMock()
    middleware = InsightPromotionMiddleware(memory_service, confidence_threshold=0.85)

    # No "new_insights" key in metadata at all.
    ctx = RuntimeContext(session_id="sess-empty", agent_id="agent-test")
    ctx.metadata["user_id"] = "user-99"

    await middleware.after_step(ctx)

    memory_service.store_memory.assert_not_awaited()
