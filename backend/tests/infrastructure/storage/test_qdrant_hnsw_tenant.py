"""Tests for tenant-aware HNSW config and query-time hnsw_ef.

Validates that:
- _build_dense_vector_config reads m/payload_m from settings
- search_similar passes search_params with hnsw_ef
- search_hybrid passes params to the dense Prefetch
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client import models

from app.infrastructure.storage.qdrant import _build_dense_vector_config


class TestTenantAwareHNSW:
    """Test that collection creation uses settings-based HNSW config."""

    def test_build_dense_vector_config_reads_settings(self):
        """_build_dense_vector_config should use qdrant_hnsw_m and qdrant_hnsw_payload_m."""
        mock_settings = MagicMock()
        mock_settings.qdrant_hnsw_m = 0
        mock_settings.qdrant_hnsw_payload_m = 16

        with patch("app.infrastructure.storage.qdrant.get_settings", return_value=mock_settings):
            config = _build_dense_vector_config()

            assert config.size == 1536
            assert config.distance == models.Distance.COSINE
            assert config.hnsw_config.m == 0
            assert config.hnsw_config.payload_m == 16
            assert config.hnsw_config.ef_construct == 100

    def test_build_dense_vector_config_custom_m(self):
        """Custom m value should be respected (for non-tenant deployments)."""
        mock_settings = MagicMock()
        mock_settings.qdrant_hnsw_m = 32
        mock_settings.qdrant_hnsw_payload_m = 0

        with patch("app.infrastructure.storage.qdrant.get_settings", return_value=mock_settings):
            config = _build_dense_vector_config()
            assert config.hnsw_config.m == 32
            assert config.hnsw_config.payload_m == 0


class TestQueryTimeHnswEf:
    """Test that search queries pass hnsw_ef in search_params."""

    @pytest.mark.asyncio
    async def test_search_similar_uses_hnsw_ef(self):
        """search_similar should pass search_params with hnsw_ef."""
        mock_settings = MagicMock()
        mock_settings.qdrant_hnsw_ef = 128
        mock_settings.qdrant_user_knowledge_collection = "user_knowledge"

        mock_client = AsyncMock()
        mock_points = MagicMock()
        mock_points.points = []
        mock_client.query_points = AsyncMock(return_value=mock_points)

        mock_qdrant = MagicMock()
        mock_qdrant.client = mock_client

        with (
            patch(
                "app.infrastructure.repositories.qdrant_memory_repository.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "app.infrastructure.repositories.qdrant_memory_repository.get_qdrant",
                return_value=mock_qdrant,
            ),
        ):
            from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository

            repo = QdrantMemoryRepository()
            await repo.search_similar(
                user_id="u1",
                query_vector=[0.1] * 1536,
                limit=5,
            )

            # Verify search_params was passed
            call_kwargs = mock_client.query_points.call_args[1]
            assert "search_params" in call_kwargs
            assert call_kwargs["search_params"].hnsw_ef == 128
            assert call_kwargs["search_params"].exact is False

    @pytest.mark.asyncio
    async def test_search_hybrid_dense_prefetch_has_params(self):
        """search_hybrid should pass params with hnsw_ef to the dense Prefetch."""
        mock_settings = MagicMock()
        mock_settings.qdrant_hnsw_ef = 256
        mock_settings.qdrant_user_knowledge_collection = "user_knowledge"

        mock_client = AsyncMock()
        mock_points = MagicMock()
        mock_points.points = []
        mock_client.query_points = AsyncMock(return_value=mock_points)

        mock_qdrant = MagicMock()
        mock_qdrant.client = mock_client

        with (
            patch(
                "app.infrastructure.repositories.qdrant_memory_repository.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "app.infrastructure.repositories.qdrant_memory_repository.get_qdrant",
                return_value=mock_qdrant,
            ),
        ):
            from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository

            repo = QdrantMemoryRepository()
            await repo.search_hybrid(
                user_id="u1",
                query_text="test query",
                dense_vector=[0.1] * 1536,
                sparse_vector={0: 1.0, 5: 0.5},
                limit=5,
            )

            call_kwargs = mock_client.query_points.call_args[1]
            prefetches = call_kwargs["prefetch"]
            # Dense prefetch (second one) should have params
            dense_prefetch = prefetches[1]
            assert dense_prefetch.params is not None
            assert dense_prefetch.params.hnsw_ef == 256
