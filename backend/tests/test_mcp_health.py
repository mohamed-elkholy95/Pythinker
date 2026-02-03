"""Tests for MCP health monitoring enhancements."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.tools.mcp import (
    MCPClientManager,
    MCPHealthMonitor,
    ServerHealth,
    ToolUsageStats,
)


class TestServerHealth:
    """Tests for ServerHealth dataclass."""

    def test_default_initialization(self):
        """Test ServerHealth default values."""
        health = ServerHealth(server_name="test-server")

        assert health.server_name == "test-server"
        assert health.healthy is True
        assert health.degraded is False
        assert health.priority == 100
        assert health.success_rate == 1.0
        assert health.avg_response_time_ms == 0.0

    def test_record_response_time(self):
        """Test response time tracking."""
        health = ServerHealth(server_name="test-server")

        health.record_response_time(100.0)
        health.record_response_time(200.0)
        health.record_response_time(300.0)

        assert health.avg_response_time_ms == 200.0
        assert len(health.response_time_samples) == 3

    def test_response_time_samples_limited(self):
        """Test that response time samples are limited."""
        health = ServerHealth(server_name="test-server")
        health.max_response_samples = 5

        for i in range(10):
            health.record_response_time(float(i * 100))

        assert len(health.response_time_samples) == 5
        # Should keep last 5: 500, 600, 700, 800, 900
        assert health.response_time_samples == [500.0, 600.0, 700.0, 800.0, 900.0]

    def test_record_success(self):
        """Test recording successful operations."""
        health = ServerHealth(server_name="test-server")

        health.record_success()
        health.record_success()
        health.record_success()

        assert health.success_count == 3
        assert health.failure_count == 0
        assert health.success_rate == 1.0

    def test_record_failure(self):
        """Test recording failed operations."""
        health = ServerHealth(server_name="test-server")

        health.record_success()
        health.record_failure()

        assert health.success_count == 1
        assert health.failure_count == 1
        assert health.success_rate == 0.5

    def test_degraded_detection(self):
        """Test degraded state detection based on success rate."""
        health = ServerHealth(server_name="test-server")

        # 9 successes, 1 failure = 90% = not degraded
        for _ in range(9):
            health.record_success()
        health.record_failure()

        assert health.degraded is False

        # Add more failures to drop below 90%
        health.record_failure()
        assert health.degraded is True

    def test_priority_calculation(self):
        """Test priority calculation based on success rate."""
        health = ServerHealth(server_name="test-server")

        # 100% success rate = priority 100
        for _ in range(10):
            health.record_success()
        assert health.priority == 100

        # Add failures to reduce success rate
        for _ in range(10):
            health.record_failure()
        # Now 50% success rate = priority 50
        assert health.priority == 50

    def test_priority_penalized_for_slow_response(self):
        """Test that slow response times reduce priority."""
        health = ServerHealth(server_name="test-server")

        # Good success rate
        for _ in range(10):
            health.record_success()

        # But slow response times (> 2 seconds)
        health.record_response_time(3000.0)  # 3 seconds
        health._update_reliability()

        # Priority should be reduced
        assert health.priority < 100

    def test_to_dict_serialization(self):
        """Test conversion to dictionary."""
        health = ServerHealth(server_name="test-server")
        health.record_success()
        health.record_response_time(150.0)

        result = health.to_dict()

        assert result["server_name"] == "test-server"
        assert result["healthy"] is True
        assert result["success_rate"] == 100.0
        assert result["avg_response_time_ms"] == 150.0


class TestToolUsageStats:
    """Tests for ToolUsageStats dataclass."""

    def test_default_initialization(self):
        """Test ToolUsageStats default values."""
        stats = ToolUsageStats(tool_name="search")

        assert stats.tool_name == "search"
        assert stats.call_count == 0
        assert stats.success_rate == 1.0
        assert stats.is_reliable is True

    def test_record_call_success(self):
        """Test recording successful calls."""
        stats = ToolUsageStats(tool_name="search")

        stats.record_call(success=True, duration_ms=100.0)

        assert stats.call_count == 1
        assert stats.success_count == 1
        assert stats.total_duration_ms == 100.0
        assert stats.min_duration_ms == 100.0
        assert stats.max_duration_ms == 100.0
        assert stats.last_used is not None

    def test_record_call_failure(self):
        """Test recording failed calls."""
        stats = ToolUsageStats(tool_name="search")

        stats.record_call(success=False, duration_ms=50.0, error="Connection refused")

        assert stats.call_count == 1
        assert stats.failure_count == 1
        assert stats.last_error == "Connection refused"

    def test_record_call_timeout(self):
        """Test recording timeout calls."""
        stats = ToolUsageStats(tool_name="search")

        stats.record_call(success=False, duration_ms=30000.0, timeout=True)

        assert stats.timeout_count == 1
        assert stats.failure_count == 1

    def test_avg_duration_calculation(self):
        """Test average duration calculation."""
        stats = ToolUsageStats(tool_name="search")

        stats.record_call(success=True, duration_ms=100.0)
        stats.record_call(success=True, duration_ms=200.0)
        stats.record_call(success=True, duration_ms=300.0)

        assert stats.avg_duration_ms == 200.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = ToolUsageStats(tool_name="search")

        stats.record_call(success=True, duration_ms=100.0)
        stats.record_call(success=True, duration_ms=100.0)
        stats.record_call(success=False, duration_ms=100.0)

        assert stats.success_rate == pytest.approx(0.666, abs=0.01)

    def test_is_reliable_threshold(self):
        """Test reliability threshold."""
        stats = ToolUsageStats(tool_name="search")

        # 90% success rate = reliable
        for _ in range(9):
            stats.record_call(success=True, duration_ms=100.0)
        stats.record_call(success=False, duration_ms=100.0)

        assert stats.is_reliable is True

        # Add more failures to drop below 90%
        stats.record_call(success=False, duration_ms=100.0)
        assert stats.is_reliable is False

    def test_to_dict_serialization(self):
        """Test conversion to dictionary."""
        stats = ToolUsageStats(tool_name="search")
        stats.record_call(success=True, duration_ms=150.0)

        result = stats.to_dict()

        assert result["tool_name"] == "search"
        assert result["call_count"] == 1
        assert result["success_rate"] == 100.0
        assert result["avg_duration_ms"] == 150.0
        assert result["is_reliable"] is True


class TestMCPClientManagerHealthMethods:
    """Tests for MCPClientManager health-related methods."""

    def test_record_tool_usage_creates_stats(self):
        """Test that record_tool_usage creates stats for new tools."""
        manager = MCPClientManager(config=None)

        manager.record_tool_usage("new_tool", success=True, duration_ms=100.0)

        assert "new_tool" in manager._tool_usage
        assert manager._tool_usage["new_tool"].call_count == 1

    def test_record_tool_usage_with_server(self):
        """Test recording tool usage with server metrics."""
        manager = MCPClientManager(config=None)
        manager._server_health["test-server"] = ServerHealth(server_name="test-server")

        manager.record_tool_usage(
            "tool1",
            success=True,
            duration_ms=150.0,
            server_name="test-server",
        )

        # Tool stats updated
        assert manager._tool_usage["tool1"].call_count == 1

        # Server health updated
        health = manager._server_health["test-server"]
        assert health.success_count == 1
        assert health.avg_response_time_ms == 150.0

    def test_record_tool_usage_failure_with_error(self):
        """Test recording failed tool usage with error."""
        manager = MCPClientManager(config=None)
        manager._server_health["test-server"] = ServerHealth(server_name="test-server")

        manager.record_tool_usage(
            "tool1",
            success=False,
            duration_ms=50.0,
            error="Timeout",
            timeout=True,
            server_name="test-server",
        )

        stats = manager._tool_usage["tool1"]
        assert stats.failure_count == 1
        assert stats.timeout_count == 1
        assert stats.last_error == "Timeout"

    def test_get_reliable_tools(self):
        """Test getting list of reliable tools."""
        manager = MCPClientManager(config=None)

        # Add a reliable tool (95% success rate)
        manager._tool_usage["reliable"] = ToolUsageStats(tool_name="reliable")
        for _ in range(19):
            manager._tool_usage["reliable"].record_call(success=True, duration_ms=100.0)
        manager._tool_usage["reliable"].record_call(success=False, duration_ms=100.0)

        # Add an unreliable tool (50% success rate)
        manager._tool_usage["unreliable"] = ToolUsageStats(tool_name="unreliable")
        for _ in range(5):
            manager._tool_usage["unreliable"].record_call(success=True, duration_ms=100.0)
            manager._tool_usage["unreliable"].record_call(success=False, duration_ms=100.0)

        reliable = manager.get_reliable_tools()
        assert "reliable" in reliable
        assert "unreliable" not in reliable

    def test_get_unreliable_tools(self):
        """Test getting list of unreliable tools."""
        manager = MCPClientManager(config=None)

        # Add a tool with 50% success rate
        manager._tool_usage["bad_tool"] = ToolUsageStats(tool_name="bad_tool")
        for _ in range(5):
            manager._tool_usage["bad_tool"].record_call(success=True, duration_ms=100.0)
            manager._tool_usage["bad_tool"].record_call(success=False, duration_ms=100.0)

        unreliable = manager.get_unreliable_tools()
        assert "bad_tool" in unreliable


class TestMCPHealthMonitor:
    """Tests for MCPHealthMonitor class."""

    def test_initialization(self):
        """Test monitor initialization."""
        manager = MagicMock(spec=MCPClientManager)
        monitor = MCPHealthMonitor(
            client_manager=manager,
            check_interval_seconds=60.0,
            recovery_interval_seconds=30.0,
        )

        assert monitor._check_interval == 60.0
        assert monitor._recovery_interval == 30.0
        assert monitor._running is False

    def test_add_health_callback(self):
        """Test adding health callbacks."""
        manager = MagicMock(spec=MCPClientManager)
        monitor = MCPHealthMonitor(client_manager=manager)

        callback = AsyncMock()
        monitor.add_health_callback(callback)

        assert callback in monitor._health_callbacks

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping the monitor."""
        manager = MagicMock(spec=MCPClientManager)
        manager.health_check = AsyncMock(return_value={})
        manager.get_health_status = MagicMock(return_value={})
        manager.reconnect_unhealthy = AsyncMock(return_value=[])

        monitor = MCPHealthMonitor(
            client_manager=manager,
            check_interval_seconds=0.1,
            recovery_interval_seconds=0.1,
        )

        await monitor.start()
        assert monitor._running is True

        await monitor.stop()
        assert monitor._running is False

    def test_get_health_summary(self):
        """Test health summary generation."""
        manager = MagicMock(spec=MCPClientManager)

        # Mock health status
        manager.get_health_status.return_value = {
            "server1": ServerHealth(server_name="server1", healthy=True),
            "server2": ServerHealth(server_name="server2", healthy=False),
        }

        # Mock tool stats
        stats1 = ToolUsageStats(tool_name="tool1")
        stats1.record_call(success=True, duration_ms=100.0)
        stats2 = ToolUsageStats(tool_name="tool2")
        stats2.record_call(success=False, duration_ms=200.0)

        manager.get_tool_stats.return_value = {"tool1": stats1, "tool2": stats2}
        manager.get_reliable_tools.return_value = ["tool1"]
        manager.get_unreliable_tools.return_value = []

        monitor = MCPHealthMonitor(client_manager=manager)
        summary = monitor.get_health_summary()

        assert summary["servers"]["total"] == 2
        assert summary["servers"]["healthy"] == 1
        assert summary["servers"]["unhealthy"] == 1
        assert "server1" in summary["servers"]["healthy_names"]
        assert "server2" in summary["servers"]["unhealthy_names"]
        assert summary["tools"]["total"] == 2
        assert summary["metrics"]["total_calls"] == 2
        assert summary["status"] == "degraded"

    def test_health_summary_all_healthy(self):
        """Test health summary when all servers are healthy."""
        manager = MagicMock(spec=MCPClientManager)
        manager.get_health_status.return_value = {
            "server1": ServerHealth(server_name="server1", healthy=True),
        }
        manager.get_tool_stats.return_value = {}
        manager.get_reliable_tools.return_value = []
        manager.get_unreliable_tools.return_value = []

        monitor = MCPHealthMonitor(client_manager=manager)
        summary = monitor.get_health_summary()

        assert summary["status"] == "healthy"


class TestHealthIntegration:
    """Integration tests for health monitoring."""

    def test_full_health_tracking_flow(self):
        """Test complete health tracking workflow."""
        manager = MCPClientManager(config=None)

        # Initialize server health
        manager._server_health["api-server"] = ServerHealth(server_name="api-server")

        # Simulate multiple tool calls
        for i in range(10):
            success = i < 8  # 80% success rate
            manager.record_tool_usage(
                "api_call",
                success=success,
                duration_ms=100.0 + (i * 10),
                error=None if success else "Error",
                server_name="api-server",
            )

        # Check stats
        stats = manager._tool_usage["api_call"]
        assert stats.call_count == 10
        assert stats.success_count == 8
        assert stats.success_rate == 0.8

        # Check server health
        health = manager._server_health["api-server"]
        assert health.success_count == 8
        assert health.failure_count == 2
        assert health.degraded is True  # Below 90%

    def test_priority_based_tool_ranking(self):
        """Test that tools are ranked by server priority."""
        manager = MCPClientManager(config=None)

        # Create two servers with different health
        manager._server_health["fast-server"] = ServerHealth(server_name="fast-server")
        manager._server_health["slow-server"] = ServerHealth(server_name="slow-server")

        # Fast server: 100% success, fast response
        for _ in range(10):
            manager._server_health["fast-server"].record_success()
            manager._server_health["fast-server"].record_response_time(50.0)

        # Slow server: 80% success, slow response
        for _ in range(8):
            manager._server_health["slow-server"].record_success()
        for _ in range(2):
            manager._server_health["slow-server"].record_failure()
        manager._server_health["slow-server"].record_response_time(3000.0)

        # Fast server should have higher priority
        assert manager._server_health["fast-server"].priority > manager._server_health["slow-server"].priority
