#!/usr/bin/env python3
"""
Generate multi-type Plotly charts from JSON input.

Supports 8 chart types: bar, line, scatter, pie, area, grouped_bar, stacked_bar, box

Input (JSON via stdin):
{
  "chart_type": "bar|line|scatter|pie|area|grouped_bar|stacked_bar|box",
  "title": "Chart Title",
  "x_label": "X Axis",
  "y_label": "Y Axis",
  "labels": ["A", "B", "C"],
  "datasets": [
    {"name": "Series 1", "values": [10, 20, 30], "color": "#2563eb"},
    {"name": "Series 2", "values": [15, 25, 35], "color": "#0891b2"}
  ],
  "orientation": "v",  // "h" for horizontal, "v" for vertical
  "lower_is_better": false,
  "width": 1000,
  "height": 600,
  "theme": "plotly_white",
  "output_html": "/home/ubuntu/chart-<id>.html",
  "output_png": "/home/ubuntu/chart-<id>.png",
  "output_json": "/home/ubuntu/chart-<id>.plotly.json"
}

Output (JSON to stdout):
{
  "success": true,
  "html_path": "...",
  "png_path": "...",
  "plotly_json_path": "...",
  "html_size": 48000,
  "png_size": 125000,
  "plotly_json_size": 32000,
  "render_contract_version": "plotly-json-v1",
  "chart_type": "bar",
  "data_points": 3,
  "series_count": 2
}

Exit codes:
- 0: Success
- 1: Invalid input JSON
- 2: Chart generation failed
- 3: File write failed
"""

from __future__ import annotations

import json
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any, TypedDict


# ---------------------------------------------------------------------------
# Constants and type definitions
# ---------------------------------------------------------------------------


class ChartType(StrEnum):
    """Supported chart types."""

    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    PIE = "pie"
    AREA = "area"
    GROUPED_BAR = "grouped_bar"
    STACKED_BAR = "stacked_bar"
    BOX = "box"


class DatasetSpec(TypedDict, total=False):
    """Shape of a single dataset in the input JSON."""

    name: str
    values: list[float]
    color: str


class ChartSpec(TypedDict, total=False):
    """Full input specification for chart generation."""

    chart_type: str
    title: str
    x_label: str
    y_label: str
    labels: list[str]
    datasets: list[DatasetSpec]
    orientation: str
    lower_is_better: bool
    width: int
    height: int
    theme: str
    output_html: str
    output_png: str
    output_json: str


# ---------------------------------------------------------------------------
# Plotly built-in qualitative color palette
# ---------------------------------------------------------------------------
# Using Plotly's own default qualitative palette (px.colors.qualitative.Plotly)
# for maximum visual distinction and accessibility. This is the canonical 10-color
# palette recommended by the Plotly documentation for categorical data.
#
# Reference: Context7 /plotly/plotly.py - discrete-color.md
PLOTLY_QUALITATIVE: list[str] = [
    "#636EFA",  # Plotly blue
    "#EF553B",  # Plotly red
    "#00CC96",  # Plotly green
    "#AB63FA",  # Plotly purple
    "#FFA15A",  # Plotly orange
    "#19D3F3",  # Plotly cyan
    "#FF6692",  # Plotly pink
    "#B6E880",  # Plotly lime
    "#FF97FF",  # Plotly magenta
    "#FECB52",  # Plotly yellow
]

# Multi-series default color sequence (distinct, color-blind friendly)
# Based on Plotly qualitative palette, same 10 colors used consistently.
SERIES_COLORS: list[str] = PLOTLY_QUALITATIVE

# Professional font stack
FONT_FAMILY = "Arial, Helvetica, sans-serif"

# Text styling constants
TITLE_FONT_SIZE = 24
TITLE_FONT_COLOR = "#111827"
BODY_FONT_SIZE = 14
BODY_FONT_COLOR = "#374151"
LABEL_FONT_SIZE = 14
LABEL_FONT_COLOR = "#1f2937"

# Grid styling constants (subtle, non-overpowering)
GRID_COLOR = "rgba(0,0,0,0.08)"
GRID_WIDTH = 1
ZEROLINE_COLOR = "rgba(0,0,0,0.15)"
ZEROLINE_WIDTH = 2

# Bar chart constants
BAR_BORDER_COLOR = "rgba(255,255,255,0.8)"
BAR_BORDER_WIDTH = 2
BAR_GAP = 0.15
BAR_GROUP_GAP = 0.1

# Uniform text settings (Context7 validated: uniformtext_minsize + uniformtext_mode)
UNIFORMTEXT_MINSIZE = 8
UNIFORMTEXT_MODE = "hide"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _get_color(index: int, dataset: DatasetSpec | None = None) -> str:
    """Get a color for a trace, using dataset override or cycling the qualitative palette.

    Args:
        index: Position index for palette cycling.
        dataset: Optional dataset spec that may contain a ``color`` override.

    Returns:
        Hex color string.
    """
    if dataset and dataset.get("color"):
        return dataset["color"]
    return PLOTLY_QUALITATIVE[index % len(PLOTLY_QUALITATIVE)]


def _hex_to_rgba(hex_color: str, alpha: float = 0.25) -> str:
    """Convert a hex color string to an rgba() CSS string.

    Handles both ``#RGB`` and ``#RRGGBB`` formats. Falls back to the original
    string with appended alpha hex if conversion fails.

    Args:
        hex_color: Hex color string (e.g. ``#2563eb``).
        alpha: Opacity value between 0 and 1.

    Returns:
        CSS rgba() string.
    """
    color = hex_color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    if len(color) != 6:
        # Fallback: return original with hex alpha
        alpha_hex = format(int(alpha * 255), "02x")
        return f"{hex_color}{alpha_hex}"
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _sanitize_label(label: str) -> str:
    """Remove markdown formatting and clean up label text.

    Handles common issues:
    - Markdown bold (**text**), italic (*text*), code (`text`)
    - Leading/trailing whitespace
    - Multiple consecutive spaces

    Args:
        label: Raw label string that may contain markdown.

    Returns:
        Cleaned label string.
    """
    import re

    # Remove markdown bold (**text**)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", label)

    # Remove markdown italic (*text*)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)

    # Remove markdown code (`text`)
    cleaned = re.sub(r"`(.+?)`", r"\1", cleaned)

    # Remove underscores used for emphasis (__text__ or _text_)
    cleaned = re.sub(r"__(.+?)__", r"\1", cleaned)
    cleaned = re.sub(r"_(.+?)_", r"\1", cleaned)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()


def _detect_extreme_outliers(values: list[float], threshold: float = 5.0) -> bool:
    """Detect if data contains extreme outliers that would crush the visual scale.

    An outlier is considered "extreme" if it's more than `threshold` times larger
    than the median value, which would make smaller values hard to read.

    Args:
        values: List of numeric values to check.
        threshold: Multiplier to consider an outlier extreme (default: 5x).

    Returns:
        True if extreme outliers detected, False otherwise.
    """
    if not values or len(values) < 2:
        return False

    import statistics

    abs_values = [abs(v) for v in values if v != 0]
    if not abs_values:
        return False

    median = statistics.median(abs_values)
    if median == 0:
        return False

    max_val = max(abs_values)
    return max_val / median >= threshold


def _smart_text_format(values: list[float]) -> str:
    """Choose a d3-format string for text labels based on value magnitude.

    Uses Plotly's ``texttemplate`` d3-format syntax:
    - Large numbers (>=10000): 2 significant digits with SI suffix (e.g. "12k")
    - Small decimals (<1): 2 decimal places
    - Everything else: comma-separated integer or 1 decimal

    Args:
        values: The data values to format.

    Returns:
        A Plotly texttemplate format string.
    """
    if not values:
        return "%{text}"

    max_val = max(abs(v) for v in values) if values else 0

    if max_val >= 10_000:
        return "%{text:.3s}"
    if max_val < 1 and max_val > 0:
        return "%{text:.2f}"
    if all(v == int(v) for v in values):
        return "%{text:,}"
    return "%{text:,.1f}"


# ---------------------------------------------------------------------------
# Shared layout builder
# ---------------------------------------------------------------------------


def _build_base_layout(
    *,
    title: str,
    subtitle: str = "",
    x_label: str = "",
    y_label: str = "",
    theme: str = "plotly_white",
    width: int = 1000,
    height: int = 600,
    orientation: str = "v",
    show_legend: bool = True,
    barmode: str | None = None,
) -> dict[str, Any]:
    """Build a shared layout dictionary used by all chart types.

    Centralizes layout configuration to eliminate duplication and ensure
    consistent professional styling across all chart types.

    Args:
        title: Chart title text.
        subtitle: Optional HTML subtitle appended below the title.
        x_label: X-axis label.
        y_label: Y-axis label.
        theme: Plotly template name.
        width: Chart width in pixels.
        height: Chart height in pixels.
        orientation: ``"v"`` for vertical, ``"h"`` for horizontal.
        show_legend: Whether to show the legend.
        barmode: Bar mode (``"group"``, ``"stack"``, or ``None``).

    Returns:
        Dictionary suitable for ``fig.update_layout(**layout)``.
    """
    full_title = f"{title}{subtitle}" if subtitle else title

    # Determine which axis gets which label based on orientation
    if orientation == "h":
        x_title = y_label
        y_title = x_label
    else:
        x_title = x_label
        y_title = y_label

    # For horizontal bar charts, hide y-axis grid (labels are categories)
    y_show_grid = orientation != "h"

    # Left margin needs to be wider for horizontal bar charts (long category labels)
    left_margin = 200 if orientation == "h" else 80

    layout: dict[str, Any] = {
        "title": {
            "text": full_title,
            "font": {
                "size": TITLE_FONT_SIZE,
                "color": TITLE_FONT_COLOR,
                "family": FONT_FAMILY,
            },
        },
        "xaxis": {
            "title": x_title,
            "showgrid": True,
            "gridcolor": GRID_COLOR,
            "gridwidth": GRID_WIDTH,
            "zeroline": True,
            "zerolinecolor": ZEROLINE_COLOR,
            "zerolinewidth": ZEROLINE_WIDTH,
        },
        "yaxis": {
            "title": y_title,
            "showgrid": y_show_grid,
            "gridcolor": GRID_COLOR,
            "gridwidth": GRID_WIDTH,
        },
        "template": theme,
        "height": height,
        "width": width,
        "margin": {"l": left_margin, "r": 100, "t": 100, "b": 80},
        "font": {
            "size": BODY_FONT_SIZE,
            "family": FONT_FAMILY,
            "color": BODY_FONT_COLOR,
        },
        "showlegend": show_legend,
        "plot_bgcolor": "rgba(0,0,0,0)",
        "paper_bgcolor": "white",
        # Uniform text sizing: hides labels that would be too small to read
        # Context7 validated: plotly.py bar-charts.md, pie-charts.md
        "uniformtext_minsize": UNIFORMTEXT_MINSIZE,
        "uniformtext_mode": UNIFORMTEXT_MODE,
    }

    if barmode is not None:
        layout["barmode"] = barmode
        layout["bargap"] = BAR_GAP
        layout["bargroupgap"] = BAR_GROUP_GAP

    return layout


# ---------------------------------------------------------------------------
# Chart generators
# ---------------------------------------------------------------------------


def generate_bar_chart(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    orientation: str,
    lower_is_better: bool,
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate a bar chart (single or multi-series).

    Single-series charts use per-bar coloring from the qualitative palette.
    Multi-series charts assign one color per series. Sorting is handled via
    Plotly's ``categoryorder`` for automatic axis ordering rather than
    manual Python sorting.

    NEW: Automatically sanitizes labels (removes markdown) and applies log scale
    when extreme outliers are detected (value range > 5x).

    Context7 validated: categoryorder='total descending' for comparisons,
    texttemplate for number formatting, uniformtext for consistent sizing.
    """
    import plotly.graph_objects as go

    # Sanitize labels to remove markdown artifacts
    clean_labels = [_sanitize_label(label) for label in labels]

    fig = go.Figure()
    is_single_series = len(datasets) == 1

    # Detect if we need log scale (extreme outliers)
    all_values = []
    for dataset in datasets:
        all_values.extend(
            [v for v in dataset["values"] if v > 0]
        )  # Log requires positive
    use_log_scale = _detect_extreme_outliers(all_values)

    if is_single_series:
        series = datasets[0]
        values = series["values"]

        # Per-bar coloring using qualitative palette
        colors = [
            PLOTLY_QUALITATIVE[i % len(PLOTLY_QUALITATIVE)]
            for i in range(len(clean_labels))
        ]
        text_format = _smart_text_format(values)

        fig.add_trace(
            go.Bar(
                x=values if orientation == "h" else clean_labels,
                y=clean_labels if orientation == "h" else values,
                orientation=orientation,
                marker={
                    "color": colors,
                    "line": {"color": BAR_BORDER_COLOR, "width": BAR_BORDER_WIDTH},
                },
                text=values,
                texttemplate=text_format,
                textposition="outside",
                textfont={"size": LABEL_FONT_SIZE, "color": LABEL_FONT_COLOR},
                name=series.get("name", ""),
            )
        )

        # Use Plotly's categoryorder for automatic sorting
        # Context7: categoryorder='total descending' is recommended for comparisons
        sort_order = "total ascending" if lower_is_better else "total descending"
        if orientation == "h":
            fig.update_yaxes(categoryorder=sort_order)
        else:
            fig.update_xaxes(categoryorder=sort_order)

    else:
        # Multi-series: one color per series
        for i, series in enumerate(datasets):
            color = _get_color(i, series)
            text_format = _smart_text_format(series["values"])
            fig.add_trace(
                go.Bar(
                    x=series["values"] if orientation == "h" else clean_labels,
                    y=clean_labels if orientation == "h" else series["values"],
                    orientation=orientation,
                    marker={"color": color},
                    text=series["values"],
                    texttemplate=text_format,
                    textposition="outside",
                    textfont={"size": LABEL_FONT_SIZE},
                    name=series.get("name", "Series"),
                )
            )

    # Build subtitle for single-series comparison context
    subtitle = ""
    if is_single_series:
        qualifier = "Lower is better" if lower_is_better else "Higher is better"
        subtitle = f"<br><sub>({qualifier})</sub>"

    # Add log scale note if detected
    if use_log_scale:
        subtitle += " <sub>• Log scale applied due to wide value range</sub>"

    layout = _build_base_layout(
        title=title,
        subtitle=subtitle,
        x_label=x_label,
        y_label=y_label,
        theme=theme,
        width=width,
        height=height,
        orientation=orientation,
        show_legend=not is_single_series,
        barmode="group" if not is_single_series else None,
    )
    fig.update_layout(**layout)

    # Apply log scale if extreme outliers detected
    if use_log_scale:
        if orientation == "h":
            fig.update_xaxes(type="log")
        else:
            fig.update_yaxes(type="log")

    return fig


def generate_line_chart(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate a line chart with markers.

    Uses the qualitative palette for multi-series differentiation.
    Lines are 3px wide with 8px markers for clear visibility.
    """
    import plotly.graph_objects as go

    # Sanitize labels
    clean_labels = [_sanitize_label(label) for label in labels]

    fig = go.Figure()

    for i, series in enumerate(datasets):
        color = _get_color(i, series)
        fig.add_trace(
            go.Scatter(
                x=clean_labels,
                y=series["values"],
                mode="lines+markers",
                name=series.get("name", "Series"),
                line={"color": color, "width": 3},
                marker={"size": 8, "color": color},
            )
        )

    layout = _build_base_layout(
        title=title,
        x_label=x_label,
        y_label=y_label,
        theme=theme,
        width=width,
        height=height,
        show_legend=len(datasets) > 1,
    )
    fig.update_layout(**layout)

    return fig


def generate_scatter_chart(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate a scatter plot.

    Uses 12px markers with hover text showing the category label.
    """
    import plotly.graph_objects as go

    # Sanitize labels
    clean_labels = [_sanitize_label(label) for label in labels]

    fig = go.Figure()

    for i, series in enumerate(datasets):
        color = _get_color(i, series)
        fig.add_trace(
            go.Scatter(
                x=clean_labels,
                y=series["values"],
                mode="markers",
                name=series.get("name", "Series"),
                marker={"size": 12, "color": color},
                text=clean_labels,
                hovertemplate="%{text}: %{y}<extra>%{fullData.name}</extra>",
            )
        )

    layout = _build_base_layout(
        title=title,
        x_label=x_label,
        y_label=y_label,
        theme=theme,
        width=width,
        height=height,
        show_legend=len(datasets) > 1,
    )
    fig.update_layout(**layout)

    return fig


def generate_pie_chart(
    title: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate a pie chart (uses first dataset only).

    Colors are assigned from the qualitative palette. Text is positioned inside
    slices showing label + percent. uniformtext ensures consistent sizing and
    hides labels that would be too small to read.

    Context7 validated: textposition='inside', uniformtext_minsize=12, uniformtext_mode='hide'.
    """
    import plotly.graph_objects as go

    # Sanitize labels
    clean_labels = [_sanitize_label(label) for label in labels]

    series = datasets[0]
    values = series["values"]

    # Use qualitative palette, cycling if more labels than colors
    colors = [
        PLOTLY_QUALITATIVE[i % len(PLOTLY_QUALITATIVE)]
        for i in range(len(clean_labels))
    ]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=clean_labels,
                values=values,
                marker={"colors": colors},
                textposition="inside",
                textinfo="label+percent",
                textfont={"size": LABEL_FONT_SIZE},
                hole=0,  # Full pie (set to 0.3-0.5 for donut)
            )
        ]
    )

    layout = _build_base_layout(
        title=title,
        theme=theme,
        width=width,
        height=height,
        show_legend=True,
    )
    # Pie charts need equal margins and no axis config
    layout["margin"] = {"l": 80, "r": 80, "t": 100, "b": 80}
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    fig.update_layout(**layout)

    return fig


def generate_area_chart(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate an area chart with semi-transparent fills.

    Uses proper hex-to-rgba conversion for fill colors instead of
    appending raw hex alpha bytes.
    """
    import plotly.graph_objects as go

    # Sanitize labels
    clean_labels = [_sanitize_label(label) for label in labels]

    fig = go.Figure()

    for i, series in enumerate(datasets):
        color = _get_color(i, series)
        fill_color = _hex_to_rgba(color, alpha=0.25)

        fig.add_trace(
            go.Scatter(
                x=clean_labels,
                y=series["values"],
                mode="lines",
                name=series.get("name", "Series"),
                line={"color": color, "width": 2},
                fill="tozeroy",
                fillcolor=fill_color,
            )
        )

    layout = _build_base_layout(
        title=title,
        x_label=x_label,
        y_label=y_label,
        theme=theme,
        width=width,
        height=height,
        show_legend=len(datasets) > 1,
    )
    fig.update_layout(**layout)

    return fig


def generate_grouped_bar_chart(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    orientation: str,
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate a grouped bar chart.

    Uses ``barmode='group'`` with consistent gap sizing.
    Context7 validated: bargap=0.15, bargroupgap=0.1.
    """
    import plotly.graph_objects as go

    # Sanitize labels
    clean_labels = [_sanitize_label(label) for label in labels]

    fig = go.Figure()

    for i, series in enumerate(datasets):
        color = _get_color(i, series)
        text_format = _smart_text_format(series["values"])
        fig.add_trace(
            go.Bar(
                x=series["values"] if orientation == "h" else clean_labels,
                y=clean_labels if orientation == "h" else series["values"],
                orientation=orientation,
                marker={"color": color},
                name=series.get("name", "Series"),
                text=series["values"],
                texttemplate=text_format,
                textposition="outside",
                textfont={"size": LABEL_FONT_SIZE},
            )
        )

    layout = _build_base_layout(
        title=title,
        x_label=x_label,
        y_label=y_label,
        theme=theme,
        width=width,
        height=height,
        orientation=orientation,
        show_legend=True,
        barmode="group",
    )
    fig.update_layout(**layout)

    return fig


def generate_stacked_bar_chart(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    orientation: str,
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate a stacked bar chart.

    Text is positioned inside bars for stacked charts to avoid overlap.
    Context7 validated: barmode='stack', textposition='inside'.
    """
    import plotly.graph_objects as go

    # Sanitize labels
    clean_labels = [_sanitize_label(label) for label in labels]

    fig = go.Figure()

    for i, series in enumerate(datasets):
        color = _get_color(i, series)
        text_format = _smart_text_format(series["values"])
        fig.add_trace(
            go.Bar(
                x=series["values"] if orientation == "h" else clean_labels,
                y=clean_labels if orientation == "h" else series["values"],
                orientation=orientation,
                marker={"color": color},
                name=series.get("name", "Series"),
                text=series["values"],
                texttemplate=text_format,
                textposition="inside",
                textfont={"size": LABEL_FONT_SIZE},
            )
        )

    layout = _build_base_layout(
        title=title,
        x_label=x_label,
        y_label=y_label,
        theme=theme,
        width=width,
        height=height,
        orientation=orientation,
        show_legend=True,
        barmode="stack",
    )
    fig.update_layout(**layout)

    return fig


def generate_box_chart(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    datasets: list[DatasetSpec],
    width: int,
    height: int,
    theme: str,
) -> Any:
    """Generate a box plot with mean and standard deviation markers.

    Each dataset becomes a separate box. Colors cycle through the
    qualitative palette for visual distinction.
    """
    import plotly.graph_objects as go

    fig = go.Figure()

    for i, series in enumerate(datasets):
        color = _get_color(i, series)
        fig.add_trace(
            go.Box(
                y=series["values"],
                name=series.get("name", "Series"),
                marker={"color": color},
                boxmean="sd",  # Show mean and standard deviation
            )
        )

    layout = _build_base_layout(
        title=title,
        x_label=x_label,
        y_label=y_label,
        theme=theme,
        width=width,
        height=height,
        show_legend=len(datasets) > 1,
    )
    fig.update_layout(**layout)

    return fig


# ---------------------------------------------------------------------------
# Chart dispatch (pattern matching)
# ---------------------------------------------------------------------------


def _generate_chart(spec: ChartSpec) -> Any:
    """Dispatch chart generation to the appropriate function using pattern matching.

    Args:
        spec: Parsed and validated chart specification.

    Returns:
        A Plotly Figure object.

    Raises:
        ValueError: If the chart type is not supported.
    """
    chart_type = spec["chart_type"]
    title = spec["title"]
    x_label = spec.get("x_label", "")
    y_label = spec.get("y_label", "")
    labels = spec["labels"]
    datasets = spec["datasets"]
    orientation = spec.get("orientation", "v")
    lower_is_better = spec.get("lower_is_better", False)
    width = spec.get("width", 1000)
    height = spec.get("height", 600)
    theme = spec.get("theme", "plotly_white")

    match chart_type:
        case ChartType.BAR:
            return generate_bar_chart(
                title,
                x_label,
                y_label,
                labels,
                datasets,
                orientation,
                lower_is_better,
                width,
                height,
                theme,
            )
        case ChartType.LINE:
            return generate_line_chart(
                title,
                x_label,
                y_label,
                labels,
                datasets,
                width,
                height,
                theme,
            )
        case ChartType.SCATTER:
            return generate_scatter_chart(
                title,
                x_label,
                y_label,
                labels,
                datasets,
                width,
                height,
                theme,
            )
        case ChartType.PIE:
            return generate_pie_chart(
                title,
                labels,
                datasets,
                width,
                height,
                theme,
            )
        case ChartType.AREA:
            return generate_area_chart(
                title,
                x_label,
                y_label,
                labels,
                datasets,
                width,
                height,
                theme,
            )
        case ChartType.GROUPED_BAR:
            return generate_grouped_bar_chart(
                title,
                x_label,
                y_label,
                labels,
                datasets,
                orientation,
                width,
                height,
                theme,
            )
        case ChartType.STACKED_BAR:
            return generate_stacked_bar_chart(
                title,
                x_label,
                y_label,
                labels,
                datasets,
                orientation,
                width,
                height,
                theme,
            )
        case ChartType.BOX:
            return generate_box_chart(
                title,
                x_label,
                y_label,
                labels,
                datasets,
                width,
                height,
                theme,
            )
        case _:
            supported = [t.value for t in ChartType]
            raise ValueError(
                f"Unsupported chart_type: {chart_type!r}. Must be one of {supported}"
            )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_input(data: dict[str, Any]) -> str | None:
    """Validate the input JSON structure and return an error message or None.

    Args:
        data: Parsed JSON input dictionary.

    Returns:
        Error message string if validation fails, ``None`` if valid.
    """
    # Required fields
    required_fields = [
        "chart_type",
        "title",
        "labels",
        "datasets",
        "output_html",
        "output_png",
    ]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return f"Missing required fields: {missing}"

    # Chart type validation
    supported = {t.value for t in ChartType}
    if data["chart_type"] not in supported:
        return f"Unsupported chart_type: {data['chart_type']!r}. Must be one of {sorted(supported)}"

    # Labels validation
    labels = data.get("labels")
    if not labels or not isinstance(labels, list):
        return "Labels must be a non-empty list"

    # Datasets validation
    datasets = data.get("datasets")
    if not datasets or not isinstance(datasets, list):
        return "Datasets must be a non-empty list"

    for i, dataset in enumerate(datasets):
        if "values" not in dataset:
            return f"Dataset {i} missing 'values' field"
        if not isinstance(dataset["values"], list):
            return f"Dataset {i} 'values' must be a list"

    return None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _error_response(error: str) -> str:
    """Format an error response as JSON."""
    return json.dumps({"success": False, "error": error})


def _success_response(
    *,
    html_path: str,
    png_path: str,
    html_size: int,
    png_size: int,
    plotly_json_path: str | None,
    plotly_json_size: int | None,
    chart_type: str,
    data_points: int,
    series_count: int,
) -> str:
    """Format a success response as JSON."""
    return json.dumps(
        {
            "success": True,
            "html_path": html_path,
            "png_path": png_path,
            "html_size": html_size,
            "png_size": png_size,
            "plotly_json_path": plotly_json_path,
            "plotly_json_size": plotly_json_size,
            "render_contract_version": "plotly-json-v1",
            "chart_type": chart_type,
            "data_points": data_points,
            "series_count": series_count,
        }
    )


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    """Read JSON from stdin, generate chart, write outputs, print result JSON.

    Returns:
        Exit code: 0 = success, 1 = invalid input, 2 = generation error, 3 = file write error.
    """
    # --- Parse input ---
    try:
        input_data: dict[str, Any] = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(_error_response(f"Invalid JSON input: {exc}"))
        return 1

    # --- Validate ---
    validation_error = _validate_input(input_data)
    if validation_error is not None:
        print(_error_response(validation_error))
        return 1

    # --- Generate chart ---
    try:
        fig = _generate_chart(input_data)
    except Exception as exc:
        print(_error_response(f"Chart generation failed: {exc}"))
        return 2

    # --- Write HTML (CDN mode for small file size) ---
    output_html: str = input_data["output_html"]
    output_png: str = input_data["output_png"]
    output_json: str = input_data.get("output_json") or str(
        Path(output_html).with_suffix(".plotly.json")
    )
    width: int = input_data.get("width", 1000)
    height: int = input_data.get("height", 600)
    plotly_json_size: int | None = None
    plotly_json_path: str | None = None

    try:
        fig.write_html(output_html, include_plotlyjs="cdn")
        html_size = Path(output_html).stat().st_size
        if html_size == 0:
            Path(output_html).unlink(missing_ok=True)
            print(_error_response("HTML write produced 0-byte file"))
            return 3
    except Exception as exc:
        print(_error_response(f"HTML write failed: {exc}"))
        return 3

    # --- Write PNG (Kaleido renderer) ---
    try:
        fig.write_image(output_png, width=width, height=height, scale=2)
        png_size = Path(output_png).stat().st_size
        if png_size == 0:
            Path(output_png).unlink(missing_ok=True)
            Path(output_html).unlink(missing_ok=True)
            print(
                _error_response("PNG render produced 0-byte file (Kaleido rendering failed)")
            )
            return 3
    except Exception as exc:
        # Clean up HTML on PNG failure
        Path(output_html).unlink(missing_ok=True)
        print(_error_response(f"PNG write failed: {exc}"))
        return 3

    # --- Write Plotly JSON render contract (best effort) ---
    # This provides a stable, parse-free interactive rendering contract for the frontend.
    try:
        figure_json = fig.to_plotly_json()
        with Path(output_json).open("w", encoding="utf-8") as json_file:
            json.dump(figure_json, json_file, separators=(",", ":"))
        plotly_json_size = Path(output_json).stat().st_size
        if plotly_json_size == 0:
            Path(output_json).unlink(missing_ok=True)
            plotly_json_size = None
            plotly_json_path = None
        else:
            plotly_json_path = output_json
    except Exception as exc:
        # Do not fail the entire chart generation if JSON sidecar fails.
        # HTML+PNG remain valid fallback artifacts.
        print(f"WARNING: Plotly JSON write failed: {exc}", file=sys.stderr)
        Path(output_json).unlink(missing_ok=True)

    # --- Success output ---
    print(
        _success_response(
            html_path=output_html,
            png_path=output_png,
            html_size=html_size,
            png_size=png_size,
            plotly_json_path=plotly_json_path,
            plotly_json_size=plotly_json_size,
            chart_type=input_data["chart_type"],
            data_points=len(input_data["labels"]),
            series_count=len(input_data["datasets"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
