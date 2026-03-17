"""Insight promotion middleware — ContextGraph → Qdrant long-term memory.

After each step, high-confidence StepInsights are promoted from the ephemeral
ContextGraph (held in ``ctx.metadata["new_insights"]``) to the Qdrant-backed
long-term memory store via ``memory_service.store_memory()``.

Promotion rules:
- Insights with ``insight_type`` in ``_ALWAYS_PROMOTE`` are stored regardless of
  confidence (ERROR_LEARNING and BLOCKER are always valuable long-term signals).
- All other insights are promoted only when ``confidence >= confidence_threshold``
  (default 0.85).
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.services.agents.context_manager import InsightType, StepInsight
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

logger = logging.getLogger(__name__)

# Insight types that are always promoted regardless of confidence score.
_ALWAYS_PROMOTE: frozenset[InsightType] = frozenset({InsightType.ERROR_LEARNING, InsightType.BLOCKER})

# Mapping from InsightType to the memory_service memory_type string.
_INSIGHT_TO_MEMORY_TYPE: dict[InsightType, str] = {
    InsightType.DISCOVERY: "FACT",
    InsightType.ERROR_LEARNING: "EXPERIENCE",
    InsightType.DECISION: "CONTEXT",
    InsightType.DEPENDENCY: "CONTEXT",
    InsightType.ASSUMPTION: "CONTEXT",
    InsightType.CONSTRAINT: "CONTEXT",
    InsightType.PROGRESS: "CONTEXT",
    InsightType.BLOCKER: "EXPERIENCE",
}


class InsightPromotionMiddleware(RuntimeMiddleware):
    """Runtime middleware that promotes high-value insights to long-term memory.

    Reads ``ctx.metadata["new_insights"]`` (list[StepInsight]) after each step,
    filters by promotion criteria, and calls ``memory_service.store_memory()``
    for each qualifying insight.  The ``new_insights`` key is popped from
    metadata after processing so downstream middlewares see a clean slate.

    Args:
        memory_service: Any object exposing an async ``store_memory()`` method
            compatible with the Pythinker memory domain service signature.
        confidence_threshold: Minimum confidence required for non-always-promote
            insight types.  Defaults to 0.85.
    """

    def __init__(self, memory_service: Any, confidence_threshold: float = 0.85) -> None:
        self._memory_service = memory_service
        self._confidence_threshold = confidence_threshold

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        """Promote qualifying insights from metadata to long-term memory."""
        insights: list[StepInsight] = ctx.metadata.get("new_insights", [])
        user_id: str = ctx.metadata.get("user_id", "")

        if not user_id:
            # Cannot associate insights without a user identifier — skip silently.
            ctx.metadata.pop("new_insights", None)
            return ctx

        promoted = 0
        for insight in insights:
            if not self._should_promote(insight):
                continue

            memory_type = _INSIGHT_TO_MEMORY_TYPE.get(insight.insight_type, "CONTEXT")
            try:
                await self._memory_service.store_memory(
                    user_id=user_id,
                    content=insight.content,
                    memory_type=memory_type,
                    importance=insight.confidence,
                    tags=[insight.insight_type.value],
                    session_id=ctx.session_id,
                    generate_embedding=True,
                )
                promoted += 1
            except Exception:
                logger.warning(
                    "Failed to promote insight %s (type=%s) to long-term memory",
                    insight.id,
                    insight.insight_type.value,
                    exc_info=True,
                )

        if promoted:
            logger.info(
                "Promoted %d/%d insights to long-term memory (session=%s)",
                promoted,
                len(insights),
                ctx.session_id,
            )

        ctx.metadata.pop("new_insights", None)
        return ctx

    def _should_promote(self, insight: StepInsight) -> bool:
        """Return True if *insight* meets the promotion criteria."""
        return insight.insight_type in _ALWAYS_PROMOTE or insight.confidence >= self._confidence_threshold
