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

from pydantic import BaseModel, Field, model_validator

from app.domain.services.chart_semantics import get_chart_spec_rejection_reason
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
    lower_is_better: bool | None = Field(
        default=None,
        description="True if lower values are better (e.g. latency, cost, fees). Optional when should_generate=False.",
    )
    points: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Data points: [{label: str, value: float, display_value?: str}, ...]. Only when should_generate=True.",
    )
    reason: str | None = Field(
        default=None,
        description="Brief explanation of the decision (for logging/debugging).",
    )

    @model_validator(mode="after")
    def validate_chart_decision(self) -> ChartAnalysisResult:
        """Keep chart specs internally consistent.

        Skip decisions may leave chart-specific fields empty, but valid chart
        specs must include an explicit lower_is_better value so downstream
        rendering never relies on an implicit default.
        """
        if not self.should_generate:
            return self

        if self.lower_is_better is None:
            raise ValueError("lower_is_better is required when should_generate=True")

        return self


# ---------------------------------------------------------------------------
# Chart analysis prompt
# ---------------------------------------------------------------------------

_CHART_ANALYSIS_PROMPT = """\
You are a report chart analyst.

Your job is NOT to find any numbers.
Your job is to decide whether the report contains a SINGLE, RELEVANT, COMPARABLE quantitative story that deserves a chart.

Return a JSON object matching the provided schema exactly.

PRIMARY RULE
Only generate a chart when the metric is genuinely meaningful for the report's subject and helps a reader understand the main comparison faster than text alone.

Think before deciding:
1. What is the report actually comparing?
2. What variable would a serious reader care about most?
3. Are the candidate values directly comparable on one scale with one meaning?
4. Would this chart communicate insight, or just visualize arbitrary numbers?

GENERATE A CHART ONLY IF ALL ARE TRUE
- The report compares 2+ distinct items.
- There is one shared metric across those items.
- That metric is central to the report's purpose, not incidental.
- Values are numeric and directly comparable on a single axis.
- The chart would be readable and decision-useful.
- The chart title and metric would make immediate sense to a human without extra explanation.

DO NOT GENERATE A CHART IF ANY ARE TRUE
- The report is mainly a guide, tutorial, workflow, best-practices document, or qualitative analysis.
- The report discusses one product/system and lists different attributes of that single thing.
- The only available numbers are specs, capacities, IDs, citations, dates, version numbers, parameter counts, memory sizes, core counts, model sizes, or other descriptive fields that are NOT the report's key outcome metric.
- The metric is a weak proxy that would mislead readers.
- The data mixes incompatible meanings or units.
- The chart would have a misleading title such as "performance" while plotting something else like parameters, memory, or price.
- There are fewer than 2 truly comparable points.
- The labels would be too long, too numerous, or too cluttered to read clearly.
- The values are ordinal/qualitative disguised as numbers.
- The report contains rankings/scores with no trustworthy underlying metric definition.

RELEVANCE TEST
A metric is relevant only if it answers the report's main question.
Examples:
- Good: latency, price, benchmark score, throughput, error rate, success rate, battery life.
- Bad unless explicitly the main comparison target: parameter count, VRAM, memory size, core count, release year, model family size.
- Extremely bad: plotting model parameter count under a title like "LLM Inference Performance".

SEMANTIC INTEGRITY RULE
The chart title, metric_name, and points must describe the SAME thing.
If the metric is "Parameters", do not title the chart "Inference Performance".
If the report is about performance but only spec-sheet numbers are available, set should_generate=false.

READABILITY RULES
- Prefer 3 to 6 points.
- Hard maximum 8 points.
- Use short, human-readable labels.
- Do not generate a chart if labels are likely to overlap badly or require excessive truncation.
- Choose only one metric.
- Ignore secondary metrics even if numeric.

CHART TYPE RULES
- "bar": default for comparing categories/items on one metric.
- "line": only for clear time series or ordered progression.
- "grouped_bar": only when comparing the same metric across 2 small sub-series with the same unit.
- "pie": only for part-of-whole with <= 6 slices and total-share semantics.
If unsure, use "bar" or skip chart generation.

LOWER_IS_BETTER
Set lower_is_better=True only for metrics where smaller is objectively better, such as:
- latency
- price
- cost
- fees
- power consumption
- error rate
- failure rate
Otherwise set it to False.

EXTRACTION RULES
If should_generate is True:
- Extract ONLY the best single metric.
- Every point must be {label, value, display_value?}.
- value must be numeric.
- display_value should preserve useful formatting/units when helpful.
- All values must represent the same unit and same semantic meaning.
- Exclude citation markers like [12], IDs, model names with embedded numbers, dates, and footnotes.
- Exclude descriptive/spec-sheet numbers unless they are explicitly the report's intended comparison metric.

If no good chart exists, set should_generate=false.
That is the correct decision when the data is weak, misleading, qualitative, heterogeneous, or not central to the report.

WHEN should_generate=false
- chart_type = null
- title = null
- metric_name = null
- lower_is_better = null
- points = []
- reason = a short concrete explanation of why a chart would be misleading or low-value

WHEN should_generate=true
- reason should briefly explain why the chosen metric is the most relevant one for the report

Be conservative.
A skipped chart is better than a misleading chart.
"""


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

        rejection_reason = get_chart_spec_rejection_reason(
            report_title=report_title,
            chart_title=spec.title or "",
            metric_name=spec.metric_name or "",
            labels=[str(point.get("label", "")) for point in spec.points],
            values=[point.get("value") for point in spec.points],
            chart_type=spec.chart_type,
        )
        if rejection_reason:
            logger.info("LLM chart analysis: rejected invalid chart spec (reason: %s)", rejection_reason)
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
            "lower_is_better": bool(spec.lower_is_better),
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
