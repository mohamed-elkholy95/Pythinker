"""Smoke tests for WP-1: Hybrid retrieval wiring in MemoryService.

Tests verify:
- search_hybrid() is called when qdrant_use_hybrid_search=True and sparse vector is non-empty
- Fallback to search_similar() when sparse vector is empty (unfitted BM25)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def mock_llm():
    llm = MagicMock()
    llm.embed = AsyncMock(return_value=[0.1] * 1536)
    return llm


@pytest.fixture()
def mock_vector_repo():
    repo = MagicMock()
    repo.search_similar = AsyncMock(return_value=[])
    repo.search_hybrid = AsyncMock(return_value=[])
    return repo


@pytest.fixture()
def mock_memory_repo():
    repo = MagicMock()
    repo.get_by_ids = AsyncMock(return_value=[])
    repo.find_by_user = AsyncMock(return_value=[])
    repo.vector_search = AsyncMock(return_value=[])
    repo.search = AsyncMock(return_value=[])
    return repo


@pytest.mark.asyncio
async def test_search_hybrid_called_when_flag_enabled_and_sparse_nonempty(
    mock_llm, mock_vector_repo, mock_memory_repo
):
    """search_hybrid() is invoked when qdrant_use_hybrid_search=True and BM25 returns vectors."""
    from app.domain.services.memory_service import MemoryService

    service = MemoryService(
        repository=mock_memory_repo,
        llm=mock_llm,
    )

    # Patch settings to enable hybrid search
    mock_settings = MagicMock()
    mock_settings.qdrant_use_hybrid_search = True

    # Sparse vector with real content
    sparse = {"0": 0.8, "1": 0.6}

    with (
        patch(
            "app.domain.services.memory_service._get_vector_repo",
            return_value=mock_vector_repo,
        ),
        patch.object(
            MemoryService,
            "_generate_embedding",
            new=AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.domain.services.memory_service.MemoryService._generate_sparse_vector",
            return_value=sparse,
        ),
        patch(
            "app.core.config.get_settings",
            return_value=mock_settings,
        ),
    ):
        await service.retrieve_relevant(user_id="u1", context="test query")

    mock_vector_repo.search_hybrid.assert_called_once()
    mock_vector_repo.search_similar.assert_not_called()


@pytest.mark.asyncio
async def test_search_similar_fallback_when_sparse_empty(
    mock_llm, mock_vector_repo, mock_memory_repo
):
    """search_similar() is used when sparse vector is empty (BM25 not fitted yet)."""
    from app.domain.services.memory_service import MemoryService

    service = MemoryService(
        repository=mock_memory_repo,
        llm=mock_llm,
    )

    mock_settings = MagicMock()
    mock_settings.qdrant_use_hybrid_search = True

    with (
        patch(
            "app.domain.services.memory_service._get_vector_repo",
            return_value=mock_vector_repo,
        ),
        patch.object(
            MemoryService,
            "_generate_embedding",
            new=AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.domain.services.memory_service.MemoryService._generate_sparse_vector",
            return_value={},  # empty — BM25 not fitted
        ),
        patch(
            "app.core.config.get_settings",
            return_value=mock_settings,
        ),
    ):
        await service.retrieve_relevant(user_id="u1", context="test query")

    mock_vector_repo.search_hybrid.assert_not_called()
    mock_vector_repo.search_similar.assert_called_once()
