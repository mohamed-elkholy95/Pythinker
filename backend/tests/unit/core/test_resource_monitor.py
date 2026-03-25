"""Tests for core resource monitor."""

from datetime import UTC, datetime

import pytest

from app.core.resource_monitor import (
    ContainerResources,
    ResourceMonitor,
    get_resource_monitor,
)


@pytest.mark.unit
class TestContainerResources:
    """Tests for ContainerResources model."""

    def test_construction(self) -> None:
        now = datetime.now(UTC)
        cr = ContainerResources(
            cpu_percent=45.2,
            memory_used_mb=512.0,
            memory_percent=25.0,
            timestamp=now,
        )
        assert cr.cpu_percent == 45.2
        assert cr.memory_used_mb == 512.0
        assert cr.memory_percent == 25.0
        assert cr.timestamp == now


@pytest.mark.unit
class TestResourceMonitor:
    """Tests for ResourceMonitor."""

    def test_initial_state(self) -> None:
        rm = ResourceMonitor()
        assert rm.get_latest_snapshot("nonexistent") is None
        assert rm.get_resource_history("nonexistent") == []
        assert rm.get_average_usage("nonexistent") is None

    def test_get_latest_snapshot_with_data(self) -> None:
        rm = ResourceMonitor()
        now = datetime.now(UTC)
        snapshot = ContainerResources(
            cpu_percent=10.0,
            memory_used_mb=256.0,
            memory_percent=12.5,
            timestamp=now,
        )
        rm._resource_history["sess1"].append(snapshot)
        assert rm.get_latest_snapshot("sess1") == snapshot

    def test_get_resource_history(self) -> None:
        rm = ResourceMonitor()
        now = datetime.now(UTC)
        snapshots = [
            ContainerResources(cpu_percent=i * 10.0, memory_used_mb=100.0, memory_percent=5.0, timestamp=now)
            for i in range(5)
        ]
        rm._resource_history["sess1"] = snapshots
        assert rm.get_resource_history("sess1") == snapshots

    def test_get_average_usage(self) -> None:
        rm = ResourceMonitor()
        now = datetime.now(UTC)
        rm._resource_history["sess1"] = [
            ContainerResources(cpu_percent=10.0, memory_used_mb=100.0, memory_percent=5.0, timestamp=now),
            ContainerResources(cpu_percent=30.0, memory_used_mb=300.0, memory_percent=15.0, timestamp=now),
        ]
        avg = rm.get_average_usage("sess1")
        assert avg is not None
        assert avg["avg_cpu_percent"] == 20.0
        assert avg["avg_memory_mb"] == 200.0
        assert avg["peak_cpu_percent"] == 30.0
        assert avg["peak_memory_mb"] == 300.0

    def test_calculate_cpu_percent_valid(self) -> None:
        rm = ResourceMonitor()
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200},
                "system_cpu_usage": 10000,
                "online_cpus": 4,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 9000,
            },
        }
        result = rm._calculate_cpu_percent(stats)
        # (200-100) / (10000-9000) * 4 * 100 = 40.0
        assert result == 40.0

    def test_calculate_cpu_percent_zero_delta(self) -> None:
        rm = ResourceMonitor()
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 1000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 1000,
            },
        }
        result = rm._calculate_cpu_percent(stats)
        assert result == 0.0

    def test_calculate_cpu_percent_missing_keys(self) -> None:
        rm = ResourceMonitor()
        result = rm._calculate_cpu_percent({})
        assert result == 0.0


@pytest.mark.unit
class TestGetResourceMonitor:
    """Tests for global resource monitor getter."""

    def test_returns_resource_monitor(self) -> None:
        rm = get_resource_monitor()
        assert isinstance(rm, ResourceMonitor)

    def test_returns_same_instance(self) -> None:
        rm1 = get_resource_monitor()
        rm2 = get_resource_monitor()
        assert rm1 is rm2
