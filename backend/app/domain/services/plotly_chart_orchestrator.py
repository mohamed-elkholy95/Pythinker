"""
Plotly Chart Orchestrator (Phase 5 — LLM-powered)

Uses a single LLM structured call to decide whether a chart is appropriate
for a report and extract properly typed, comparable data points.
Replaces the legacy heuristic pipeline (regex + table parsing).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.domain.utils.text import extract_json_from_shell_output

if TYPE_CHECKING:
    from app.domain.external.llm import LLM
    from app.domain.external.sandbox import Sandbox

logger = logging.getLogger(__name__)

# Sandbox venv python path (plotly is installed in the runtime venv)
_VENV_PYTHON = "/opt/base-python-venv/bin/python3"
_CHART_SCRIPT = "/app/scripts/generate_comparison_chart_plotly.py"

# Maximum report length sent to LLM for chart analysis (tokens ≈ chars / 4).
# Shorter content reduces the risk of TokenLimitExceededError during
# structured output generation.
_MAX_ANALYSIS_CONTENT = 8000


# ---------------------------------------------------------------------------
# Pydantic schema for LLM chart decision
# ---------------------------------------------------------------------------


class ChartAnalysisResult(BaseModel):
    """LLM-generated chart decision and data specification.

    When should_generate is False, all other fields are optional/empty.
    When True, chart_type/title/metric_name/points must be populated.
    """

    should_generate: bool = Field(description="Whether a meaningful chart can be generated from this report.")
    chart_type: str | None = Field(
        default=None,
        description="Chart type: 'bar', 'line', 'pie', or 'grouped_bar'. Only when should_generate=True.",
    )
    title: str | None = Field(
        default=None,
        description="Chart title. Only when should_generate=True.",
    )
    metric_name: str | None = Field(
        default=None,
        description="Name of the metric being charted (e.g. 'Latency (ms)', 'Price ($)'). Only when should_generate=True.",
    )
    lower_is_better: bool = Field(
        default=False,
        description="True if lower values are better (e.g. latency, cost, fees).",
    )
    points: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Data points: [{label: str, value: float, display_value?: str}, ...]. Only when should_generate=True.",
    )
    reason: str | None = Field(
        default=None,
        description="Brief explanation of the decision (for logging/debugging).",
    )


# ---------------------------------------------------------------------------
# Chart analysis prompt
# ---------------------------------------------------------------------------

_CHART_ANALYSIS_PROMPT = """\
Analyze this report and decide if a meaningful data visualization chart should be generated.

GENERATE a chart when:
- The report COMPARES 2+ distinct items on the SAME numeric metric (e.g., latencies, prices, scores, ratings)
- Values are directly comparable on a single axis with one unit
- A bar chart would help the reader understand relative differences at a glance

DO NOT generate a chart when:
- The report is a guide, tutorial, how-to, or qualitative overview
- The data lists features/specs of a SINGLE product (e.g., one credit card's fee + rewards + bonus — these are different attributes, not comparable items)
- Values have incompatible units (e.g., "$0 fee" vs "3% cash back" vs "None")
- Numbers are citation references like [23], page numbers, or IDs — NOT data
- There are fewer than 2 comparable numeric data points
- The table is informational (test format, eligibility docs, study tips) rather than a ranking or benchmark

If should_generate is True:
- Extract ONLY genuinely numeric, comparable data points on the SAME metric
- Each point needs: label (item name), value (number), optional display_value (formatted string)
- Set lower_is_better=True for metrics where low values are desirable (fees, latency, cost, error rate, price)
- Choose chart_type: "bar" for rankings/comparisons, "line" for time series, "pie" for part-of-whole (max 7 slices)
- Limit to 8 data points maximum (pick the most important if more exist)"""


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
    """LLM-powered Plotly chart orchestrator.

    1. Asks the LLM to analyze the report and produce a chart spec.
    2. Writes the spec as JSON to the sandbox.
    3. Executes the Plotly generation script.
    4. Parses the result.

    When no LLM is provided (e.g., in tests or degraded mode),
    generate_chart() returns None — no chart is generated.
    """

    def __init__(
        self,
        sandbox: Sandbox,
        session_id: str,
        llm: LLM | None = None,
    ):
        self._sandbox = sandbox
        self._session_id = session_id
        self._llm = llm

    async def generate_chart(
        self,
        report_title: str,
        markdown_content: str,
        report_id: str,
        *,
        force_generation: bool = False,
    ) -> PlotlyChartResult | None:
        """Generate Plotly chart from report markdown via LLM analysis.

        Returns None when no LLM is available, when the LLM decides a chart
        is not appropriate, or when generation fails.
        """
        if not markdown_content.strip():
            return None

        if self._llm is None:
            logger.debug("No LLM available for chart analysis, skipping chart generation")
            return None

        spec = await self._analyze_with_llm(report_title, markdown_content, force=force_generation)
        if spec is None:
            return None

        if not spec.should_generate:
            logger.info(
                "LLM chart analysis: skip (reason: %s)",
                spec.reason or "not chartable",
            )
            return None

        if not spec.points or len(spec.points) < 2:
            logger.info("LLM chart analysis: should_generate=True but <2 points, skipping")
            return None

        return await self._execute_chart(spec, report_title, report_id)

    # ------------------------------------------------------------------
    # LLM analysis
    # ------------------------------------------------------------------

    async def _analyze_with_llm(
        self, report_title: str, markdown_content: str, *, force: bool = False
    ) -> ChartAnalysisResult | None:
        """Ask the LLM whether a chart is appropriate and what data to chart."""
        try:
            content = markdown_content
            if len(content) > _MAX_ANALYSIS_CONTENT:
                content = content[:_MAX_ANALYSIS_CONTENT] + "\n\n[... content truncated for analysis ...]"

            system = _CHART_ANALYSIS_PROMPT
            if force:
                system += (
                    "\n\nIMPORTANT: The user has explicitly requested a chart. "
                    "Try harder to find chartable data. If there are ANY numeric "
                    "values that can be meaningfully compared, generate a chart."
                )

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Report title: {report_title}\n\n{content}"},
            ]

            result = await self._llm.ask_structured(
                messages=messages,
                response_model=ChartAnalysisResult,
                max_tokens=2048,
                temperature=0.1,
            )
            logger.info(
                "LLM chart analysis complete: should_generate=%s, chart_type=%s, points=%d, reason=%s",
                result.should_generate,
                result.chart_type,
                len(result.points),
                result.reason or "-",
            )
            return result

        except Exception as exc:
            # Graceful degradation: report will be delivered without a chart.
            # Use concise log for known LLM failures, full trace for unexpected ones.
            exc_name = type(exc).__name__
            if "Token" in exc_name or "Retry" in exc_name or "Incomplete" in exc_name:
                logger.warning("LLM chart analysis failed (token/retry limit): %s", exc_name)
            else:
                logger.warning("LLM chart analysis failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Sandbox execution
    # ------------------------------------------------------------------

    async def _execute_chart(
        self,
        spec: ChartAnalysisResult,
        report_title: str,
        report_id: str,
    ) -> PlotlyChartResult | None:
        """Execute the Plotly chart script in the sandbox from an LLM-produced spec."""
        simple_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in report_title[:50].lower())
        simple_name = simple_name.strip("_") or "chart"
        chart_dir = "/workspace"

        points = []
        for p in spec.points:
            point = {"label": str(p.get("label", "")), "value": float(p.get("value", 0))}
            point["display_value"] = str(p.get("display_value", point["value"]))
            points.append(point)

        script_input = {
            "title": spec.title or report_title,
            "metric_name": spec.metric_name or "Value",
            "lower_is_better": spec.lower_is_better,
            "points": points,
            "output_html": f"{chart_dir}/{simple_name}.html",
            "output_png": f"{chart_dir}/{simple_name}.png",
        }

        return await self._run_sandbox_script(script_input, spec.metric_name)

    async def _run_sandbox_script(self, script_input: dict, metric_name: str | None) -> PlotlyChartResult | None:
        """Write input JSON, execute Plotly script, parse result."""
        chart_dir = "/workspace"
        try:
            tmp_input = f"{chart_dir}/plotly_input_{uuid.uuid4().hex[:8]}.json"
            write_result = await self._sandbox.file_write(
                file=tmp_input,
                content=json.dumps(script_input),
            )
            if not write_result.success:
                logger.error("Failed to write Plotly input to sandbox: %s", write_result.message)
                return None

            command = f"{_VENV_PYTHON} {_CHART_SCRIPT} < {tmp_input}"
            result = await self._sandbox.exec_command(
                session_id=self._session_id,
                exec_dir="/home/ubuntu",
                command=command,
            )

            if not result.success:
                logger.error("Plotly chart generation script failed: %s", result.message)
                with contextlib.suppress(Exception):
                    await self._sandbox.file_delete(path=tmp_input)
                return None

            # Handle async completion
            exec_status = result.data.get("status") if isinstance(result.data, dict) else None
            if exec_status == "running":
                logger.debug("Plotly script still running — waiting up to 30s")
                with contextlib.suppress(Exception):
                    await self._sandbox.wait_for_process(session_id=self._session_id, seconds=30)
                with contextlib.suppress(Exception):
                    result = await self._sandbox.exec_command(
                        session_id=self._session_id,
                        exec_dir="/home/ubuntu",
                        command="true",
                    )

            # Retry on empty output
            if isinstance(result.data, dict) and not result.data.get("output", "").strip():
                logger.debug("Plotly script output empty — retrying after 0.5s")
                await asyncio.sleep(0.5)
                with contextlib.suppress(Exception):
                    result = await self._sandbox.exec_command(
                        session_id=self._session_id,
                        exec_dir="/home/ubuntu",
                        command="true",
                    )

            # Clean up temp file
            with contextlib.suppress(Exception):
                await self._sandbox.file_delete(path=tmp_input)

            # Parse output
            if isinstance(result.data, dict):
                raw_output = result.data.get("output", "")
            elif isinstance(result.data, str):
                raw_output = result.data
            else:
                raw_output = result.message or ""

            try:
                cleaned_output = extract_json_from_shell_output(raw_output)
                output = json.loads(cleaned_output)
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
                metric_name=metric_name,
                chart_kind="bar",
            )

        except Exception:
            logger.exception("Plotly chart orchestration failed")
            return None
