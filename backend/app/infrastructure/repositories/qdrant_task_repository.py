"""Qdrant repository for task artifact vectors.

Stores embeddings of task outcomes, plans, and procedures
for cross-session learning and similar task retrieval.
"""

import asyncio
import logging
import time

from qdrant_client import models

from app.core.config import get_settings
from app.domain.repositories.vector_repos import TaskArtifactRepository
from app.infrastructure.storage.qdrant import get_qdrant

logger = logging.getLogger(__name__)


class QdrantTaskRepository(TaskArtifactRepository):
    """Repository for task artifact vectors in Qdrant."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._collection = self._settings.qdrant_task_artifacts_collection
        self._use_named_vectors: bool | None = None
        self._vector_mode_lock = asyncio.Lock()

    @staticmethod
    def _is_vector_name_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "not existing vector name" in message or "vector with name" in message

    async def _resolve_vector_mode(self) -> bool:
        """Return whether this collection uses named vectors.

        Defaults to named vectors on introspection failure because the project
        creates task_artifacts with named dense+sparse vectors.
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

    async def store_task_artifact(
        self,
        artifact_id: str,
        user_id: str,
        session_id: str,
        embedding: list[float],
        artifact_type: str,
        agent_role: str = "executor",
        task_id: str | None = None,
        step_index: int | None = None,
        success: bool | None = None,
        content_summary: str = "",
    ) -> None:
        """Store a task artifact embedding."""
        use_named_vectors = await self._resolve_vector_mode()

        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "artifact_type": artifact_type,
            "agent_role": agent_role,
            "step_index": step_index,
            "success": success,
            "content_summary": content_summary,
            "created_at": time.time(),
        }

        try:
            await get_qdrant().client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=artifact_id,
                        vector={"dense": embedding} if use_named_vectors else embedding,
                        payload=payload,
                    )
                ],
            )
        except Exception as e:
            if not self._is_vector_name_error(e):
                raise

            use_named_vectors = await self._flip_vector_mode()
            logger.warning(
                "Task artifact upsert vector mode mismatch for %s, retrying with %s vectors",
                self._collection,
                "named" if use_named_vectors else "unnamed",
            )
            await get_qdrant().client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=artifact_id,
                        vector={"dense": embedding} if use_named_vectors else embedding,
                        payload=payload,
                    )
                ],
            )

    async def find_similar_tasks(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int = 5,
        min_score: float = 0.5,
        artifact_types: list[str] | None = None,
    ) -> list[dict]:
        """Find similar past task artifacts."""
        must_conditions: list[models.FieldCondition] = [
            models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))
        ]

        if artifact_types:
            must_conditions.append(
                models.FieldCondition(
                    key="artifact_type",
                    match=models.MatchAny(any=artifact_types),
                )
            )

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
        except Exception as e:
            if not self._is_vector_name_error(e):
                raise

            use_named_vectors = await self._flip_vector_mode()
            logger.warning(
                "Task artifact query vector mode mismatch for %s, retrying with %s vectors",
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
                "artifact_id": str(point.id),
                "relevance_score": point.score,
                "artifact_type": point.payload.get("artifact_type") if point.payload else None,
                "session_id": point.payload.get("session_id") if point.payload else None,
                "success": point.payload.get("success") if point.payload else None,
                "content_summary": point.payload.get("content_summary") if point.payload else None,
            }
            for point in results.points
        ]

    async def delete_user_artifacts(self, user_id: str) -> None:
        """Delete all task artifacts for a user."""
        await get_qdrant().client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
                )
            ),
        )
