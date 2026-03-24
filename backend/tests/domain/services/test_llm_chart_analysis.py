"""
Tests for LLM-powered chart analysis in PlotlyChartOrchestrator.

Covers:
- ChartAnalysisResult Pydantic model validation
- LLM-based chart analysis returns spec for comparison data
- LLM-based chart analysis returns skip for non-chartable data
- Orchestrator uses LLM path when llm is provided, falls back to heuristic when not
- Chart spec correctly converts to sandbox script input
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.plotly_chart_orchestrator import (
    ChartAnalysisResult,
    PlotlyChartOrchestrator,
)

# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestChartAnalysisResult:
    """ChartAnalysisResult Pydantic model validation."""

    def test_valid_bar_chart_spec(self):
        """A valid bar chart spec should parse correctly."""
        result = ChartAnalysisResult(
            should_generate=True,
            chart_type="bar",
            title="API Latency Comparison",
            metric_name="Latency (ms)",
            lower_is_better=True,
            points=[
                {"label": "Claude", "value": 95.0},
                {"label": "GPT-4", "value": 120.0},
                {"label": "Gemini", "value": 110.0},
            ],
            reason="Report compares API latencies across three models.",
        )
        assert result.should_generate is True
        assert result.chart_type == "bar"
        assert len(result.points) == 3
        assert result.lower_is_better is True

    def test_skip_decision(self):
        """When should_generate is False, points can be empty."""
        result = ChartAnalysisResult(
            should_generate=False,
            reason="Report is a qualitative guide, not a quantitative comparison.",
        )
        assert result.should_generate is False
        assert result.points == []
        assert result.chart_type is None

    def test_points_require_label_and_value(self):
        """Each point must have a label and numeric value."""
        result = ChartAnalysisResult(
            should_generate=True,
            chart_type="bar",
            title="Test",
            metric_name="Score",
            points=[
                {"label": "A", "value": 10.0},
                {"label": "B", "value": 20.0},
            ],
        )
        assert result.points[0]["label"] == "A"
        assert result.points[0]["value"] == 10.0


# ---------------------------------------------------------------------------
# LLM analysis integration
# ---------------------------------------------------------------------------


class TestLLMChartAnalysis:
    """Test the LLM-powered chart analysis path."""

    @pytest.fixture
    def mock_sandbox(self):
        sandbox = AsyncMock()
        sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
        sandbox.exec_command = AsyncMock(
            return_value=MagicMock(
                success=True,
                data={
                    "output": '{"success": true, "html_path": "/workspace/chart.html", '
                    '"png_path": "/workspace/chart.png", '
                    '"html_size": 2048, "png_size": 1024, '
                    '"data_points": 3, "chart_kind": "bar"}'
                },
            )
        )
        sandbox.file_delete = AsyncMock()
        return sandbox

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM that returns chart analysis via ask_structured."""
        llm = AsyncMock()
        llm.model_name = "test-model"
        return llm

    @pytest.fixture
    def orchestrator_with_llm(self, mock_sandbox, mock_llm):
        return PlotlyChartOrchestrator(
            sandbox=mock_sandbox,
            session_id="test-session",
            llm=mock_llm,
        )

    @pytest.fixture
    def orchestrator_without_llm(self, mock_sandbox):
        return PlotlyChartOrchestrator(
            sandbox=mock_sandbox,
            session_id="test-session",
        )

    @pytest.mark.asyncio
    async def test_llm_path_generates_chart_for_comparison_report(self, orchestrator_with_llm, mock_llm):
        """When LLM returns should_generate=True, a chart should be produced."""
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=True,
            chart_type="bar",
            title="API Latency Comparison",
            metric_name="Latency (ms)",
            lower_is_better=True,
            points=[
                {"label": "Claude", "value": 95.0},
                {"label": "GPT-4", "value": 120.0},
                {"label": "Gemini", "value": 110.0},
            ],
            reason="Compares latencies.",
        )

        result = await orchestrator_with_llm.generate_chart(
            report_title="API Latency Comparison",
            markdown_content="# API Latency\n| Model | Latency |\n|---|---|\n| Claude | 95ms |\n| GPT-4 | 120ms |",
            report_id="test-report-1",
        )

        assert result is not None
        assert result.data_points == 3
        mock_llm.ask_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_path_skips_chart_for_qualitative_report(self, orchestrator_with_llm, mock_llm):
        """When LLM returns should_generate=False, no chart should be produced."""
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=False,
            reason="This is a qualitative guide about Virginia DMV permit tests.",
        )

        result = await orchestrator_with_llm.generate_chart(
            report_title="Virginia DMV Permit Test Guide",
            markdown_content="# Virginia DMV Guide\n## Eligibility\n...",
            report_id="test-report-2",
        )

        assert result is None
        mock_llm.ask_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_path_skips_chart_for_credit_card_features(self, orchestrator_with_llm, mock_llm):
        """A single credit card feature list should NOT produce a chart."""
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=False,
            reason="Single product feature list, not a comparison between products.",
        )

        markdown = (
            "# Robinhood Gold Card Review\n"
            "| Feature | Details | Source |\n"
            "|---------|---------|--------|\n"
            "| Annual Fee | $0 | [23] |\n"
            "| Rewards Rate | 3% cash back | [24] |\n"
        )

        result = await orchestrator_with_llm.generate_chart(
            report_title="Robinhood Gold Card Review",
            markdown_content=markdown,
            report_id="test-report-3",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_llm(self, orchestrator_without_llm):
        """Without an LLM, the orchestrator returns None (no chart)."""
        result = await orchestrator_without_llm.generate_chart(
            report_title="Model Comparison",
            markdown_content="# Comparison\n| Model | Score |\n|---|---|\n| A | 92 |\n| B | 87 |",
            report_id="test-report-4",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_llm_error(self, orchestrator_with_llm, mock_llm):
        """If the LLM call fails, return None gracefully (no chart)."""
        mock_llm.ask_structured.side_effect = Exception("LLM timeout")

        result = await orchestrator_with_llm.generate_chart(
            report_title="Model Comparison",
            markdown_content="# Comparison\n| Model | Score |\n|---|---|\n| A | 92 |\n| B | 87 |",
            report_id="test-report-5",
        )

        assert result is None
        mock_llm.ask_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_receives_truncated_content(self, orchestrator_with_llm, mock_llm):
        """Very long reports should be truncated before sending to LLM."""
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=False,
            reason="No comparison data.",
        )

        long_content = "# Report\n" + ("Some content.\n" * 5000)

        await orchestrator_with_llm.generate_chart(
            report_title="Long Report",
            markdown_content=long_content,
            report_id="test-report-6",
        )

        # Verify the LLM was called with truncated content (check message length)
        call_args = mock_llm.ask_structured.call_args
        messages = call_args[0][0] if call_args[0] else call_args[1].get("messages", [])
        user_msg = next(m for m in messages if m["role"] == "user")
        # Content should be truncated to a reasonable size, not the full 75K
        assert len(user_msg["content"]) < 15000
