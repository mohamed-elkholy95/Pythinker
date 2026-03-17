"""Tests for graduated step wall-clock pressure thresholds."""

from app.domain.services.agents.base import (
    _get_wall_clock_pressure_level,
    _should_block_tool_at_pressure,
)


class TestGraduatedWallClock:
    def test_none_below_50_percent(self):
        assert _get_wall_clock_pressure_level(200.0, 600.0) is None

    def test_advisory_at_50_percent(self):
        assert _get_wall_clock_pressure_level(310.0, 600.0) == "ADVISORY"

    def test_urgent_at_75_percent(self):
        assert _get_wall_clock_pressure_level(460.0, 600.0) == "URGENT"

    def test_critical_at_90_percent(self):
        assert _get_wall_clock_pressure_level(550.0, 600.0) == "CRITICAL"

    def test_zero_budget_returns_none(self):
        assert _get_wall_clock_pressure_level(100.0, 0.0) is None

    def test_read_tools_blocked_at_urgent(self):
        assert _should_block_tool_at_pressure("web_search", "URGENT") is True
        assert _should_block_tool_at_pressure("file_read", "URGENT") is True
        assert _should_block_tool_at_pressure("file_write", "URGENT") is False

    def test_all_blocked_at_critical_except_write(self):
        assert _should_block_tool_at_pressure("web_search", "CRITICAL") is True
        assert _should_block_tool_at_pressure("file_read", "CRITICAL") is True
        assert _should_block_tool_at_pressure("file_write", "CRITICAL") is False
        assert _should_block_tool_at_pressure("code_save_artifact", "CRITICAL") is False
        assert _should_block_tool_at_pressure("file_str_replace", "CRITICAL") is False

    def test_nothing_blocked_at_advisory(self):
        assert _should_block_tool_at_pressure("web_search", "ADVISORY") is False
        assert _should_block_tool_at_pressure("file_read", "ADVISORY") is False
