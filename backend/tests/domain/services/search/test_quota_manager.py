"""Tests for SearchQuotaManager.

Tests the search quota management pipeline: quota tracking, usage
recording, aggregate ratio calculation, health score extraction,
and in-memory fallback when Redis is unavailable.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.search.cost_router import QuotaStatus
from app.domain.services.search.quota_manager import (
    SearchQuotaManager,
    _PROVIDER_QUOTA_SETTINGS,
)


def _make_manager(redis_client: AsyncMock | None = None) -> SearchQuotaManager:
    """Create a SearchQuotaManager with mocked dependencies."""
    return SearchQuotaManager(
        redis_client=redis_client,
        intent_classifier=MagicMock(),
        cost_router=MagicMock(),
        dedup=MagicMock(),
    )


# --- _aggregate_remaining_ratio ---


class TestAggregateRemainingRatio:
    def test_all_full(self) -> None:
        quotas = {
            "tavily": QuotaStatus(used=0, limit=1000),
            "serper": QuotaStatus(used=0, limit=500),
        }
        assert SearchQuotaManager._aggregate_remaining_ratio(quotas) == 1.0

    def test_all_exhausted(self) -> None:
        quotas = {
            "tavily": QuotaStatus(used=1000, limit=1000),
            "serper": QuotaStatus(used=500, limit=500),
        }
        assert SearchQuotaManager._aggregate_remaining_ratio(quotas) == 0.0

    def test_partial_usage(self) -> None:
        quotas = {
            "tavily": QuotaStatus(used=500, limit=1000),
            "serper": QuotaStatus(used=250, limit=500),
        }
        assert SearchQuotaManager._aggregate_remaining_ratio(quotas) == 750 / 1500

    def test_unlimited_providers_excluded(self) -> None:
        quotas = {
            "tavily": QuotaStatus(used=500, limit=1000),
            "duckduckgo": QuotaStatus(used=100, limit=0),
        }
        assert SearchQuotaManager._aggregate_remaining_ratio(quotas) == 0.5

    def test_all_unlimited_returns_one(self) -> None:
        quotas = {
            "duckduckgo": QuotaStatus(used=0, limit=0),
            "bing": QuotaStatus(used=0, limit=0),
        }
        assert SearchQuotaManager._aggregate_remaining_ratio(quotas) == 1.0

    def test_empty_quotas(self) -> None:
        assert SearchQuotaManager._aggregate_remaining_ratio({}) == 1.0

    def test_over_limit_clamped_to_zero(self) -> None:
        quotas = {"tavily": QuotaStatus(used=1500, limit=1000)}
        assert SearchQuotaManager._aggregate_remaining_ratio(quotas) == 0.0


# --- _get_health_scores ---


class TestGetHealthScores:
    def test_from_context(self) -> None:
        scores = {"tavily": 0.8, "serper": 0.5}
        result = SearchQuotaManager._get_health_scores({"health_scores": scores})
        assert result == scores

    def test_no_context_returns_defaults(self) -> None:
        result = SearchQuotaManager._get_health_scores(None)
        for provider in _PROVIDER_QUOTA_SETTINGS:
            assert result[provider] == 1.0

    def test_empty_context_returns_defaults(self) -> None:
        result = SearchQuotaManager._get_health_scores({})
        assert all(v == 1.0 for v in result.values())


# --- _get_usage (Redis vs in-memory) ---


class TestGetUsage:
    @pytest.mark.asyncio()
    async def test_redis_available(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"42")
        manager = _make_manager(redis_client=redis)

        usage = await manager._get_usage("tavily")
        assert usage == 42

    @pytest.mark.asyncio()
    async def test_redis_returns_none(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        manager = _make_manager(redis_client=redis)

        usage = await manager._get_usage("tavily")
        assert usage == 0

    @pytest.mark.asyncio()
    async def test_redis_unavailable_falls_back(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        manager = _make_manager(redis_client=redis)
        manager._usage_counters["tavily"] = 15

        usage = await manager._get_usage("tavily")
        assert usage == 15

    @pytest.mark.asyncio()
    async def test_no_redis_uses_memory(self) -> None:
        manager = _make_manager(redis_client=None)
        manager._usage_counters["serper"] = 7

        usage = await manager._get_usage("serper")
        assert usage == 7


# --- _record_usage ---


class TestRecordUsage:
    @pytest.mark.asyncio()
    async def test_increments_in_memory(self) -> None:
        manager = _make_manager(redis_client=None)

        await manager._record_usage("tavily", 5)
        assert manager._usage_counters["tavily"] == 5

        await manager._record_usage("tavily", 3)
        assert manager._usage_counters["tavily"] == 8

    @pytest.mark.asyncio()
    async def test_writes_to_redis(self) -> None:
        redis = AsyncMock()
        redis.incrby = AsyncMock()
        redis.ttl = AsyncMock(return_value=-1)
        redis.expire = AsyncMock()
        manager = _make_manager(redis_client=redis)

        await manager._record_usage("tavily", 3)

        redis.incrby.assert_called_once()
        redis.expire.assert_called_once()

    @pytest.mark.asyncio()
    async def test_skips_ttl_if_already_set(self) -> None:
        redis = AsyncMock()
        redis.incrby = AsyncMock()
        redis.ttl = AsyncMock(return_value=86400)
        redis.expire = AsyncMock()
        manager = _make_manager(redis_client=redis)

        await manager._record_usage("serper", 1)

        redis.incrby.assert_called_once()
        redis.expire.assert_not_called()

    @pytest.mark.asyncio()
    async def test_redis_failure_still_updates_memory(self) -> None:
        redis = AsyncMock()
        redis.incrby = AsyncMock(side_effect=ConnectionError("Redis down"))
        manager = _make_manager(redis_client=redis)

        await manager._record_usage("tavily", 2)
        assert manager._usage_counters["tavily"] == 2


# --- get_quota_status ---


class TestGetQuotaStatus:
    @pytest.mark.asyncio()
    async def test_returns_all_providers(self) -> None:
        manager = _make_manager(redis_client=None)

        with patch("app.domain.services.search.quota_manager.get_settings") as mock_settings:
            settings_obj = MagicMock()
            settings_obj.search_quota_tavily = 1000
            settings_obj.search_quota_serper = 500
            settings_obj.search_quota_brave = 200
            settings_obj.search_quota_exa = 100
            settings_obj.search_quota_jina = 100
            mock_settings.return_value = settings_obj

            quotas = await manager.get_quota_status()

        assert "tavily" in quotas
        assert "serper" in quotas
        assert "duckduckgo" in quotas
        assert quotas["duckduckgo"].limit == 0
        assert quotas["tavily"].limit == 1000


# --- QuotaStatus ---


class TestQuotaStatus:
    def test_remaining_ratio_full(self) -> None:
        qs = QuotaStatus(used=0, limit=1000)
        assert qs.remaining_ratio == 1.0

    def test_remaining_ratio_half(self) -> None:
        qs = QuotaStatus(used=500, limit=1000)
        assert qs.remaining_ratio == 0.5

    def test_remaining_ratio_exhausted(self) -> None:
        qs = QuotaStatus(used=1000, limit=1000)
        assert qs.remaining_ratio == 0.0

    def test_remaining_ratio_unlimited(self) -> None:
        qs = QuotaStatus(used=999, limit=0)
        assert qs.remaining_ratio == 1.0

    def test_remaining_ratio_over_limit(self) -> None:
        qs = QuotaStatus(used=1500, limit=1000)
        assert qs.remaining_ratio == 0.0
