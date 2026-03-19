"""Qdrant repository for tool execution log vectors.

Stores embeddings of tool executions to enable learning
from past tool use patterns and error recovery.
"""

import asyncio
import logging
import time

from qdrant_client import models

from app.core.config import get_settings
from app.core.retry import db_retry
from app.domain.repositories.vector_repos import ToolLogRepository
from app.infrastructure.storage.qdrant import get_qdrant

logger = logging.getLogger(__name__)


class QdrantToolLogRepository(ToolLogRepository):
    """Repository for tool execution log vectors in Qdrant."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._collection = self._settings.qdrant_tool_logs_collection
        self._use_named_vectors: bool | None = None
        self._vector_mode_lock = asyncio.Lock()

    @staticmethod
    def _is_vector_name_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "not existing vector name" in message or "vector with name" in message

    async def _resolve_vector_mode(self) -> bool:
        """Return whether this collection uses named vectors.

        Defaults to named vectors on introspection failure because the project
        creates tool_logs with named dense+sparse vectors.
        """
        if self._use_named_vectors is not None:
            return self._use_named_vectors

        async with self._vector_mode_lock:
            if self._use_named_vectors is not None:
                return self._use_named_vectors

            try:
                collection_info = await get_qdrant().client.get_collection(collection_name=self._collection)
                vectors = collection_info.config.params.vectors
                self._use_named_vectors = isinstance(vectors, dict)
            except Exception as e:
                # Broad catch justified: qdrant_client may raise httpx errors,
                # gRPC errors, or custom exceptions depending on transport mode.
                # Defaulting to named vectors is the safe fallback.
                logger.debug(
                    "Failed to introspect vector mode for collection %s, defaulting to named vectors: %s",
                    self._collection,
                    e,
                )
                self._use_named_vectors = True

            return self._use_named_vectors

    async def _flip_vector_mode(self) -> bool:
        """Flip cached vector mode to recover from schema mismatch."""
        current = await self._resolve_vector_mode()
        self._use_named_vectors = not current
        return self._use_named_vectors

    @db_retry
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
        use_named_vectors = await self._resolve_vector_mode()
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "tool_name": tool_name,
            "outcome": outcome,
            "input_summary": input_summary,
            "error_type": error_type,
            "created_at": time.time(),
        }

        try:
            await get_qdrant().client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=log_id,
                        vector={"dense": embedding} if use_named_vectors else embedding,
                        payload=payload,
                    )
                ],
            )
        except Exception as e:  # Broad catch: qdrant_client uses varied exception types (gRPC/REST)
            if not self._is_vector_name_error(e):
                raise

            use_named_vectors = await self._flip_vector_mode()
            logger.warning(
                "Tool log upsert vector mode mismatch for %s, retrying with %s vectors",
                self._collection,
                "named" if use_named_vectors else "unnamed",
            )
            await get_qdrant().client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=log_id,
                        vector={"dense": embedding} if use_named_vectors else embedding,
                        payload=payload,
                    )
                ],
            )

    @db_retry
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

        use_named_vectors = await self._resolve_vector_mode()
        query_kwargs = {
            "collection_name": self._collection,
            "query": query_vector,
            "query_filter": models.Filter(must=must_conditions),
            "limit": limit,
            "score_threshold": min_score,
        }
        if use_named_vectors:
            query_kwargs["using"] = "dense"

        try:
            results = await get_qdrant().client.query_points(**query_kwargs)
        except Exception as e:  # Broad catch: qdrant_client uses varied exception types (gRPC/REST)
            if not self._is_vector_name_error(e):
                raise

            use_named_vectors = await self._flip_vector_mode()
            logger.warning(
                "Tool log query vector mode mismatch for %s, retrying with %s vectors",
                self._collection,
                "named" if use_named_vectors else "unnamed",
            )
            if use_named_vectors:
                query_kwargs["using"] = "dense"
            else:
                query_kwargs.pop("using", None)
            results = await get_qdrant().client.query_points(**query_kwargs)

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

    @db_retry
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
