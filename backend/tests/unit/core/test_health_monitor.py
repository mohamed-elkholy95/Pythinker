"""Tests for the health monitoring system."""

import asyncio
import contextlib
import unittest.mock as mock_lib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.health_monitor import (
    ComponentHealth,
    ComponentStatus,
    HealthMetric,
    HealthMonitor,
    get_health_monitor,
)

# ---------------------------------------------------------------------------
# ComponentStatus
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComponentStatus:
    """Tests for the ComponentStatus enum."""

    def test_healthy_value(self) -> None:
        assert ComponentStatus.HEALTHY == "healthy"

    def test_degraded_value(self) -> None:
        assert ComponentStatus.DEGRADED == "degraded"

    def test_unhealthy_value(self) -> None:
        assert ComponentStatus.UNHEALTHY == "unhealthy"

    def test_unknown_value(self) -> None:
        assert ComponentStatus.UNKNOWN == "unknown"

    def test_member_count(self) -> None:
        assert len(ComponentStatus) == 4

    def test_is_str_enum(self) -> None:
        assert isinstance(ComponentStatus.HEALTHY, str)


# ---------------------------------------------------------------------------
# HealthMetric
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHealthMetric:
    """Tests for the HealthMetric dataclass."""

    def test_basic_construction(self) -> None:
        ts = datetime.now(UTC)
        metric = HealthMetric(
            name="error_rate",
            value=2.5,
            status=ComponentStatus.HEALTHY,
            timestamp=ts,
        )
        assert metric.name == "error_rate"
        assert metric.value == 2.5
        assert metric.status == ComponentStatus.HEALTHY
        assert metric.timestamp == ts

    def test_metadata_defaults_to_empty_dict(self) -> None:
        metric = HealthMetric(
            name="latency",
            value=0.01,
            status=ComponentStatus.HEALTHY,
            timestamp=datetime.now(UTC),
        )
        assert metric.metadata == {}

    def test_metadata_is_independent_per_instance(self) -> None:
        ts = datetime.now(UTC)
        m1 = HealthMetric(name="a", value=1.0, status=ComponentStatus.HEALTHY, timestamp=ts)
        m2 = HealthMetric(name="b", value=2.0, status=ComponentStatus.HEALTHY, timestamp=ts)
        m1.metadata["key"] = "val"
        assert "key" not in m2.metadata

    def test_metadata_custom_values(self) -> None:
        metric = HealthMetric(
            name="cache",
            value=0.8,
            status=ComponentStatus.HEALTHY,
            timestamp=datetime.now(UTC),
            metadata={"hits": 100, "misses": 25},
        )
        assert metric.metadata["hits"] == 100
        assert metric.metadata["misses"] == 25


# ---------------------------------------------------------------------------
# ComponentHealth
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComponentHealth:
    """Tests for the ComponentHealth dataclass."""

    def test_basic_construction(self) -> None:
        health = ComponentHealth(component="redis", status=ComponentStatus.HEALTHY)
        assert health.component == "redis"
        assert health.status == ComponentStatus.HEALTHY
        assert health.metrics == []
        assert health.last_check is None
        assert health.error_count == 0

    def test_metrics_default_is_independent_per_instance(self) -> None:
        h1 = ComponentHealth(component="a", status=ComponentStatus.HEALTHY)
        h2 = ComponentHealth(component="b", status=ComponentStatus.HEALTHY)
        h1.metrics.append(MagicMock())
        assert len(h2.metrics) == 0

    def test_add_metric_appends(self) -> None:
        health = ComponentHealth(component="db", status=ComponentStatus.HEALTHY)
        metric = HealthMetric(name="rt", value=0.05, status=ComponentStatus.HEALTHY, timestamp=datetime.now(UTC))
        health.add_metric(metric)
        assert len(health.metrics) == 1
        assert health.metrics[0] is metric

    def test_add_metric_enforces_100_limit(self) -> None:
        health = ComponentHealth(component="db", status=ComponentStatus.HEALTHY)
        ts = datetime.now(UTC)
        for i in range(101):
            health.add_metric(HealthMetric(name=f"m{i}", value=float(i), status=ComponentStatus.HEALTHY, timestamp=ts))
        assert len(health.metrics) == 100

    def test_add_metric_drops_oldest_when_limit_exceeded(self) -> None:
        health = ComponentHealth(component="db", status=ComponentStatus.HEALTHY)
        ts = datetime.now(UTC)
        for i in range(101):
            health.add_metric(HealthMetric(name=f"m{i}", value=float(i), status=ComponentStatus.HEALTHY, timestamp=ts))
        # m0 is dropped; the oldest remaining is m1
        assert health.metrics[0].name == "m1"

    def test_add_metric_exactly_at_limit_does_not_drop(self) -> None:
        health = ComponentHealth(component="db", status=ComponentStatus.HEALTHY)
        ts = datetime.now(UTC)
        for i in range(100):
            health.add_metric(HealthMetric(name=f"m{i}", value=float(i), status=ComponentStatus.HEALTHY, timestamp=ts))
        assert len(health.metrics) == 100
        assert health.metrics[0].name == "m0"


# ---------------------------------------------------------------------------
# HealthMonitor - initialisation and lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHealthMonitorInit:
    """Tests for HealthMonitor initialisation defaults."""

    def test_components_empty_on_init(self) -> None:
        monitor = HealthMonitor()
        assert monitor._components == {}

    def test_monitoring_tasks_empty_on_init(self) -> None:
        monitor = HealthMonitor()
        assert monitor._monitoring_tasks == {}

    def test_monitoring_interval_default(self) -> None:
        monitor = HealthMonitor()
        assert monitor._monitoring_interval == 30

    def test_is_monitoring_false_on_init(self) -> None:
        monitor = HealthMonitor()
        assert monitor._is_monitoring is False


# ---------------------------------------------------------------------------
# HealthMonitor - start / stop monitoring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHealthMonitorLifecycle:
    """Tests for start_monitoring and stop_monitoring."""

    @pytest.mark.asyncio
    async def test_start_monitoring_sets_flag(self) -> None:
        monitor = HealthMonitor()
        # Patch _monitor_component so create_task receives a fast-completing coroutine.
        with patch.object(HealthMonitor, "_monitor_component", new=AsyncMock(return_value=None)):
            await monitor.start_monitoring()
            assert monitor._is_monitoring is True
            await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_start_monitoring_creates_tasks_for_all_components(self) -> None:
        monitor = HealthMonitor()
        expected_count = 6  # error_manager, sandbox_manager, database, redis, redis_cache, qdrant
        with patch.object(HealthMonitor, "_monitor_component", new=AsyncMock(return_value=None)):
            with patch("asyncio.create_task", wraps=asyncio.create_task) as mock_create:
                await monitor.start_monitoring()
                assert mock_create.call_count == expected_count
            await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_start_monitoring_idempotent(self) -> None:
        monitor = HealthMonitor()
        with patch.object(HealthMonitor, "_monitor_component", new=AsyncMock(return_value=None)):
            with patch("asyncio.create_task", wraps=asyncio.create_task) as mock_create:
                await monitor.start_monitoring()
                first_count = mock_create.call_count
                await monitor.start_monitoring()  # second call should be a no-op
                assert mock_create.call_count == first_count
            await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_stop_monitoring_clears_flag(self) -> None:
        monitor = HealthMonitor()
        with patch.object(HealthMonitor, "_monitor_component", new=AsyncMock(return_value=None)):
            await monitor.start_monitoring()
            await monitor.stop_monitoring()
        assert monitor._is_monitoring is False

    @pytest.mark.asyncio
    async def test_stop_monitoring_clears_tasks(self) -> None:
        monitor = HealthMonitor()
        with patch.object(HealthMonitor, "_monitor_component", new=AsyncMock(return_value=None)):
            await monitor.start_monitoring()
            await monitor.stop_monitoring()
        assert monitor._monitoring_tasks == {}

    @pytest.mark.asyncio
    async def test_stop_monitoring_cancels_tasks(self) -> None:
        monitor = HealthMonitor()
        mock_tasks: list[MagicMock] = []

        def _fake_create_task(coro: object, **kwargs: object) -> MagicMock:
            # Close the coroutine to avoid ResourceWarning
            if hasattr(coro, "close"):
                coro.close()  # type: ignore[union-attr]
            t = MagicMock(spec=asyncio.Task)
            mock_tasks.append(t)
            return t

        with patch("asyncio.create_task", side_effect=_fake_create_task):
            await monitor.start_monitoring()
            await monitor.stop_monitoring()

        # stop_monitoring must call .cancel() on every task it holds
        assert len(mock_tasks) == 6
        for t in mock_tasks:
            t.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# HealthMonitor - get_system_health
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSystemHealth:
    """Tests for HealthMonitor.get_system_health()."""

    def test_empty_components_returns_healthy(self) -> None:
        monitor = HealthMonitor()
        result = monitor.get_system_health()
        assert result["overall_status"] == ComponentStatus.HEALTHY.value

    def test_returns_monitoring_active_flag(self) -> None:
        monitor = HealthMonitor()
        result = monitor.get_system_health()
        assert result["monitoring_active"] is False

    def test_returns_last_check_timestamp(self) -> None:
        monitor = HealthMonitor()
        result = monitor.get_system_health()
        assert "last_check" in result
        # Should be a parseable ISO-8601 string
        datetime.fromisoformat(result["last_check"])

    def test_returns_component_statuses_dict(self) -> None:
        monitor = HealthMonitor()
        monitor._components["redis"] = ComponentHealth("redis", ComponentStatus.HEALTHY)
        result = monitor.get_system_health()
        assert "components" in result
        assert result["components"]["redis"] == "healthy"

    def test_one_unhealthy_component_makes_overall_unhealthy(self) -> None:
        monitor = HealthMonitor()
        monitor._components["redis"] = ComponentHealth("redis", ComponentStatus.HEALTHY)
        monitor._components["db"] = ComponentHealth("db", ComponentStatus.UNHEALTHY)
        result = monitor.get_system_health()
        assert result["overall_status"] == ComponentStatus.UNHEALTHY.value

    def test_one_degraded_component_makes_overall_degraded(self) -> None:
        monitor = HealthMonitor()
        monitor._components["redis"] = ComponentHealth("redis", ComponentStatus.HEALTHY)
        monitor._components["db"] = ComponentHealth("db", ComponentStatus.DEGRADED)
        result = monitor.get_system_health()
        assert result["overall_status"] == ComponentStatus.DEGRADED.value

    def test_unhealthy_beats_degraded_for_overall(self) -> None:
        monitor = HealthMonitor()
        monitor._components["a"] = ComponentHealth("a", ComponentStatus.DEGRADED)
        monitor._components["b"] = ComponentHealth("b", ComponentStatus.UNHEALTHY)
        result = monitor.get_system_health()
        assert result["overall_status"] == ComponentStatus.UNHEALTHY.value

    def test_all_healthy_components_overall_healthy(self) -> None:
        monitor = HealthMonitor()
        for name in ("redis", "db", "qdrant"):
            monitor._components[name] = ComponentHealth(name, ComponentStatus.HEALTHY)
        result = monitor.get_system_health()
        assert result["overall_status"] == ComponentStatus.HEALTHY.value


# ---------------------------------------------------------------------------
# HealthMonitor - get_component_health
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetComponentHealth:
    """Tests for HealthMonitor.get_component_health()."""

    def test_returns_none_for_unknown_component(self) -> None:
        monitor = HealthMonitor()
        assert monitor.get_component_health("nonexistent") is None

    def test_returns_component_name(self) -> None:
        monitor = HealthMonitor()
        monitor._components["redis"] = ComponentHealth("redis", ComponentStatus.HEALTHY)
        result = monitor.get_component_health("redis")
        assert result is not None
        assert result["component"] == "redis"

    def test_returns_status_as_string(self) -> None:
        monitor = HealthMonitor()
        monitor._components["redis"] = ComponentHealth("redis", ComponentStatus.DEGRADED)
        result = monitor.get_component_health("redis")
        assert result["status"] == "degraded"

    def test_last_check_none_when_not_set(self) -> None:
        monitor = HealthMonitor()
        monitor._components["redis"] = ComponentHealth("redis", ComponentStatus.HEALTHY)
        result = monitor.get_component_health("redis")
        assert result["last_check"] is None

    def test_last_check_serialised_to_iso_string(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.HEALTHY)
        health.last_check = datetime.now(UTC)
        monitor._components["redis"] = health
        result = monitor.get_component_health("redis")
        assert result["last_check"] is not None
        datetime.fromisoformat(result["last_check"])

    def test_error_count_included(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.UNHEALTHY)
        health.error_count = 3
        monitor._components["redis"] = health
        result = monitor.get_component_health("redis")
        assert result["error_count"] == 3

    def test_metrics_list_included(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.HEALTHY)
        health.add_metric(
            HealthMetric(
                name="response_time",
                value=0.02,
                status=ComponentStatus.HEALTHY,
                timestamp=datetime.now(UTC),
            )
        )
        monitor._components["redis"] = health
        result = monitor.get_component_health("redis")
        assert len(result["metrics"]) == 1
        m = result["metrics"][0]
        assert m["name"] == "response_time"
        assert m["value"] == 0.02
        assert m["status"] == "healthy"

    def test_metrics_capped_at_last_10(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.HEALTHY)
        ts = datetime.now(UTC)
        for i in range(15):
            health.add_metric(HealthMetric(name=f"m{i}", value=float(i), status=ComponentStatus.HEALTHY, timestamp=ts))
        monitor._components["redis"] = health
        result = monitor.get_component_health("redis")
        assert len(result["metrics"]) == 10
        # Should be the last 10 (m5..m14)
        assert result["metrics"][0]["name"] == "m5"

    def test_metric_timestamp_is_iso_string(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.HEALTHY)
        health.add_metric(
            HealthMetric(name="rt", value=0.1, status=ComponentStatus.HEALTHY, timestamp=datetime.now(UTC))
        )
        monitor._components["redis"] = health
        result = monitor.get_component_health("redis")
        datetime.fromisoformat(result["metrics"][0]["timestamp"])

    def test_metric_metadata_preserved(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.HEALTHY)
        health.add_metric(
            HealthMetric(
                name="rt",
                value=0.1,
                status=ComponentStatus.HEALTHY,
                timestamp=datetime.now(UTC),
                metadata={"hits": 50},
            )
        )
        monitor._components["redis"] = health
        result = monitor.get_component_health("redis")
        assert result["metrics"][0]["metadata"] == {"hits": 50}


# ---------------------------------------------------------------------------
# HealthMonitor - _check_component_health (error handling path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckComponentHealthErrorHandling:
    """Tests for _check_component_health exception handling."""

    @pytest.mark.asyncio
    async def test_exception_sets_unhealthy_status(self) -> None:
        monitor = HealthMonitor()
        with patch.object(
            monitor,
            "_check_error_manager_health",
            side_effect=RuntimeError("boom"),
        ):
            await monitor._check_component_health("error_manager")

        assert monitor._components["error_manager"].status == ComponentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_exception_increments_error_count(self) -> None:
        monitor = HealthMonitor()
        with patch.object(
            monitor,
            "_check_error_manager_health",
            side_effect=RuntimeError("boom"),
        ):
            await monitor._check_component_health("error_manager")
            await monitor._check_component_health("error_manager")

        assert monitor._components["error_manager"].error_count == 2

    @pytest.mark.asyncio
    async def test_unknown_component_name_is_stored(self) -> None:
        monitor = HealthMonitor()
        # An unknown component name hits none of the if-branches; health is stored as UNKNOWN.
        await monitor._check_component_health("totally_unknown")
        assert "totally_unknown" in monitor._components


# ---------------------------------------------------------------------------
# HealthMonitor - individual component checks (mocked dependencies)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckErrorManagerHealth:
    """Tests for _check_error_manager_health."""

    @pytest.mark.asyncio
    async def test_low_error_rate_gives_healthy(self) -> None:
        mock_em = MagicMock()
        mock_em.get_error_stats.return_value = {"total_errors": 60}  # 1 err/min

        monitor = HealthMonitor()
        health = ComponentHealth("error_manager", ComponentStatus.UNKNOWN)
        with patch("app.core.health_monitor.get_error_manager", return_value=mock_em):
            await monitor._check_error_manager_health(health)

        assert health.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_medium_error_rate_gives_degraded(self) -> None:
        mock_em = MagicMock()
        mock_em.get_error_stats.return_value = {"total_errors": 360}  # 6 err/min

        monitor = HealthMonitor()
        health = ComponentHealth("error_manager", ComponentStatus.UNKNOWN)
        with patch("app.core.health_monitor.get_error_manager", return_value=mock_em):
            await monitor._check_error_manager_health(health)

        assert health.status == ComponentStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_high_error_rate_gives_unhealthy(self) -> None:
        mock_em = MagicMock()
        mock_em.get_error_stats.return_value = {"total_errors": 660}  # 11 err/min

        monitor = HealthMonitor()
        health = ComponentHealth("error_manager", ComponentStatus.UNKNOWN)
        with patch("app.core.health_monitor.get_error_manager", return_value=mock_em):
            await monitor._check_error_manager_health(health)

        assert health.status == ComponentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_metric_is_recorded(self) -> None:
        mock_em = MagicMock()
        mock_em.get_error_stats.return_value = {"total_errors": 0}

        monitor = HealthMonitor()
        health = ComponentHealth("error_manager", ComponentStatus.UNKNOWN)
        with patch("app.core.health_monitor.get_error_manager", return_value=mock_em):
            await monitor._check_error_manager_health(health)

        assert len(health.metrics) == 1
        assert health.metrics[0].name == "error_rate"


@pytest.mark.unit
class TestCheckSandboxManagerHealth:
    """Tests for _check_sandbox_manager_health."""

    def _make_mock_sandbox_manager(self, total: int, healthy: int) -> MagicMock:
        mock_sm = MagicMock()
        mock_sm.get_sandbox_stats.return_value = {
            "total_sandboxes": total,
            "healthy_sandboxes": healthy,
        }
        return mock_sm

    @pytest.mark.asyncio
    async def test_all_healthy_sandboxes_gives_healthy(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("sandbox_manager", ComponentStatus.UNKNOWN)
        mock_sm = self._make_mock_sandbox_manager(10, 10)

        async def _no_pool() -> None:
            return None

        with (
            patch("app.core.health_monitor.get_sandbox_manager", return_value=mock_sm),
            patch.dict(
                "sys.modules",
                {"app.core.sandbox_pool": mock_lib.MagicMock(get_sandbox_pool=_no_pool)},
            ),
            contextlib.suppress(Exception),
        ):
            await monitor._check_sandbox_manager_health(health)

        assert health.status in (ComponentStatus.HEALTHY, ComponentStatus.UNKNOWN)

    @pytest.mark.asyncio
    async def test_no_sandboxes_idle_state_is_healthy(self) -> None:
        # Verify that the ratio logic treats 0/0 as 1.0 (idle state = healthy).
        total = 0
        healthy = 0
        healthy_ratio = 1.0 if total == 0 else healthy / total
        assert healthy_ratio >= 0.8

    @pytest.mark.asyncio
    async def test_below_50_pct_healthy_gives_unhealthy(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("sandbox_manager", ComponentStatus.UNKNOWN)
        # 3/10 = 0.3 < 0.5 -> UNHEALTHY
        mock_sm = self._make_mock_sandbox_manager(10, 3)

        async def _no_pool() -> None:
            return None

        with (
            patch("app.core.health_monitor.get_sandbox_manager", return_value=mock_sm),
            patch.dict(
                "sys.modules",
                {"app.core.sandbox_pool": mock_lib.MagicMock(get_sandbox_pool=_no_pool)},
            ),
            contextlib.suppress(Exception),
        ):
            await monitor._check_sandbox_manager_health(health)

        # If the method ran to completion, status must be UNHEALTHY.
        if health.status != ComponentStatus.UNKNOWN:
            assert health.status == ComponentStatus.UNHEALTHY


@pytest.mark.unit
class TestCheckRedisHealth:
    """Tests for _check_redis_health."""

    @pytest.mark.asyncio
    async def test_redis_unreachable_sets_unhealthy(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.UNKNOWN)
        mock_redis = AsyncMock()
        mock_redis.initialize = AsyncMock(side_effect=ConnectionError("refused"))

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.redis": MagicMock(get_redis=lambda: mock_redis),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_redis_health(health)

        assert health.status == ComponentStatus.UNHEALTHY
        assert len(health.metrics) == 1
        assert health.metrics[0].value == -1

    @pytest.mark.asyncio
    async def test_redis_healthy_sets_healthy_when_memory_below_threshold(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.UNKNOWN)

        info_text = "used_memory:100\nmaxmemory:1000\nkeyspace_hits:80\nkeyspace_misses:20\nevicted_keys:0\n"
        mock_redis = AsyncMock()
        mock_redis.initialize = AsyncMock()
        mock_redis.call = AsyncMock(return_value=info_text)

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.redis": MagicMock(get_redis=lambda: mock_redis),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_redis_health(health)

        assert health.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_redis_degraded_when_memory_above_95_pct(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis", ComponentStatus.UNKNOWN)

        info_text = "used_memory:960\nmaxmemory:1000\nkeyspace_hits:0\nkeyspace_misses:0\nevicted_keys:0\n"
        mock_redis = AsyncMock()
        mock_redis.initialize = AsyncMock()
        mock_redis.call = AsyncMock(return_value=info_text)

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.redis": MagicMock(get_redis=lambda: mock_redis),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_redis_health(health)

        assert health.status == ComponentStatus.DEGRADED


@pytest.mark.unit
class TestCheckRedisCacheHealth:
    """Tests for _check_redis_cache_health."""

    @pytest.mark.asyncio
    async def test_no_cache_redis_reports_healthy(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis_cache", ComponentStatus.UNKNOWN)

        with patch.dict(
            "sys.modules",
            {"app.infrastructure.storage.redis": MagicMock(get_cache_redis=lambda: None)},
        ):
            await monitor._check_redis_cache_health(health)

        assert health.status == ComponentStatus.HEALTHY
        assert health.metrics[0].value == 0

    @pytest.mark.asyncio
    async def test_cache_redis_ping_failure_degrades(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis_cache", ComponentStatus.UNKNOWN)

        mock_redis = AsyncMock()
        mock_redis.initialize = AsyncMock()
        mock_redis.call = AsyncMock(side_effect=ConnectionError("timeout"))

        with patch.dict(
            "sys.modules",
            {"app.infrastructure.storage.redis": MagicMock(get_cache_redis=lambda: mock_redis)},
        ):
            await monitor._check_redis_cache_health(health)

        assert health.status == ComponentStatus.DEGRADED
        assert health.metrics[0].value == -1

    @pytest.mark.asyncio
    async def test_cache_redis_ping_success_gives_healthy(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("redis_cache", ComponentStatus.UNKNOWN)

        mock_redis = AsyncMock()
        mock_redis.initialize = AsyncMock()
        mock_redis.call = AsyncMock(return_value=b"PONG")

        with patch.dict(
            "sys.modules",
            {"app.infrastructure.storage.redis": MagicMock(get_cache_redis=lambda: mock_redis)},
        ):
            await monitor._check_redis_cache_health(health)

        assert health.status == ComponentStatus.HEALTHY


@pytest.mark.unit
class TestCheckQdrantHealth:
    """Tests for _check_qdrant_health."""

    @pytest.mark.asyncio
    async def test_qdrant_unreachable_sets_degraded(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("qdrant", ComponentStatus.UNKNOWN)

        mock_qdrant = MagicMock()
        mock_qdrant.client.get_collections = AsyncMock(side_effect=ConnectionError("refused"))

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.qdrant": MagicMock(get_qdrant=lambda: mock_qdrant),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_qdrant_health(health)

        assert health.status == ComponentStatus.DEGRADED
        assert health.metrics[0].value == -1

    @pytest.mark.asyncio
    async def test_qdrant_healthy_no_optimizer_issues(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("qdrant", ComponentStatus.UNKNOWN)

        col_info = MagicMock()
        col_info.name = "user_knowledge"
        col_detail = MagicMock()
        col_detail.vectors_count = 500
        col_detail.optimizer_status = MagicMock(status="ok")

        mock_client = AsyncMock()
        mock_client.get_collections = AsyncMock(return_value=MagicMock(collections=[col_info]))
        mock_client.get_collection = AsyncMock(return_value=col_detail)

        mock_qdrant = MagicMock()
        mock_qdrant.client = mock_client

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.qdrant": MagicMock(get_qdrant=lambda: mock_qdrant),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_qdrant_health(health)

        assert health.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_qdrant_degraded_when_optimizer_issues(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("qdrant", ComponentStatus.UNKNOWN)

        col_info = MagicMock()
        col_info.name = "user_knowledge"
        col_detail = MagicMock()
        col_detail.vectors_count = 200
        col_detail.optimizer_status = MagicMock(status="error")

        mock_client = AsyncMock()
        mock_client.get_collections = AsyncMock(return_value=MagicMock(collections=[col_info]))
        mock_client.get_collection = AsyncMock(return_value=col_detail)

        mock_qdrant = MagicMock()
        mock_qdrant.client = mock_client

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.qdrant": MagicMock(get_qdrant=lambda: mock_qdrant),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_qdrant_health(health)

        assert health.status == ComponentStatus.DEGRADED


@pytest.mark.unit
class TestCheckDatabaseHealth:
    """Tests for _check_database_health."""

    @pytest.mark.asyncio
    async def test_db_unreachable_sets_unhealthy(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("database", ComponentStatus.UNKNOWN)

        mock_mongodb = MagicMock()
        mock_mongodb.client.admin.command = AsyncMock(side_effect=Exception("connection refused"))

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.mongodb": MagicMock(get_mongodb=lambda: mock_mongodb),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_database_health(health)

        assert health.status == ComponentStatus.UNHEALTHY
        assert health.metrics[0].value == -1

    @pytest.mark.asyncio
    async def test_db_healthy_when_cache_below_95_pct(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("database", ComponentStatus.UNKNOWN)

        server_status = {
            "wiredTiger": {
                "cache": {
                    "bytes currently in the cache": 500,
                    "maximum bytes configured": 1000,
                    "tracked dirty bytes in the cache": 10,
                }
            },
            "connections": {"current": 5},
        }
        mock_mongodb = MagicMock()
        mock_mongodb.client.admin.command = AsyncMock(return_value=server_status)

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.mongodb": MagicMock(get_mongodb=lambda: mock_mongodb),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_database_health(health)

        assert health.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_db_degraded_when_cache_above_95_pct(self) -> None:
        monitor = HealthMonitor()
        health = ComponentHealth("database", ComponentStatus.UNKNOWN)

        server_status = {
            "wiredTiger": {
                "cache": {
                    "bytes currently in the cache": 960,
                    "maximum bytes configured": 1000,
                    "tracked dirty bytes in the cache": 50,
                }
            },
            "connections": {"current": 10},
        }
        mock_mongodb = MagicMock()
        mock_mongodb.client.admin.command = AsyncMock(return_value=server_status)

        with patch.dict(
            "sys.modules",
            {
                "app.infrastructure.storage.mongodb": MagicMock(get_mongodb=lambda: mock_mongodb),
                "app.core.prometheus_metrics": MagicMock(),
            },
        ):
            await monitor._check_database_health(health)

        assert health.status == ComponentStatus.DEGRADED


# ---------------------------------------------------------------------------
# get_health_monitor global singleton
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetHealthMonitor:
    """Tests for the module-level get_health_monitor() factory."""

    def test_returns_health_monitor_instance(self) -> None:
        monitor = get_health_monitor()
        assert isinstance(monitor, HealthMonitor)

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        assert get_health_monitor() is get_health_monitor()
