"""Qdrant repository for conversation context vectors.

Handles vectorized storage and hybrid search for conversation turns
during active sessions. Follows the same patterns as QdrantMemoryRepository.

Phase 1: Named-vector schema with hybrid dense+sparse (RRF) retrieval.
"""

import logging
import time

from qdrant_client import models

from app.core.config import get_settings
from app.core.prometheus_metrics import qdrant_query_duration_seconds
from app.domain.models.conversation_context import ConversationContextResult
from app.infrastructure.storage.qdrant import get_qdrant

logger = logging.getLogger(__name__)


class ConversationContextRepository:
    """Qdrant-based vector storage for conversation context.

    Stores and retrieves vectorized conversation turns for real-time
    semantic retrieval during active sessions and cross-session recall.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._collection = getattr(
            self._settings,
            "qdrant_conversation_context_collection",
            "conversation_context",
        )

    async def upsert_batch(
        self,
        turns: list[dict],
    ) -> None:
        """Batch upsert conversation turns with named vectors.

        Args:
            turns: List of dicts with keys:
                - point_id: str (UUID)
                - dense_vector: list[float] (1536d)
                - sparse_vector: dict[int, float] (BM25)
                - payload: dict (user_id, session_id, role, event_type, etc.)
        """
        if not turns:
            return

        points = []
        for turn in turns:
            vectors: dict = {"dense": turn["dense_vector"]}

            sparse = turn.get("sparse_vector")
            if sparse:
                vectors["sparse"] = models.SparseVector(
                    indices=[int(k) for k in sparse],
                    values=list(sparse.values()),
                )

            points.append(
                models.PointStruct(
                    id=turn["point_id"],
                    vector=vectors,
                    payload=turn["payload"],
                )
            )

        await get_qdrant().client.upsert(
            collection_name=self._collection,
            points=points,
        )
        logger.debug("Batch upserted %d conversation turns to Qdrant", len(turns))

    async def search_session_turns(
        self,
        session_id: str,
        dense_vector: list[float],
        sparse_vector: dict[int, float] | None = None,
        limit: int = 5,
        min_score: float = 0.3,
        exclude_turn_numbers: list[int] | None = None,
    ) -> list[ConversationContextResult]:
        """Search for relevant turns within a session using hybrid RRF search.

        Args:
            session_id: Session to search within
            dense_vector: Query embedding
            sparse_vector: Optional BM25 sparse vector for hybrid search
            limit: Max results
            min_score: Minimum relevance score
            exclude_turn_numbers: Turn numbers to exclude (e.g., sliding window)
        """
        must_conditions: list[models.Condition] = [
            models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id)),
        ]

        # Exclude recent turns already in sliding window
        must_not_conditions: list[models.Condition] = []
        if exclude_turn_numbers:
            must_not_conditions.extend(
                models.FieldCondition(key="turn_number", match=models.MatchValue(value=tn))
                for tn in exclude_turn_numbers
            )

        query_filter = models.Filter(
            must=must_conditions,
            must_not=must_not_conditions if must_not_conditions else None,
        )

        start_time = time.time()
        try:
            if sparse_vector and self._settings.qdrant_use_hybrid_search:
                # Hybrid RRF search (dense + sparse)
                sparse_vec = models.SparseVector(
                    indices=[int(k) for k in sparse_vector],
                    values=list(sparse_vector.values()),
                )
                results = await get_qdrant().client.query_points(
                    collection_name=self._collection,
                    prefetch=[
                        models.Prefetch(
                            query=sparse_vec,
                            using="sparse",
                            limit=limit * 2,
                            filter=query_filter,
                        ),
                        models.Prefetch(
                            query=dense_vector,
                            using="dense",
                            limit=limit * 2,
                            filter=query_filter,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=min_score,
                )
            else:
                # Dense-only search
                results = await get_qdrant().client.query_points(
                    collection_name=self._collection,
                    query=dense_vector,
                    using="dense",
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=min_score,
                )
        finally:
            duration = time.time() - start_time
            qdrant_query_duration_seconds.observe(
                {"operation": "search_session_turns", "collection": self._collection},
                duration,
            )

        return [
            ConversationContextResult(
                point_id=str(point.id),
                content=point.payload.get("content", "") if point.payload else "",
                role=point.payload.get("role", "user") if point.payload else "user",
                event_type=point.payload.get("event_type", "message") if point.payload else "message",
                session_id=session_id,
                turn_number=point.payload.get("turn_number", 0) if point.payload else 0,
                created_at=point.payload.get("created_at", 0) if point.payload else 0,
                relevance_score=point.score,
                source="intra_session",
            )
            for point in results.points
        ]

    async def search_cross_session(
        self,
        user_id: str,
        exclude_session_id: str,
        dense_vector: list[float],
        sparse_vector: dict[int, float] | None = None,
        limit: int = 3,
        min_score: float = 0.4,
    ) -> list[ConversationContextResult]:
        """Search for relevant turns across other sessions by the same user.

        Args:
            user_id: User whose sessions to search
            exclude_session_id: Current session to exclude
            dense_vector: Query embedding (reused from intra-session search)
            sparse_vector: Optional BM25 sparse vector
            limit: Max results
            min_score: Minimum relevance (higher than intra-session)
        """
        query_filter = models.Filter(
            must=[
                models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
            ],
            must_not=[
                models.FieldCondition(key="session_id", match=models.MatchValue(value=exclude_session_id)),
            ],
        )

        start_time = time.time()
        try:
            if sparse_vector and self._settings.qdrant_use_hybrid_search:
                sparse_vec = models.SparseVector(
                    indices=[int(k) for k in sparse_vector],
                    values=list(sparse_vector.values()),
                )
                results = await get_qdrant().client.query_points(
                    collection_name=self._collection,
                    prefetch=[
                        models.Prefetch(
                            query=sparse_vec,
                            using="sparse",
                            limit=limit * 2,
                            filter=query_filter,
                        ),
                        models.Prefetch(
                            query=dense_vector,
                            using="dense",
                            limit=limit * 2,
                            filter=query_filter,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=min_score,
                )
            else:
                results = await get_qdrant().client.query_points(
                    collection_name=self._collection,
                    query=dense_vector,
                    using="dense",
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=min_score,
                )
        finally:
            duration = time.time() - start_time
            qdrant_query_duration_seconds.observe(
                {"operation": "search_cross_session", "collection": self._collection},
                duration,
            )

        return [
            ConversationContextResult(
                point_id=str(point.id),
                content=point.payload.get("content", "") if point.payload else "",
                role=point.payload.get("role", "user") if point.payload else "user",
                event_type=point.payload.get("event_type", "message") if point.payload else "message",
                session_id=point.payload.get("session_id", "") if point.payload else "",
                turn_number=point.payload.get("turn_number", 0) if point.payload else 0,
                created_at=point.payload.get("created_at", 0) if point.payload else 0,
                relevance_score=point.score,
                source="cross_session",
            )
            for point in results.points
        ]

    async def get_recent_turns(
        self,
        session_id: str,
        min_turn_number: int,
        limit: int = 5,
    ) -> list[ConversationContextResult]:
        """Get recent turns by turn_number (sliding window).

        Uses scroll instead of search — no embedding needed.
        Returns turns with turn_number >= min_turn_number, ordered ascending.
        """
        start_time = time.time()
        try:
            results, _next_offset = await get_qdrant().client.scroll(
                collection_name=self._collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id)),
                        models.FieldCondition(
                            key="turn_number",
                            range=models.Range(gte=min_turn_number),
                        ),
                    ],
                ),
                limit=limit,
                order_by=models.OrderBy(key="turn_number", direction=models.Direction.ASC),
            )
        finally:
            duration = time.time() - start_time
            qdrant_query_duration_seconds.observe(
                {"operation": "get_recent_turns", "collection": self._collection},
                duration,
            )

        return [
            ConversationContextResult(
                point_id=str(point.id),
                content=point.payload.get("content", "") if point.payload else "",
                role=point.payload.get("role", "user") if point.payload else "user",
                event_type=point.payload.get("event_type", "message") if point.payload else "message",
                session_id=session_id,
                turn_number=point.payload.get("turn_number", 0) if point.payload else 0,
                created_at=point.payload.get("created_at", 0) if point.payload else 0,
                relevance_score=1.0,  # Sliding window — always relevant
                source="sliding_window",
            )
            for point in results
        ]

    async def delete_session_context(self, session_id: str) -> None:
        """Delete all context for a session."""
        await get_qdrant().client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))]
                )
            ),
        )
        logger.info("Deleted conversation context for session %s", session_id)

    async def delete_user_context(self, user_id: str) -> None:
        """Delete all context for a user."""
        await get_qdrant().client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
                )
            ),
        )
        logger.info("Deleted all conversation context for user %s", user_id)

    async def count_session_turns(self, session_id: str) -> int:
        """Count stored turns for a session."""
        result = await get_qdrant().client.count(
            collection_name=self._collection,
            count_filter=models.Filter(
                must=[models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))]
            ),
        )
        return result.count
