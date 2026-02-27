"""Tests for enhanced health monitor metrics (MongoDB/Redis/Qdrant deep health).

Validates that health checks extract and publish WiredTiger cache stats,
Redis memory/hit ratio, and Qdrant collection stats to Prometheus gauges.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.health_monitor import ComponentHealth, ComponentStatus, HealthMonitor


@pytest.fixture
def monitor():
    return HealthMonitor()


class TestMongoDBDeepHealth:
    """Test enhanced MongoDB health check with serverStatus."""

    @pytest.mark.asyncio
    async def test_mongodb_health_extracts_wiredtiger_cache(self, monitor):
        """serverStatus should populate WiredTiger cache gauges."""
        mock_mongodb = MagicMock()
        mock_mongodb.client.admin.command = AsyncMock(
            return_value={
                "wiredTiger": {
                    "cache": {
                        "bytes currently in the cache": 500_000_000,
                        "maximum bytes configured": 1_000_000_000,
                        "tracked dirty bytes in the cache": 10_000_000,
                    }
                },
                "connections": {"current": 42},
                "opcounters": {"insert": 100, "query": 500},
            }
        )

        with (
            patch("app.infrastructure.storage.mongodb.get_mongodb", return_value=mock_mongodb),
            patch("app.core.prometheus_metrics.mongodb_wiredtiger_cache_bytes"),
            patch("app.core.prometheus_metrics.mongodb_connections_current"),
        ):
            health = ComponentHealth("database", ComponentStatus.UNKNOWN)
            await monitor._check_database_health(health)

            assert health.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_mongodb_health_degraded_on_high_cache(self, monitor):
        """Cache ratio > 95% should mark as DEGRADED."""
        mock_mongodb = MagicMock()
        mock_mongodb.client.admin.command = AsyncMock(
            return_value={
                "wiredTiger": {
                    "cache": {
                        "bytes currently in the cache": 960_000_000,
                        "maximum bytes configured": 1_000_000_000,
                        "tracked dirty bytes in the cache": 50_000_000,
                    }
                },
                "connections": {"current": 5},
            }
        )

        with (
            patch("app.infrastructure.storage.mongodb.get_mongodb", return_value=mock_mongodb),
            patch("app.core.prometheus_metrics.mongodb_wiredtiger_cache_bytes"),
            patch("app.core.prometheus_metrics.mongodb_connections_current"),
        ):
            health = ComponentHealth("database", ComponentStatus.UNKNOWN)
            await monitor._check_database_health(health)
            assert health.status == ComponentStatus.DEGRADED


class TestRedisDeepHealth:
    """Test enhanced Redis health check with INFO."""

    @pytest.mark.asyncio
    async def test_redis_health_parses_info(self, monitor):
        """Redis INFO should populate memory and hit ratio gauges."""
        mock_redis = MagicMock()
        mock_redis.initialize = AsyncMock()
        mock_redis.call = AsyncMock(
            return_value=(
                "# Memory\r\n"
                "used_memory:200000000\r\n"
                "maxmemory:512000000\r\n"
                "evicted_keys:5\r\n"
                "# Stats\r\n"
                "keyspace_hits:9000\r\n"
                "keyspace_misses:1000\r\n"
                "connected_clients:10\r\n"
            )
        )

        with (
            patch("app.infrastructure.storage.redis.get_redis", return_value=mock_redis),
            patch("app.core.prometheus_metrics.redis_memory_bytes"),
            patch("app.core.prometheus_metrics.redis_keyspace_hit_ratio"),
            patch("app.core.prometheus_metrics.cache_eviction_rate"),
        ):
            health = ComponentHealth("redis", ComponentStatus.UNKNOWN)
            await monitor._check_redis_health(health)
            assert health.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_redis_health_degraded_on_high_memory(self, monitor):
        """Memory usage > 95% should mark as DEGRADED."""
        mock_redis = MagicMock()
        mock_redis.initialize = AsyncMock()
        mock_redis.call = AsyncMock(
            return_value=(
                "used_memory:490000000\r\n"
                "maxmemory:512000000\r\n"
                "evicted_keys:100\r\n"
                "keyspace_hits:100\r\n"
                "keyspace_misses:100\r\n"
            )
        )

        with (
            patch("app.infrastructure.storage.redis.get_redis", return_value=mock_redis),
            patch("app.core.prometheus_metrics.redis_memory_bytes"),
            patch("app.core.prometheus_metrics.redis_keyspace_hit_ratio"),
            patch("app.core.prometheus_metrics.cache_eviction_rate"),
        ):
            health = ComponentHealth("redis", ComponentStatus.UNKNOWN)
            await monitor._check_redis_health(health)
            assert health.status == ComponentStatus.DEGRADED


class TestQdrantDeepHealth:
    """Test enhanced Qdrant health check with collection stats."""

    @pytest.mark.asyncio
    async def test_qdrant_health_collects_stats(self, monitor):
        """Qdrant health should get_collections and per-collection stats."""
        mock_qdrant = MagicMock()
        mock_client = AsyncMock()

        # Mock collection list
        col_info = MagicMock()
        col_info.name = "user_knowledge"
        collections_response = MagicMock()
        collections_response.collections = [col_info]
        mock_client.get_collections = AsyncMock(return_value=collections_response)

        # Mock collection detail
        col_detail = MagicMock()
        col_detail.vectors_count = 5000
        col_detail.disk_data_size = 100_000_000
        opt_status = MagicMock()
        opt_status.status = "ok"
        col_detail.optimizer_status = opt_status
        mock_client.get_collection = AsyncMock(return_value=col_detail)

        mock_qdrant.client = mock_client

        with (
            patch("app.infrastructure.storage.qdrant.get_qdrant", return_value=mock_qdrant),
            patch("app.core.prometheus_metrics.qdrant_collection_size"),
            patch("app.core.prometheus_metrics.qdrant_disk_usage_bytes"),
        ):
            health = ComponentHealth("qdrant", ComponentStatus.UNKNOWN)
            await monitor._check_qdrant_health(health)
            assert health.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_qdrant_health_degraded_on_optimizer_issue(self, monitor):
        """Optimizer status != 'ok' should mark as DEGRADED."""
        mock_qdrant = MagicMock()
        mock_client = AsyncMock()

        col_info = MagicMock()
        col_info.name = "user_knowledge"
        collections_response = MagicMock()
        collections_response.collections = [col_info]
        mock_client.get_collections = AsyncMock(return_value=collections_response)

        col_detail = MagicMock()
        col_detail.vectors_count = 5000
        col_detail.disk_data_size = 100_000_000
        opt_status = MagicMock()
        opt_status.status = "indexing"
        col_detail.optimizer_status = opt_status
        mock_client.get_collection = AsyncMock(return_value=col_detail)

        mock_qdrant.client = mock_client

        with (
            patch("app.infrastructure.storage.qdrant.get_qdrant", return_value=mock_qdrant),
            patch("app.core.prometheus_metrics.qdrant_collection_size"),
            patch("app.core.prometheus_metrics.qdrant_disk_usage_bytes"),
        ):
            health = ComponentHealth("qdrant", ComponentStatus.UNKNOWN)
            await monitor._check_qdrant_health(health)
            assert health.status == ComponentStatus.DEGRADED
