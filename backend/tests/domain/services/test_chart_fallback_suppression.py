"""Tests for chart fallback suppression when no data is extractable."""
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestChartFallbackSuppression:
    """Verify no chart is generated when primary extraction finds no data."""

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_finds_no_data(self):
        """When Plotly finds no chart data (not an error), skip SVG fallback entirely."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runtime = MagicMock(spec=AgentTaskRunner)
        runtime._plotly_chart_orchestrator = AsyncMock()
        runtime._plotly_chart_orchestrator.generate_chart = AsyncMock(return_value=None)
        runtime._has_attachment = MagicMock(return_value=False)
        runtime._ensure_legacy_svg_chart = AsyncMock(return_value=[])
        runtime._session_id = "test-session"

        event = MagicMock()
        event.id = "test-report"
        event.title = "Test Report"
        event.content = "# Report\nSome text without tables."

        # Call the actual method — unbound, pass self
        result = await AgentTaskRunner._ensure_plotly_chart_files(
            runtime, event, [], force_generation=False, generation_mode="auto"
        )

        # Should NOT call legacy SVG fallback when primary found no data (no error)
        runtime._ensure_legacy_svg_chart.assert_not_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_fallback_on_actual_error(self):
        """When Plotly raises an exception, DO fall back to legacy SVG."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runtime = MagicMock(spec=AgentTaskRunner)
        runtime._plotly_chart_orchestrator = AsyncMock()
        runtime._plotly_chart_orchestrator.generate_chart = AsyncMock(
            side_effect=ValueError("chart rendering failed")
        )
        runtime._has_attachment = MagicMock(return_value=False)
        runtime._ensure_legacy_svg_chart = AsyncMock(return_value=["fallback.svg"])
        runtime._session_id = "test-session"

        event = MagicMock()
        event.id = "test-report"
        event.title = "Test Report"
        event.content = "# Report\n| col1 | col2 |\n| --- | --- |\n| 1 | 2 |"

        await AgentTaskRunner._ensure_plotly_chart_files(
            runtime, event, [], force_generation=False, generation_mode="auto"
        )

        # SHOULD call legacy SVG fallback when there was an actual error
        runtime._ensure_legacy_svg_chart.assert_called_once()
