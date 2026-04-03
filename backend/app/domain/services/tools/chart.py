"""
Plotly chart creation tool for the agent.

Supports 14 chart types: bar, line, scatter, pie, area, grouped_bar, stacked_bar, box,
donut, waterfall, funnel, treemap, indicator, auto
"""

import asyncio
import json
import logging
import uuid
from typing import Any

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

logger = logging.getLogger(__name__)


class ChartTool(BaseTool):
    """
    Plotly chart creation tool for the agent.

    Creates interactive HTML and static PNG charts from structured data.
    Supports bar, line, scatter, pie, area, grouped_bar, stacked_bar, box,
    donut, waterfall, funnel, treemap, indicator, and auto-detected chart types.
    """

    name: str = "chart"

    def __init__(
        self,
        sandbox: Sandbox,
        session_id: str,
        max_observe: int | None = None,
    ):
        """
        Initialize Chart tool.

        Args:
            sandbox: Sandbox service for chart generation
            session_id: Session identifier
            max_observe: Optional custom observation limit
        """
        super().__init__(
            max_observe=max_observe,
            defaults=ToolDefaults(category="chart"),
        )
        self.sandbox = sandbox
        self.session_id = session_id
        self._background_tasks: set[asyncio.Task[None]] = set()

    @tool(
        name="chart_create",
        description="""Create professional interactive Plotly charts following industry best practices.

STEP 1: IDENTIFY YOUR DATA TYPE
Before choosing a chart, classify your data:
- Categorical/Ordinal: Groups with no inherent order (product types, regions) or ordered categories (satisfaction levels)
- Time Series: Numerical values measured over ordered time points (sales by month, daily users)
- Numerical Continuous: Measurements like price, speed, weight, temperature
- Part-to-Whole: Components that sum to a total (market share, budget breakdown)
- Relationship/Correlation: Two or more variables to compare (ad spend vs conversions, height vs weight)
- Distribution: Spread of values showing frequency, quartiles, outliers

STEP 2: MATCH DATA TYPE TO CHART TYPE

COMPARISON & CATEGORICAL DATA:
- bar: Compare values across categories (sales by product, cost by model)
  • Use when: You have discrete categories and want to show which is larger/smaller
  • Variable type: Categorical + Numerical metric
  • Example: "Compare average response time across 5 LLM models"
  • Orientation: Always use vertical (default). Only pass 'h' if user explicitly requests horizontal.

- grouped_bar: Compare multiple series across categories (Q1 vs Q2 sales by region)
  • Use when: Multiple metrics per category need side-by-side comparison
  • Variable type: Categorical + Multiple numerical series
  • Example: "Compare speed and accuracy scores for each model"

- stacked_bar: Show part-to-whole composition across categories
  • Use when: You want to see both total and components per category
  • Variable type: Categorical + Multiple numerical components
  • Example: "Total budget by department, broken down by expense type"

TRENDS & TIME-SERIES DATA:
- line: Show how values change over time or continuous range
  • Use when: Data points are ordered and continuity matters
  • Variable type: Time/ordered variable + Numerical metric
  • Example: "Daily active users over the past 6 months"
  • Tip: Add markers for discrete data points; use multiple lines for series comparison

- area: Emphasize volume and cumulative trends over time
  • Use when: Magnitude of change is more important than precise values
  • Variable type: Time/ordered variable + Numerical metric
  • Example: "Revenue accumulation over quarters"

DISTRIBUTION & SPREAD:
- box: Show distribution quartiles, median, and outliers
  • Use when: Understanding data spread and identifying outliers is key
  • Variable type: Numerical continuous data (single variable or grouped by category)
  • Example: "Distribution of response times across different API endpoints"

RELATIONSHIP & CORRELATION:
- scatter: Explore relationship between two numerical variables
  • Use when: Looking for correlation, clusters, or outliers between variables
  • Variable type: Two numerical variables
  • Example: "Correlation between model size (parameters) and inference speed"
  • Tip: Use color/size for third dimension (bubble chart effect)

PART-TO-WHOLE:
- pie: Show proportions of a total (max 5-7 slices)
  • Use when: You have a small number of categories that sum to 100%
  • Variable type: Categorical + Percentage/proportion
  • Example: "Market share distribution among top 5 vendors"
  • AVOID when: More than 7 categories (use bar instead), or values are similar (hard to distinguish)

STEP 3: APPLY BEST PRACTICES
- Vertical bars (default): ALWAYS prefer vertical bars — they are the standard for comparisons and rankings
- Horizontal bars ('h'): ONLY use when the user explicitly asks for horizontal. Do NOT switch automatically based on label length.
- Orientation: Leave as 'auto' (default) and the system will handle it. Never pass 'h' unless user specifically requests horizontal.
- Sorting: Charts auto-sort by value (descending) for optimal readability in comparisons
- Colors: Professional Plotly qualitative palette applied automatically (10 distinct colors)
- Theme: 'plotly_white' recommended for clean, professional appearance
- Text: Auto-formatted with smart number abbreviations (12k, 1.5M, etc.)
- Data Sanitization: Markdown formatting (**bold**, *italic*) automatically removed from labels
- Smart Scaling: Log scale automatically applied when value range >5x to prevent crushing small values

STEP 4: AVOID COMMON MISTAKES
- Don't use pie charts for >7 categories or similar values → Use bar chart instead
- Don't use line charts for unordered categories → Use bar chart
- Don't use bar charts for time-series → Use line chart
- Don't force horizontal orientation — let auto-orientation handle it

FINANCIAL & CUMULATIVE DATA:
- waterfall: Show cumulative effect of sequential values (P&L, budget changes)
  • Use when: Values represent incremental changes (gains/losses) building to a total
  • Example: "Quarterly profit breakdown: revenue, costs, taxes → net profit"
  • Optional: Pass 'measure' in dataset with ["relative", "relative", "total"] values

CONVERSION & PIPELINE DATA:
- funnel: Visualize conversion pipeline stages
  • Use when: Sequential stages with decreasing values (sales funnel, user journey)
  • Example: "Website conversion: Visitors → Signups → Trials → Paid"
  • Shows value + percent of initial automatically

HIERARCHICAL DATA:
- treemap: Show hierarchical part-to-whole relationships
  • Use when: Data has parent-child relationships (org chart, file sizes, budget hierarchy)
  • Requires: 'parents' parameter matching labels
  • Example: "Department budget breakdown with sub-departments"

KPI & METRICS:
- indicator: Dashboard-style KPI card with optional delta
  • Use when: Single headline number with optional comparison to reference
  • Example: "Current MRR: $125,000 (+12.5% vs last month)"
  • Optional: 'reference' parameter for delta calculation

MODERN ALTERNATIVES:
- donut: Modern pie chart with center hole (hole=0.45)
  • Use when: Same as pie but want modern appearance
  • Example: "Revenue by product line"

AUTO-DETECTION:
- auto: Let the system choose the best chart type based on data characteristics
  • Analyzes: data count, temporal patterns, hierarchy, value distributions
  • Good when you're unsure which chart type fits best

DECISION FLOWCHART:
1. Unsure? → Use 'auto' and let the system decide
2. Is data categorical? → bar (orientation auto-detected) or grouped_bar
3. Is data time-series? → line chart
4. Is data continuous relationship? → scatter plot
5. Is data part-to-whole with <7 categories? → pie or donut
6. Is data distribution/spread? → box plot
7. Is data cumulative/financial? → waterfall
8. Is data a conversion pipeline? → funnel
9. Is data hierarchical? → treemap
10. Single KPI metric? → indicator

Returns both interactive HTML and static PNG files.""",
        parameters={
            "chart_type": {
                "type": "string",
                "description": "Type of chart to create. Use 'auto' to let the system choose. See tool description for selection guide.",
                "enum": [
                    "bar",
                    "line",
                    "scatter",
                    "pie",
                    "area",
                    "grouped_bar",
                    "stacked_bar",
                    "box",
                    "donut",
                    "waterfall",
                    "funnel",
                    "treemap",
                    "indicator",
                    "auto",
                ],
            },
            "title": {
                "type": "string",
                "description": "Chart title",
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "X-axis labels or category names (e.g., ['Option A', 'Option B', 'Option C'])",
            },
            "datasets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Series name (e.g., 'Performance')"},
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Data values for this series",
                        },
                        "color": {
                            "type": "string",
                            "description": "Optional hex color code (e.g., '#2563eb')",
                        },
                    },
                    "required": ["values"],
                },
                "description": "Data series to plot. For single-series charts like pie, use one dataset. For multi-series charts like grouped_bar, use multiple datasets.",
            },
            "x_label": {
                "type": "string",
                "description": "X-axis label (optional)",
            },
            "y_label": {
                "type": "string",
                "description": "Y-axis label (optional)",
            },
            "orientation": {
                "type": "string",
                "description": "Chart orientation: 'auto' (DEFAULT - strongly biased toward vertical). Only pass 'h' if user explicitly requests horizontal bars. Leave as 'auto' for best results.",
                "enum": ["auto", "v", "h"],
            },
            "lower_is_better": {
                "type": "boolean",
                "description": "For single-series bar charts, whether lower values are better (affects sorting and subtitle)",
            },
            "width": {
                "type": "integer",
                "description": "Chart width in pixels (default: 1000)",
            },
            "height": {
                "type": "integer",
                "description": "Chart height in pixels (default: 600)",
            },
            "theme": {
                "type": "string",
                "description": "Plotly theme (default: 'plotly_white')",
                "enum": ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white"],
            },
            "parents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parent labels for treemap hierarchy. Must match labels array length. Use '' for root nodes.",
            },
            "reference": {
                "type": "number",
                "description": "Reference value for indicator delta calculation (e.g., previous period value).",
            },
        },
        required=["chart_type", "title", "datasets"],
    )
    async def chart_create(
        self,
        chart_type: str,
        title: str,
        datasets: list[dict[str, Any]],
        labels: list[str] | None = None,
        x_label: str = "",
        y_label: str = "",
        orientation: str = "auto",
        lower_is_better: bool = False,
        width: int = 1000,
        height: int = 600,
        theme: str = "plotly_white",
        parents: list[str] | None = None,
        reference: float | None = None,
    ) -> ToolResult:
        """
        Create a Plotly chart and return HTML + PNG file references.

        Args:
            chart_type: Type of chart
            title: Chart title
            datasets: Data series to plot
            labels: X-axis labels or category names (not required for indicator)
            x_label: X-axis label
            y_label: Y-axis label
            orientation: Chart orientation (auto, v, or h)
            lower_is_better: Whether lower values are better (for sorting)
            width: Chart width in pixels
            height: Chart height in pixels
            theme: Plotly theme
            parents: Parent labels for treemap hierarchy
            reference: Reference value for indicator delta

        Returns:
            ToolResult with chart metadata and file paths
        """
        is_indicator = chart_type == "indicator"

        # Validate inputs — indicator charts don't require labels
        if not is_indicator and (not labels or len(labels) == 0):
            return ToolResult(success=False, message="Labels cannot be empty")

        if not datasets or len(datasets) == 0:
            return ToolResult(success=False, message="Datasets cannot be empty")

        # Treemap requires parents
        if chart_type == "treemap":
            if not parents:
                return ToolResult(success=False, message="Treemap requires 'parents' parameter")
            if labels and len(parents) != len(labels):
                return ToolResult(
                    success=False,
                    message=f"parents ({len(parents)}) must match labels ({len(labels)})",
                )

        for i, dataset in enumerate(datasets):
            if "values" not in dataset:
                return ToolResult(success=False, message=f"Dataset {i} missing 'values' field")
            # Skip length check for indicator (may have single value with no labels)
            if not is_indicator and labels and len(dataset["values"]) != len(labels):
                return ToolResult(
                    success=False,
                    message=f"Dataset {i} has {len(dataset['values'])} values but {len(labels)} labels. They must match.",
                )

        # Generate unique chart ID
        chart_id = str(uuid.uuid4())[:8]

        # Build output paths — HTML (interactive) + PNG (static preview)
        output_html = f"/home/ubuntu/chart-{chart_id}.html"
        output_png = f"/home/ubuntu/chart-{chart_id}.png"

        # Build JSON payload for sandbox script
        chart_spec: dict[str, Any] = {
            "chart_type": chart_type,
            "title": title,
            "x_label": x_label,
            "y_label": y_label,
            "labels": labels or [],
            "datasets": datasets,
            "orientation": orientation,
            "lower_is_better": lower_is_better,
            "width": width,
            "height": height,
            "theme": theme,
            "output_html": output_html,
            "output_png": output_png,
        }
        if parents:
            chart_spec["parents"] = parents
        if reference is not None:
            chart_spec["reference"] = reference

        # Write JSON spec to sandbox temp file (must be within /home/ubuntu or /workspace)
        temp_input_path = f"/home/ubuntu/plotly_input_{chart_id}.json"
        try:
            write_result = await self.sandbox.file_write(
                file=temp_input_path,
                content=json.dumps(chart_spec, indent=2),
            )
            if not write_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to write chart spec to sandbox: {write_result.message}",
                )
        except Exception as e:
            logger.exception(f"Failed to write chart spec: {e}")
            return ToolResult(success=False, message=f"Failed to write chart spec: {e}")

        # Execute chart generation script
        python_path = "/opt/base-python-venv/bin/python3"
        script_path = "/app/scripts/generate_plotly_chart.py"
        command = f"{python_path} {script_path} < {temp_input_path}"

        try:
            exec_result = await self.sandbox.exec_command(
                session_id=self.session_id,
                exec_dir="/home/ubuntu",
                command=command,
            )

            if not exec_result.success:
                logger.warning(f"Chart generation failed: {exec_result.message}")
                self._cleanup_temp_file(temp_input_path)
                return ToolResult(
                    success=False,
                    message=f"Chart generation failed: {exec_result.message}",
                )

            # If the chart script is still running (took >5s), wait for it then fetch output.
            # IMPORTANT: Do NOT run any other exec_command on this session_id until the
            # chart process finishes — the sandbox shell service is single-process-per-session
            # and will kill the running chart script if we reuse the session.
            exec_status = exec_result.data.get("status") if exec_result.data else None
            if exec_status == "running":
                logger.debug("Chart script still running, waiting up to 120s for completion")
                wait_result = await self.sandbox.wait_for_process(session_id=self.session_id, seconds=120)
                if not wait_result.success:
                    logger.warning(f"Chart script timed out: {wait_result.message}")
                    self._cleanup_temp_file(temp_input_path)
                    return ToolResult(
                        success=False,
                        message="Chart generation timed out after 120 seconds",
                    )
                view_result = await self.sandbox.view_shell(session_id=self.session_id)
                raw_output = view_result.data.get("output") if view_result.data else None
            else:
                # Extract output — NEVER fall back to exec_result.message
                # (it's a generic string like "Command executed", not JSON)
                raw_output = exec_result.data.get("output") if exec_result.data else None

            # If command completed but output is empty, the sandbox output
            # reader may still be buffering. Retry with view_shell after a
            # short delay.
            if not raw_output and exec_status == "completed":
                logger.debug("Chart output empty after exec, retrying with view_shell after 0.5s delay")
                await asyncio.sleep(0.5)
                view_result = await self.sandbox.view_shell(session_id=self.session_id)
                raw_output = view_result.data.get("output") if view_result.data else None

            # Clean up temp file AFTER output has been captured — running
            # exec_command earlier would kill the still-running chart process
            # because the sandbox shell is single-process-per-session.
            self._cleanup_temp_file(temp_input_path)

            if not raw_output:
                logger.warning(f"Chart script produced no output. exec_result.data={exec_result.data}")
                return ToolResult(
                    success=False,
                    message="Chart script produced no output — the script may have failed silently",
                )

            # Parse JSON output from script — find the JSON line in potentially mixed output
            try:
                output_str = raw_output
                # Script outputs JSON on a single line; search for it in case stderr is mixed in
                json_line = next(
                    (line for line in output_str.splitlines() if line.strip().startswith("{")),
                    None,
                )
                if json_line is None:
                    raise json.JSONDecodeError("No JSON line found", output_str, 0)
                output_data = json.loads(json_line)
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.warning(f"Failed to parse chart script output: {e}")
                detail = str(output_str)[:500] if output_str else exec_result.message
                return ToolResult(
                    success=False,
                    message=f"Failed to parse chart output: {detail}",
                )

            if not output_data.get("success"):
                error_msg = output_data.get("error", "Unknown error")
                return ToolResult(success=False, message=f"Chart generation failed: {error_msg}")

            # Return success with chart metadata
            return ToolResult(
                success=True,
                message=f"Created {chart_type} chart: {title}",
                data={
                    "chart_type": chart_type,
                    "title": title,
                    "html_path": output_data.get("html_path"),
                    "png_path": output_data.get("png_path"),
                    "html_size": output_data.get("html_size"),
                    "png_size": output_data.get("png_size"),
                    "data_points": output_data.get("data_points"),
                    "series_count": output_data.get("series_count"),
                },
            )

        except Exception as e:
            logger.exception(f"Chart creation failed: {e}")
            self._cleanup_temp_file(temp_input_path)
            return ToolResult(success=False, message=f"Chart creation failed: {e}")

    def _cleanup_temp_file(self, path: str) -> None:
        """Schedule best-effort cleanup of a sandbox temp file.

        Uses ``file_delete`` (a dedicated file API) instead of ``exec_command``
        to avoid killing a still-running process — the sandbox shell service
        is single-process-per-session and reusing the session would terminate
        the chart script.
        """

        async def _do_cleanup() -> None:
            try:
                await self.sandbox.file_delete(path)
            except Exception:
                logger.debug(f"Failed to clean up temp file {path}")

        task = asyncio.ensure_future(_do_cleanup())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
