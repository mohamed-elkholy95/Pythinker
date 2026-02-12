"""
Plotly Chart Orchestrator (Phase 4)

Orchestrates comparison chart generation using the Plotly sandbox script.
Reuses table detection logic from ComparisonChartGenerator and runs
the Plotly chart generator script in the sandbox.
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from dataclasses import dataclass

from app.domain.external.sandbox import Sandbox
from app.domain.services.comparison_chart_generator import ComparisonChartGenerator

logger = logging.getLogger(__name__)

# Sandbox venv python path (plotly is installed in the runtime venv)
_VENV_PYTHON = "/opt/base-python-venv/bin/python3"
_CHART_SCRIPT = "/app/scripts/generate_comparison_chart_plotly.py"


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
    """Orchestrates Plotly chart generation in the sandbox.

    Uses the sandbox ``exec_command`` API to:
    1. Write the chart specification JSON to a temporary file in the sandbox.
    2. Execute the Plotly generation script piping that file as stdin.
    3. Parse the JSON result from the script's stdout.
    """

    def __init__(self, sandbox: Sandbox, session_id: str):
        """Initialize orchestrator.

        Args:
            sandbox: Sandbox instance for running chart generation script
            session_id: Session ID for sandbox command execution
        """
        self._sandbox = sandbox
        self._session_id = session_id
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
            # Write chart input JSON to a temp file in the sandbox
            tmp_input = f"/tmp/plotly_input_{uuid.uuid4().hex[:8]}.json"
            write_result = await self._sandbox.file_write(
                file=tmp_input,
                content=json.dumps(script_input),
            )
            if not write_result.success:
                logger.error("Failed to write Plotly input to sandbox: %s", write_result.message)
                return None

            # Execute the chart generation script, piping the temp file as stdin
            command = f"{_VENV_PYTHON} {_CHART_SCRIPT} < {tmp_input}"
            result = await self._sandbox.exec_command(
                session_id=self._session_id,
                exec_dir="/home/ubuntu",
                command=command,
            )

            # Clean up temp file (best-effort)
            with contextlib.suppress(Exception):
                await self._sandbox.file_delete(path=tmp_input)

            if not result.success:
                logger.error("Plotly chart generation script failed: %s", result.message)
                return None

            # Parse JSON output from script stdout
            raw_output = (result.data if isinstance(result.data, str) else result.message) or ""
            try:
                output = json.loads(raw_output.strip())
            except json.JSONDecodeError as e:
                logger.error("Failed to parse Plotly script output: %s\nOutput: %s", e, raw_output[:500])
                return None

            if not output.get("success"):
                logger.error("Plotly script reported failure: %s", output.get("error"))
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

        except Exception:
            logger.exception("Plotly chart orchestration failed")
            return None
