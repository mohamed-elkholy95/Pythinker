"""Qdrant repository for tool execution log vectors.

Stores embeddings of tool executions to enable learning
from past tool use patterns and error recovery.
"""

import logging
import time

from qdrant_client import models

from app.core.config import get_settings
from app.domain.repositories.vector_repos import ToolLogRepository
from app.infrastructure.storage.qdrant import get_qdrant

logger = logging.getLogger(__name__)


class QdrantToolLogRepository(ToolLogRepository):
    """Repository for tool execution log vectors in Qdrant."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._collection = self._settings.qdrant_tool_logs_collection

    async def log_tool_execution(
        self,
        log_id: str,
        user_id: str,
        session_id: str,
        tool_name: str,
        embedding: list[float],
        outcome: str,
        input_summary: str = "",
        error_type: str | None = None,
    ) -> None:
        """Log a tool execution with its embedding."""
        await get_qdrant().client.upsert(
            collection_name=self._collection,
            points=[
                models.PointStruct(
                    id=log_id,
                    vector=embedding,
                    payload={
                        "user_id": user_id,
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "outcome": outcome,
                        "input_summary": input_summary,
                        "error_type": error_type,
                        "created_at": time.time(),
                    },
                )
            ],
        )

    async def find_similar_tool_executions(
        self,
        user_id: str,
        query_vector: list[float],
        tool_name: str | None = None,
        outcome: str | None = None,
        limit: int = 5,
        min_score: float = 0.4,
    ) -> list[dict]:
        """Find similar past tool executions."""
        must_conditions: list[models.FieldCondition] = [
            models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))
        ]

        if tool_name:
            must_conditions.append(models.FieldCondition(key="tool_name", match=models.MatchValue(value=tool_name)))

        if outcome:
            must_conditions.append(models.FieldCondition(key="outcome", match=models.MatchValue(value=outcome)))

        results = await get_qdrant().client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=models.Filter(must=must_conditions),
            limit=limit,
            score_threshold=min_score,
        )

        return [
            {
                "log_id": str(point.id),
                "relevance_score": point.score,
                "tool_name": point.payload.get("tool_name") if point.payload else None,
                "outcome": point.payload.get("outcome") if point.payload else None,
                "error_type": point.payload.get("error_type") if point.payload else None,
                "input_summary": point.payload.get("input_summary") if point.payload else None,
            }
            for point in results.points
        ]

    async def delete_user_logs(self, user_id: str) -> None:
        """Delete all tool logs for a user."""
        await get_qdrant().client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
                )
            ),
        )
