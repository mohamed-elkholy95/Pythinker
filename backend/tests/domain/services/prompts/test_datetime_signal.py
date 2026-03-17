"""Tests for the unified datetime signal in system.py."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from app.domain.services.prompts.system import (
    CURRENT_DATETIME_SIGNAL,
    get_current_datetime_signal,
)


class TestCurrentDatetimeSignal:
    """Tests for get_current_datetime_signal()."""

    def test_returns_string_with_date_and_time(self):
        result = get_current_datetime_signal()
        assert "CURRENT DATE AND TIME:" in result
        assert "UTC" in result
        assert "IMPORTANT:" in result

    def test_contains_day_of_week(self):
        result = get_current_datetime_signal()
        days = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
        assert any(day in result for day in days)

    def test_contains_current_year(self):
        now = datetime.now(UTC)
        result = get_current_datetime_signal()
        assert now.strftime("%Y") in result

    def test_contains_time_component(self):
        result = get_current_datetime_signal()
        # Should contain HH:MM format somewhere
        assert "approximately" in result
        assert "UTC" in result

    def test_template_has_all_placeholders(self):
        """Verify template has all expected format placeholders."""
        assert "{current_datetime}" in CURRENT_DATETIME_SIGNAL
        assert "{day_of_week}" in CURRENT_DATETIME_SIGNAL
        assert "{full_date}" in CURRENT_DATETIME_SIGNAL
        assert "{current_time}" in CURRENT_DATETIME_SIGNAL
        assert "{year}" in CURRENT_DATETIME_SIGNAL


class TestBackwardCompatAliases:
    """Verify backward-compat aliases in execution.py and planner.py."""

    def test_execution_alias_resolves(self):
        from app.domain.services.prompts.execution import get_current_date_signal

        result = get_current_date_signal()
        assert "CURRENT DATE AND TIME:" in result

    def test_planner_alias_resolves(self):
        from app.domain.services.prompts.planner import get_current_date_signal

        result = get_current_date_signal()
        assert "CURRENT DATE AND TIME:" in result

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[MOCKED]")
    def test_execution_alias_is_patchable(self, mock_fn):
        from app.domain.services.prompts.execution import get_current_date_signal

        assert get_current_date_signal() == "[MOCKED]"

    @patch("app.domain.services.prompts.planner.get_current_date_signal", return_value="[MOCKED]")
    def test_planner_alias_is_patchable(self, mock_fn):
        from app.domain.services.prompts.planner import get_current_date_signal

        assert get_current_date_signal() == "[MOCKED]"
