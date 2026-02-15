"""
Plotly chart creation tool for the agent.

Supports 8 chart types: bar, line, scatter, pie, area, grouped_bar, stacked_bar, box
"""

import json
import logging
import uuid
from typing import Any

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


class ChartTool(BaseTool):
    """
    Plotly chart creation tool for the agent.

    Creates interactive HTML and static PNG charts from structured data.
    Supports bar, line, scatter, pie, area, grouped_bar, stacked_bar, and box charts.
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
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox
        self.session_id = session_id

    @tool(
        name="chart_create",
        description="""Create professional interactive Plotly charts following industry best practices.

CHART TYPE SELECTION GUIDE (Context7 MCP Validated):
- bar: Categorical comparisons, rankings (default: vertical; use orientation='h' for labels >4 chars)
- line: Time-series data, trends over continuous range
- scatter: Correlation analysis, distribution patterns, outlier detection
- pie: Part-to-whole relationships (max 5-7 categories, avoid if values are similar)
- area: Cumulative trends, stacked contributions over time
- grouped_bar: Multi-series categorical comparison
- stacked_bar: Part-to-whole over categories
- box: Distribution analysis, quartiles, outliers

BEST PRACTICES:
- Vertical bars (default): Best for rankings, histograms, categorical comparisons
- Horizontal bars ('h'): Switch to this when labels are longer than 3-4 characters
- Sorting: Charts auto-sort by value (descending) for optimal readability
- Colors: Professional Plotly qualitative palette applied automatically
- Theme: 'plotly_white' recommended for clean, professional appearance
- Text: Auto-formatted with smart number abbreviations (12k, 1.5M, etc.)
- Data Sanitization: Markdown formatting (**bold**, *italic*) automatically removed from labels
- Smart Scaling: Log scale automatically applied when value range >5x to prevent crushing small values

Returns both interactive HTML and static PNG files.""",
        parameters={
            "chart_type": {
                "type": "string",
                "description": "Type of chart to create. See tool description for selection guide.",
                "enum": ["bar", "line", "scatter", "pie", "area", "grouped_bar", "stacked_bar", "box"],
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
                "description": "Chart orientation: 'v' for vertical (DEFAULT - best for rankings, histograms, categorical comparisons), 'h' for horizontal (use when labels are longer than 3-4 characters to prevent rotation issues).",
                "enum": ["v", "h"],
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
        },
        required=["chart_type", "title", "labels", "datasets"],
    )
    async def chart_create(
        self,
        chart_type: str,
        title: str,
        labels: list[str],
        datasets: list[dict[str, Any]],
        x_label: str = "",
        y_label: str = "",
        orientation: str = "v",
        lower_is_better: bool = False,
        width: int = 1000,
        height: int = 600,
        theme: str = "plotly_white",
    ) -> ToolResult:
        """
        Create a Plotly chart and return HTML + PNG file references.

        Args:
            chart_type: Type of chart (bar, line, scatter, pie, area, grouped_bar, stacked_bar, box)
            title: Chart title
            labels: X-axis labels or category names
            datasets: Data series to plot
            x_label: X-axis label
            y_label: Y-axis label
            orientation: Chart orientation (v or h)
            lower_is_better: Whether lower values are better (for sorting)
            width: Chart width in pixels
            height: Chart height in pixels
            theme: Plotly theme

        Returns:
            ToolResult with chart metadata and file paths
        """
        # Validate inputs
        if not labels:
            return ToolResult(success=False, message="Labels cannot be empty")

        if not datasets or len(datasets) == 0:
            return ToolResult(success=False, message="Datasets cannot be empty")

        for i, dataset in enumerate(datasets):
            if "values" not in dataset:
                return ToolResult(success=False, message=f"Dataset {i} missing 'values' field")
            if len(dataset["values"]) != len(labels):
                return ToolResult(
                    success=False,
                    message=f"Dataset {i} has {len(dataset['values'])} values but {len(labels)} labels. They must match.",
                )

        # Generate unique chart ID
        chart_id = str(uuid.uuid4())[:8]

        # Build output paths
        output_html = f"/home/ubuntu/chart-{chart_id}.html"
        output_png = f"/home/ubuntu/chart-{chart_id}.png"

        # Build JSON payload for sandbox script
        chart_spec = {
            "chart_type": chart_type,
            "title": title,
            "x_label": x_label,
            "y_label": y_label,
            "labels": labels,
            "datasets": datasets,
            "orientation": orientation,
            "lower_is_better": lower_is_better,
            "width": width,
            "height": height,
            "theme": theme,
            "output_html": output_html,
            "output_png": output_png,
        }

        # Write JSON spec to sandbox temp file
        temp_input_path = f"/tmp/plotly_input_{chart_id}.json"
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
                cwd="/home/ubuntu",
                command=command,
            )

            # Clean up temp file (best-effort)
            try:
                await self.sandbox.exec_command(
                    session_id=self.session_id,
                    cwd="/home/ubuntu",
                    command=f"rm -f {temp_input_path}",
                )
            except Exception:
                logger.debug(f"Failed to clean up temp file {temp_input_path}")

            if not exec_result.success:
                logger.warning(f"Chart generation failed: {exec_result.message}")
                return ToolResult(
                    success=False,
                    message=f"Chart generation failed: {exec_result.message}",
                )

            # Parse JSON output from script
            # Output is in exec_result.data['output'], not exec_result.message
            try:
                output_str = exec_result.data.get("output") if exec_result.data else exec_result.message
                output_data = json.loads(output_str)
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Failed to parse chart script output: {e}")
                return ToolResult(
                    success=False,
                    message=f"Failed to parse chart output: {output_str if 'output_str' in locals() else exec_result.message}",
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
            return ToolResult(success=False, message=f"Chart creation failed: {e}")
