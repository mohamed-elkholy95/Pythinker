"""Tests for ConversationContextRepository.

Unit tests with mocked Qdrant client covering batch upsert,
hybrid search, sliding window scroll, and deletion.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client import models

from app.domain.models.conversation_context import ConversationContextResult
from app.infrastructure.repositories.conversation_context_repository import (
    ConversationContextRepository,
)

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _mock_settings():
    mock = MagicMock()
    mock.qdrant_conversation_context_collection = "conversation_context"
    mock.qdrant_use_hybrid_search = True
    return mock


def _mock_scored_point(
    point_id: str = "pt-1",
    content: str = "test content",
    role: str = "user",
    event_type: str = "message",
    session_id: str = "sess-1",
    turn_number: int = 0,
    created_at: int = 1700000000,
    score: float = 0.85,
):
    """Create a mock ScoredPoint matching Qdrant query_points output."""
    point = MagicMock()
    point.id = point_id
    point.score = score
    point.payload = {
        "content": content,
        "role": role,
        "event_type": event_type,
        "session_id": session_id,
        "turn_number": turn_number,
        "created_at": created_at,
    }
    return point


def _mock_record(
    point_id: str = "pt-1",
    content: str = "test content",
    role: str = "user",
    event_type: str = "message",
    session_id: str = "sess-1",
    turn_number: int = 0,
    created_at: int = 1700000000,
):
    """Create a mock Record matching Qdrant scroll output."""
    record = MagicMock()
    record.id = point_id
    record.payload = {
        "content": content,
        "role": role,
        "event_type": event_type,
        "session_id": session_id,
        "turn_number": turn_number,
        "created_at": created_at,
    }
    return record


@pytest.fixture
def mock_qdrant_client():
    """Create a mock Qdrant client."""
    client = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    client.count = AsyncMock()
    return client


@pytest.fixture
def repo(mock_qdrant_client):
    """Create ConversationContextRepository with mocked dependencies."""
    with (
        patch(
            "app.infrastructure.repositories.conversation_context_repository.get_settings",
            return_value=_mock_settings(),
        ),
        patch(
            "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
        ) as mock_qdrant_fn,
    ):
        mock_qdrant = MagicMock()
        mock_qdrant.client = mock_qdrant_client
        mock_qdrant_fn.return_value = mock_qdrant

        repository = ConversationContextRepository()

        # Patch get_qdrant for method calls too
        repository._get_qdrant = mock_qdrant

    return repository


# ------------------------------------------------------------------ #
# Batch upsert
# ------------------------------------------------------------------ #


class TestUpsertBatch:
    """Tests for batch upsert with named vectors."""

    @pytest.mark.asyncio
    async def test_upsert_batch_with_dense_and_sparse(self, mock_qdrant_client):
        """Upsert creates PointStruct with both dense and sparse named vectors."""
        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()

            turns = [
                {
                    "point_id": "pt-1",
                    "dense_vector": [0.1] * 10,
                    "sparse_vector": {0: 0.8, 5: 0.6},
                    "payload": {"user_id": "u1", "session_id": "s1", "content": "hello"},
                },
            ]

            await repo.upsert_batch(turns)

            mock_qdrant_client.upsert.assert_called_once()
            call_args = mock_qdrant_client.upsert.call_args
            assert call_args.kwargs["collection_name"] == "conversation_context"

            points = call_args.kwargs["points"]
            assert len(points) == 1
            assert points[0].id == "pt-1"
            # Check vectors dict has 'dense' and 'sparse' keys
            assert "dense" in points[0].vector
            assert isinstance(points[0].vector["sparse"], models.SparseVector)

    @pytest.mark.asyncio
    async def test_upsert_batch_without_sparse(self, mock_qdrant_client):
        """Upsert with None sparse_vector only includes dense."""
        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()

            turns = [
                {
                    "point_id": "pt-1",
                    "dense_vector": [0.1] * 10,
                    "sparse_vector": None,
                    "payload": {"user_id": "u1", "session_id": "s1"},
                },
            ]

            await repo.upsert_batch(turns)

            call_args = mock_qdrant_client.upsert.call_args
            points = call_args.kwargs["points"]
            assert "dense" in points[0].vector
            assert "sparse" not in points[0].vector

    @pytest.mark.asyncio
    async def test_upsert_batch_empty_list(self, mock_qdrant_client):
        """Empty list is a no-op."""
        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            await repo.upsert_batch([])

            mock_qdrant_client.upsert.assert_not_called()


# ------------------------------------------------------------------ #
# Session turn search
# ------------------------------------------------------------------ #


class TestSearchSessionTurns:
    """Tests for intra-session hybrid search."""

    @pytest.mark.asyncio
    async def test_search_session_returns_results(self, mock_qdrant_client):
        """Hybrid RRF search returns ConversationContextResult list."""
        query_result = MagicMock()
        query_result.points = [
            _mock_scored_point("pt-1", "turn content A", score=0.9, turn_number=3),
            _mock_scored_point("pt-2", "turn content B", score=0.7, turn_number=1),
        ]
        mock_qdrant_client.query_points = AsyncMock(return_value=query_result)

        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            results = await repo.search_session_turns(
                session_id="sess-1",
                dense_vector=[0.1] * 10,
                sparse_vector={0: 0.5},
                limit=5,
            )

        assert len(results) == 2
        assert all(isinstance(r, ConversationContextResult) for r in results)
        assert results[0].content == "turn content A"
        assert results[0].relevance_score == 0.9
        assert results[0].source == "intra_session"

    @pytest.mark.asyncio
    async def test_search_session_dense_only_fallback(self, mock_qdrant_client):
        """Without sparse_vector, falls back to dense-only search."""
        query_result = MagicMock()
        query_result.points = [_mock_scored_point("pt-1", "dense result")]
        mock_qdrant_client.query_points = AsyncMock(return_value=query_result)

        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            results = await repo.search_session_turns(
                session_id="sess-1",
                dense_vector=[0.1] * 10,
                sparse_vector=None,
                limit=5,
            )

        assert len(results) == 1
        # Dense-only uses `using="dense"`, not prefetch+fusion
        call_args = mock_qdrant_client.query_points.call_args
        assert call_args.kwargs.get("using") == "dense"


# ------------------------------------------------------------------ #
# Cross-session search
# ------------------------------------------------------------------ #


class TestSearchCrossSession:
    """Tests for cross-session search isolation."""

    @pytest.mark.asyncio
    async def test_cross_session_excludes_current(self, mock_qdrant_client):
        """Cross-session search excludes the current session_id."""
        query_result = MagicMock()
        query_result.points = [
            _mock_scored_point("pt-x", "old session turn", session_id="sess-old", score=0.75),
        ]
        mock_qdrant_client.query_points = AsyncMock(return_value=query_result)

        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            results = await repo.search_cross_session(
                user_id="user-1",
                exclude_session_id="sess-current",
                dense_vector=[0.1] * 10,
                sparse_vector={0: 0.5},
                limit=3,
            )

        assert len(results) == 1
        assert results[0].source == "cross_session"
        assert results[0].session_id == "sess-old"

        # Verify the filter excludes current session
        call_args = mock_qdrant_client.query_points.call_args
        query_filter = call_args.kwargs.get("query_filter")
        assert query_filter is not None


# ------------------------------------------------------------------ #
# Sliding window scroll
# ------------------------------------------------------------------ #


class TestGetRecentTurns:
    """Tests for payload-only scroll (no embedding needed)."""

    @pytest.mark.asyncio
    async def test_get_recent_turns(self, mock_qdrant_client):
        """Scroll returns ConversationContextResult with score=1.0."""
        records = [
            _mock_record("pt-1", "Turn A", turn_number=8),
            _mock_record("pt-2", "Turn B", turn_number=9),
        ]
        mock_qdrant_client.scroll = AsyncMock(return_value=(records, None))

        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            results = await repo.get_recent_turns(
                session_id="sess-1",
                min_turn_number=8,
                limit=5,
            )

        assert len(results) == 2
        assert all(r.relevance_score == 1.0 for r in results)
        assert all(r.source == "sliding_window" for r in results)
        assert results[0].turn_number == 8
        assert results[1].turn_number == 9


# ------------------------------------------------------------------ #
# Deletion
# ------------------------------------------------------------------ #


class TestDeletion:
    """Tests for session and user context deletion."""

    @pytest.mark.asyncio
    async def test_delete_session_context(self, mock_qdrant_client):
        """Delete removes all points for a session."""
        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            await repo.delete_session_context("sess-to-delete")

            mock_qdrant_client.delete.assert_called_once()
            call_args = mock_qdrant_client.delete.call_args
            assert call_args.kwargs["collection_name"] == "conversation_context"

    @pytest.mark.asyncio
    async def test_delete_user_context(self, mock_qdrant_client):
        """Delete removes all points for a user."""
        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            await repo.delete_user_context("user-to-delete")

            mock_qdrant_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_session_turns(self, mock_qdrant_client):
        """Count returns the number of stored turns for a session."""
        count_result = MagicMock()
        count_result.count = 42
        mock_qdrant_client.count = AsyncMock(return_value=count_result)

        with (
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "app.infrastructure.repositories.conversation_context_repository.get_qdrant",
            ) as mock_qdrant_fn,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_fn.return_value = mock_qdrant

            repo = ConversationContextRepository()
            count = await repo.count_session_turns("sess-1")

        assert count == 42
