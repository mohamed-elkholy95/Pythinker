"""Integration tests: SearchQuotaManager wraps SearchTool flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.search.cost_router import CostAwareSearchRouter
from app.domain.services.search.dedup_enhanced import EnhancedDedup
from app.domain.services.search.intent_classifier import QueryIntentClassifier
from app.domain.services.search.quota_manager import SearchQuotaManager


class TestQuotaManagerDedup:
    """Verify dedup works end-to-end inside SearchQuotaManager.route()."""

    @pytest.mark.asyncio()
    async def test_dedup_prevents_second_identical_call(self):
        """Second identical query should be caught by dedup."""
        mgr = SearchQuotaManager(
            redis_client=None,
            intent_classifier=QueryIntentClassifier(),
            cost_router=CostAwareSearchRouter(),
            dedup=EnhancedDedup(similarity_threshold=0.6),
        )

        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(
            return_value=MagicMock(
                success=True,
                data=MagicMock(results=["r1", "r2"]),
                message="ok",
            )
        )

        # First call succeeds
        r1 = await mgr.route("best laptop 2026", mock_engine)
        assert r1.success is True

        # Second identical call should be deduped
        r2 = await mgr.route("best laptop 2026", mock_engine)
        assert r2.success is False
        assert mock_engine.search.call_count == 1  # Only called once

    @pytest.mark.asyncio()
    async def test_different_queries_both_execute(self):
        """Two different queries should both make API calls."""
        mgr = SearchQuotaManager(
            redis_client=None,
            intent_classifier=QueryIntentClassifier(),
            cost_router=CostAwareSearchRouter(),
            dedup=EnhancedDedup(similarity_threshold=0.6),
        )

        mock_engine = AsyncMock()
        mock_engine.search = AsyncMock(
            return_value=MagicMock(
                success=True,
                data=MagicMock(results=["r1"]),
                message="ok",
            )
        )

        await mgr.route("best laptop 2026", mock_engine)
        await mgr.route("Python asyncio tutorial", mock_engine)

        assert mock_engine.search.call_count == 2


class TestFeatureFlagGating:
    """Verify SearchTool's quota_manager is gated by search_quota_manager_enabled."""

    def test_quota_manager_none_when_flag_off(self):
        """When feature flag is False, SearchTool._quota_manager should be None."""
        from unittest.mock import MagicMock

        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        # Feature flag defaults to False, so quota_manager should be None
        tool = SearchTool(search_engine=mock_engine)
        assert tool._quota_manager is None

    def test_quota_manager_initialized_when_flag_on(self):
        """When feature flag is True, SearchTool._quota_manager should be set."""
        from app.domain.services.tools.search import SearchTool

        mock_settings = MagicMock()
        mock_settings.search_quota_manager_enabled = True
        mock_settings.search_dedup_jaccard_threshold = 0.6
        mock_settings.max_search_api_calls_per_task = 15
        mock_settings.max_wide_research_calls_per_task = 2
        mock_settings.max_wide_research_queries = 3
        mock_settings.search_dedup_skip_existing = True

        with (
            patch("app.core.config.get_settings", return_value=mock_settings),
            patch("app.domain.services.search.quota_manager.get_search_quota_manager") as mock_factory,
        ):
            mock_factory.return_value = MagicMock()
            mock_engine = MagicMock()
            tool = SearchTool(search_engine=mock_engine)
            assert tool._quota_manager is not None
