"""Tests for ToolEfficiencyMonitor reset and settings."""

from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor


class TestEfficiencyMonitorReset:
    def test_reset_clears_state(self):
        monitor = ToolEfficiencyMonitor()
        monitor.record_tool_call("web_search")
        monitor.record_tool_call("web_search")
        assert monitor._consecutive_reads > 0

        monitor.reset()
        assert monitor._consecutive_reads == 0

    def test_custom_thresholds(self):
        monitor = ToolEfficiencyMonitor(
            read_threshold=8,
            strong_threshold=10,
            same_tool_threshold=6,
            same_tool_strong_threshold=8,
        )
        assert monitor.read_threshold == 8
        assert monitor.strong_threshold == 10
        assert monitor.same_tool_threshold == 6
        assert monitor.same_tool_strong_threshold == 8
