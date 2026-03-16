"""Tests for SearchQuotaManager orchestration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.search.cost_router import CostAwareSearchRouter, QuotaStatus
from app.domain.services.search.dedup_enhanced import EnhancedDedup
from app.domain.services.search.intent_classifier import QueryIntentClassifier, SearchIntent
from app.domain.services.search.quota_manager import SearchQuotaManager


@pytest.fixture()
def mock_classifier():
    clf = MagicMock(spec=QueryIntentClassifier)
    clf.classify.return_value = SearchIntent.STANDARD
    return clf


@pytest.fixture()
def mock_router():
    router = MagicMock(spec=CostAwareSearchRouter)
    router.select_provider.return_value = ("serper", "basic")
    return router


@pytest.fixture()
def mock_dedup():
    dedup = MagicMock(spec=EnhancedDedup)
    dedup.is_duplicate.return_value = False
    return dedup


@pytest.fixture()
def manager(mock_classifier, mock_router, mock_dedup):
    return SearchQuotaManager(
        redis_client=None,
        intent_classifier=mock_classifier,
        cost_router=mock_router,
        dedup=mock_dedup,
    )


class TestQuotaManagerInit:
    """Test initialization and defaults."""

    def test_creates_with_no_redis(self, mock_classifier, mock_router, mock_dedup):
        mgr = SearchQuotaManager(
            redis_client=None,
            intent_classifier=mock_classifier,
            cost_router=mock_router,
            dedup=mock_dedup,
        )
        assert mgr is not None

    def test_session_queries_starts_empty(self, manager):
        assert manager._session_queries == []


class TestQuotaManagerRoute:
    """Test the route() orchestration flow."""

    @pytest.mark.asyncio()
    async def test_calls_classifier(self, manager, mock_classifier):
        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(return_value=MagicMock(success=True, data=MagicMock(results=[])))

        await manager.route("test query", mock_engine)
        mock_classifier.classify.assert_called_once()

    @pytest.mark.asyncio()
    async def test_dedup_blocks_duplicate(self, manager, mock_dedup):
        mock_dedup.is_duplicate.return_value = True
        mock_engine = AsyncMock()

        result = await manager.route("duplicate query", mock_engine)
        # Should return early with dedup message
        assert result.success is False
        assert (
            "duplicate" in result.message.lower()
            or "already" in result.message.lower()
            or "similar" in result.message.lower()
        )
        mock_engine.search.assert_not_called()

    @pytest.mark.asyncio()
    async def test_records_query_after_search(self, manager):
        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(return_value=MagicMock(success=True, data=MagicMock(results=["r1"])))

        await manager.route("unique query", mock_engine)
        assert "unique query" in manager._session_queries

    @pytest.mark.asyncio()
    async def test_records_usage_counter(self, manager, mock_router):
        mock_router.select_provider.return_value = ("serper", "basic")
        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(return_value=MagicMock(success=True, data=MagicMock(results=["r"])))

        await manager.route("test query", mock_engine)
        # In-memory counter should be incremented
        assert manager._usage_counters.get("serper", 0) >= 1


class TestQuotaManagerGetQuotaStatus:
    """Test quota status retrieval."""

    @pytest.mark.asyncio()
    async def test_returns_all_providers(self, manager):
        status = await manager.get_quota_status()
        assert isinstance(status, dict)
        assert "tavily" in status
        assert isinstance(status["tavily"], QuotaStatus)

    @pytest.mark.asyncio()
    async def test_reflects_usage(self, manager, mock_router):
        mock_router.select_provider.return_value = ("tavily", "basic")
        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(return_value=MagicMock(success=True, data=MagicMock(results=["r"])))

        await manager.route("test", mock_engine)
        status = await manager.get_quota_status()
        assert status["tavily"].used >= 1
