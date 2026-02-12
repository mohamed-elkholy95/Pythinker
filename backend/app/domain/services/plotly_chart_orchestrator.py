"""
Plotly Chart Orchestrator (Phase 4)

Orchestrates comparison chart generation using the Plotly sandbox script.
Reuses table detection logic from ComparisonChartGenerator and runs
the Plotly chart generator script in the sandbox.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.domain.external.sandbox import Sandbox
from app.domain.services.comparison_chart_generator import ComparisonChartGenerator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlotlyChartResult:
    """Result of Plotly chart generation."""

    html_path: str
    png_path: str
    html_size: int
    png_size: int
    data_points: int
    metric_name: str | None
    chart_kind: str


class PlotlyChartOrchestrator:
    """Orchestrates Plotly chart generation in the sandbox."""

    def __init__(self, sandbox: Sandbox):
        """Initialize orchestrator.

        Args:
            sandbox: Sandbox instance for running chart generation script
        """
        self._sandbox = sandbox
        # Reuse existing table detection logic
        self._legacy_generator = ComparisonChartGenerator()

    async def generate_chart(
        self,
        report_title: str,
        markdown_content: str,
        report_id: str,
        *,
        force_generation: bool = False,
    ) -> PlotlyChartResult | None:
        """Generate Plotly chart from report markdown if it contains comparison data.

        Args:
            report_title: Report title
            markdown_content: Markdown content to analyze
            report_id: Report event ID (for filename)
            force_generation: Force generation even if not detected as comparison

        Returns:
            PlotlyChartResult if chart was generated, None otherwise
        """
        if not markdown_content.strip():
            return None

        # Reuse legacy table extraction logic
        tables = self._legacy_generator._extract_tables(markdown_content)
        if not tables:
            logger.debug("No tables found in report markdown")
            return None

        best_table = self._legacy_generator._select_best_table(tables)
        if best_table is None:
            logger.debug("No suitable table found for chart generation")
            return None

        # Check if this is a comparison context (unless forced)
        if not force_generation and not self._legacy_generator._is_comparison_context(
            report_title, markdown_content, best_table
        ):
            logger.debug("Report does not appear to be a comparison (no force flag)")
            return None

        # Try to build numeric chart spec (bar chart)
        numeric_spec = self._legacy_generator._build_numeric_chart_spec(best_table, report_title)
        if numeric_spec is None:
            logger.warning("Could not extract numeric data from comparison table")
            return None

        # Build JSON payload for sandbox script
        script_input = {
            "title": numeric_spec.title,
            "metric_name": numeric_spec.metric_name,
            "lower_is_better": numeric_spec.lower_is_better,
            "points": [
                {"label": p.label, "value": p.value, "display_value": p.display_value} for p in numeric_spec.points
            ],
            "output_html": f"/home/ubuntu/comparison-chart-{report_id}.html",
            "output_png": f"/home/ubuntu/comparison-chart-{report_id}.png",
        }

        # Run Plotly chart generator script in sandbox
        try:
            script_cmd = f"python3 /app/scripts/generate_comparison_chart_plotly.py"
            result = await self._sandbox.shell_exec(script_cmd, stdin_data=json.dumps(script_input))

            if not result.success:
                logger.error(f"Plotly chart generation script failed: {result.message}")
                return None

            # Parse JSON output from script
            try:
                output = json.loads(result.result.strip())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Plotly script output: {e}\nOutput: {result.result}")
                return None

            if not output.get("success"):
                logger.error(f"Plotly script reported failure: {output.get('error')}")
                return None

            return PlotlyChartResult(
                html_path=output["html_path"],
                png_path=output["png_path"],
                html_size=output["html_size"],
                png_size=output["png_size"],
                data_points=output["data_points"],
                metric_name=numeric_spec.metric_name,
                chart_kind="bar",
            )

        except Exception as e:
            logger.exception(f"Plotly chart orchestration failed: {e}")
            return None
