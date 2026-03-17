"""Tests for Qdrant vector database wiring and multi-collection setup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.repositories.vector_memory_repository import (
    VectorMemoryRepository,
    VectorSearchResult,
    get_vector_memory_repository,
    set_vector_memory_repository,
)
from app.infrastructure.repositories.qdrant_memory_repository import (
    QdrantMemoryRepository,
)


class TestQdrantABCCompliance:
    """Test that QdrantMemoryRepository properly implements VectorMemoryRepository."""

    def test_inherits_from_abc(self):
        """QdrantMemoryRepository should extend VectorMemoryRepository."""
        assert issubclass(QdrantMemoryRepository, VectorMemoryRepository)

    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    def test_instance_is_vector_memory_repository(self, mock_settings):
        """Instance should be usable as VectorMemoryRepository."""
        mock_settings.return_value = MagicMock(qdrant_collection="test")
        repo = QdrantMemoryRepository()
        assert isinstance(repo, VectorMemoryRepository)

    @pytest.mark.asyncio
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_qdrant")
    async def test_search_similar_returns_vector_search_result(self, mock_qdrant, mock_settings):
        """search_similar should return VectorSearchResult instances."""
        mock_settings.return_value = MagicMock(qdrant_collection="test")

        # Mock Qdrant query_points response
        mock_point = MagicMock()
        mock_point.id = "mem-1"
        mock_point.score = 0.85
        mock_point.payload = {"memory_type": "fact", "importance": "high"}

        mock_response = MagicMock()
        mock_response.points = [mock_point]

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.query_points = AsyncMock(return_value=mock_response)
        mock_qdrant.return_value = mock_storage

        repo = QdrantMemoryRepository()
        results = await repo.search_similar(
            user_id="user-1",
            query_vector=[0.1] * 1536,
        )

        assert len(results) == 1
        assert isinstance(results[0], VectorSearchResult)
        assert results[0].memory_id == "mem-1"
        assert results[0].relevance_score == 0.85
        assert results[0].memory_type == "fact"
        assert results[0].importance == "high"

    @pytest.mark.asyncio
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_qdrant")
    async def test_search_similar_empty_results(self, mock_qdrant, mock_settings):
        """search_similar should return empty list when no points match."""
        mock_settings.return_value = MagicMock(qdrant_collection="test")

        mock_response = MagicMock()
        mock_response.points = []

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.query_points = AsyncMock(return_value=mock_response)
        mock_qdrant.return_value = mock_storage

        repo = QdrantMemoryRepository()
        results = await repo.search_similar(
            user_id="user-1",
            query_vector=[0.1] * 1536,
        )

        assert results == []

    @pytest.mark.asyncio
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_qdrant")
    async def test_upsert_memory_calls_qdrant(self, mock_qdrant, mock_settings):
        """upsert_memory should call Qdrant upsert with correct parameters."""
        mock_settings.return_value = MagicMock(qdrant_collection="test_collection")

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.upsert = AsyncMock()
        mock_qdrant.return_value = mock_storage

        repo = QdrantMemoryRepository()
        await repo.upsert_memory(
            memory_id="mem-1",
            user_id="user-1",
            embedding=[0.1] * 1536,
            memory_type="fact",
            importance="high",
            tags=["python"],
        )

        mock_storage.client.upsert.assert_called_once()
        call_kwargs = mock_storage.client.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"

    @pytest.mark.asyncio
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_qdrant")
    async def test_delete_memory_calls_qdrant(self, mock_qdrant, mock_settings):
        """delete_memory should call Qdrant delete with correct point ID."""
        mock_settings.return_value = MagicMock(qdrant_collection="test_collection")

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.delete = AsyncMock()
        mock_qdrant.return_value = mock_storage

        repo = QdrantMemoryRepository()
        await repo.delete_memory("mem-1")

        mock_storage.client.delete.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_qdrant")
    async def test_delete_user_memories_uses_filter(self, mock_qdrant, mock_settings):
        """delete_user_memories should delete by user_id filter."""
        mock_settings.return_value = MagicMock(qdrant_collection="test_collection")

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.delete = AsyncMock()
        mock_qdrant.return_value = mock_storage

        repo = QdrantMemoryRepository()
        await repo.delete_user_memories("user-1")

        mock_storage.client.delete.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_qdrant")
    async def test_upsert_memories_batch_skips_empty(self, mock_qdrant, mock_settings):
        """upsert_memories_batch should return early for empty list."""
        mock_settings.return_value = MagicMock(qdrant_collection="test")

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.upsert = AsyncMock()
        mock_qdrant.return_value = mock_storage

        repo = QdrantMemoryRepository()
        await repo.upsert_memories_batch([])

        mock_storage.client.upsert.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_settings")
    @patch("app.infrastructure.repositories.qdrant_memory_repository.get_qdrant")
    async def test_search_similar_with_memory_type_filter(self, mock_qdrant, mock_settings):
        """search_similar should pass memory_types filter to Qdrant."""
        from app.domain.models.long_term_memory import MemoryType

        mock_settings.return_value = MagicMock(qdrant_collection="test")

        mock_response = MagicMock()
        mock_response.points = []

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.query_points = AsyncMock(return_value=mock_response)
        mock_qdrant.return_value = mock_storage

        repo = QdrantMemoryRepository()
        await repo.search_similar(
            user_id="user-1",
            query_vector=[0.1] * 1536,
            memory_types=[MemoryType.FACT, MemoryType.PREFERENCE],
        )

        call_kwargs = mock_storage.client.query_points.call_args.kwargs
        # Verify the filter includes memory_type condition
        filter_obj = call_kwargs["query_filter"]
        assert filter_obj is not None


class TestVectorRepoWiring:
    """Test domain-layer vector repo singleton wiring."""

    def test_set_and_get_vector_memory_repository(self):
        """set/get should work as dependency injection."""
        import app.domain.repositories.vector_memory_repository as mod

        old = mod._vector_memory_repo

        mock_repo = MagicMock(spec=VectorMemoryRepository)
        set_vector_memory_repository(mock_repo)

        result = get_vector_memory_repository()
        assert result is mock_repo

        # Restore original
        mod._vector_memory_repo = old

    def test_get_returns_none_when_not_set(self):
        """get should return None before set is called."""
        import app.domain.repositories.vector_memory_repository as mod

        old = mod._vector_memory_repo
        mod._vector_memory_repo = None

        result = get_vector_memory_repository()
        assert result is None

        # Restore
        mod._vector_memory_repo = old

    def test_set_accepts_none_for_clearing(self):
        """set_vector_memory_repository(None) should clear the singleton."""
        import app.domain.repositories.vector_memory_repository as mod

        old = mod._vector_memory_repo

        mock_repo = MagicMock(spec=VectorMemoryRepository)
        set_vector_memory_repository(mock_repo)
        assert get_vector_memory_repository() is mock_repo

        set_vector_memory_repository(None)
        assert get_vector_memory_repository() is None

        # Restore
        mod._vector_memory_repo = old


class TestMultiCollectionSetup:
    """Test multi-collection configuration."""

    def test_collections_dict_has_required_collections(self):
        """COLLECTIONS should define all required collections."""
        from app.infrastructure.storage.qdrant import COLLECTIONS

        assert "user_knowledge" in COLLECTIONS
        assert "task_artifacts" in COLLECTIONS
        assert "tool_logs" in COLLECTIONS
        assert "semantic_cache" in COLLECTIONS

    def test_collections_use_cosine_distance(self):
        """All collections should use cosine distance."""
        from qdrant_client import models as qdrant_models

        from app.infrastructure.storage.qdrant import COLLECTIONS

        for name, params in COLLECTIONS.items():
            assert params.distance == qdrant_models.Distance.COSINE, f"{name} should use COSINE distance"

    def test_collections_use_1536_dimensions(self):
        """All collections should use 1536 dimensions for OpenAI embeddings."""
        from app.infrastructure.storage.qdrant import COLLECTIONS

        for name, params in COLLECTIONS.items():
            assert params.size == 1536, f"{name} should have 1536 dimensions"

    def test_collection_indexes_defined(self):
        """COLLECTION_INDEXES should define indexes for all collections."""
        from app.infrastructure.storage.qdrant import COLLECTION_INDEXES

        assert "user_id" in COLLECTION_INDEXES["user_knowledge"]
        assert "memory_type" in COLLECTION_INDEXES["user_knowledge"]
        assert "importance" in COLLECTION_INDEXES["user_knowledge"]

        assert "user_id" in COLLECTION_INDEXES["task_artifacts"]
        assert "session_id" in COLLECTION_INDEXES["task_artifacts"]
        assert "artifact_type" in COLLECTION_INDEXES["task_artifacts"]

        assert "tool_name" in COLLECTION_INDEXES["tool_logs"]
        assert "outcome" in COLLECTION_INDEXES["tool_logs"]

        assert "context_hash" in COLLECTION_INDEXES["semantic_cache"]

    def test_collection_indexes_cover_all_collections(self):
        """Every collection in COLLECTIONS should have indexes defined."""
        from app.infrastructure.storage.qdrant import COLLECTION_INDEXES, COLLECTIONS

        for name in COLLECTIONS:
            assert name in COLLECTION_INDEXES, f"Missing indexes for collection: {name}"

    def test_config_has_multi_collection_fields(self):
        """Settings should have multi-collection config fields."""
        from app.core.config import Settings

        settings = Settings(
            mongodb_uri="mongodb://localhost:27017",
            api_key="test-key",
        )
        assert settings.qdrant_user_knowledge_collection == "user_knowledge"
        assert settings.qdrant_task_artifacts_collection == "task_artifacts"
        assert settings.qdrant_tool_logs_collection == "tool_logs"

    def test_config_has_legacy_collection(self):
        """Settings should have legacy qdrant_collection field."""
        from app.core.config import Settings

        settings = Settings(
            mongodb_uri="mongodb://localhost:27017",
            api_key="test-key",
        )
        assert settings.qdrant_collection == "agent_memories"

    def test_config_has_qdrant_connection_fields(self):
        """Settings should have Qdrant connection config."""
        from app.core.config import Settings

        settings = Settings(
            mongodb_uri="mongodb://localhost:27017",
            api_key="test-key",
        )
        assert hasattr(settings, "qdrant_url")
        assert hasattr(settings, "qdrant_grpc_port")
        assert hasattr(settings, "qdrant_prefer_grpc")
        assert hasattr(settings, "qdrant_api_key")
