"""Domain Protocol for conversation context vector storage.

Defines the contract for conversation context repositories,
supporting batch upsert and hybrid search operations.
"""

from typing import Protocol

from app.domain.models.conversation_context import ConversationContextResult


class ConversationContextRepository(Protocol):
    """Abstract repository for conversation context vector storage.

    Implementations should handle:
    - Batch upsert of vectorized conversation turns
    - Hybrid (dense + sparse) intra-session semantic search
    - Cross-session recall search
    - Sliding window retrieval by turn number
    """

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
        ...

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
        ...

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
        ...

    async def get_recent_turns(
        self,
        session_id: str,
        min_turn_number: int,
        limit: int = 5,
    ) -> list[ConversationContextResult]:
        """Get recent turns by turn_number (sliding window).

        Returns turns with turn_number >= min_turn_number, ordered ascending.
        """
        ...
