#!/usr/bin/env python3
"""
Generate Plotly comparison charts from JSON input (Phase 3).

Input (JSON via stdin or file):
{
  "title": "Chart Title",
  "metric_name": "Performance Score",
  "lower_is_better": false,
  "points": [
    {"label": "Option A", "value": 95.5, "display_value": "95.5%"},
    {"label": "Option B", "value": 87.2, "display_value": "87.2%"}
  ],
  "output_html": "/home/ubuntu/comparison-chart-abc123.html",
  "output_png": "/home/ubuntu/comparison-chart-abc123.png"
}

Output (JSON to stdout):
{
  "success": true,
  "html_path": "/home/ubuntu/comparison-chart-abc123.html",
  "png_path": "/home/ubuntu/comparison-chart-abc123.png",
  "html_size": 45678,
  "png_size": 123456,
  "data_points": 2
}

Exit codes:
- 0: Success
- 1: Invalid input JSON
- 2: Chart generation failed
- 3: File write failed
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (inlined from generate_plotly_chart.py — no cross-script imports)
# ---------------------------------------------------------------------------

PLOTLY_QUALITATIVE: list[str] = [
    "#636EFA",
    "#EF553B",
    "#00CC96",
    "#AB63FA",
    "#FFA15A",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
]
FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
GRID_COLOR = "rgba(0,0,0,0.06)"
BAR_CORNER_RADIUS = "15%"


# ---------------------------------------------------------------------------
# Inlined helpers (no cross-script imports in sandbox)
# ---------------------------------------------------------------------------


def _looks_temporal(labels: list[str]) -> bool:
    """Detect if labels look like temporal/time-series data."""
    temporal_patterns = [
        r"^\d{4}[-/]\d{1,2}",
        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
        r"^(January|February|March|April|May|June|July|August|September|October|November|December)",
        r"^Q[1-4]\b",
        r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)",
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
        r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
        r"^(Week|W)\s*\d+",
        r"^(FY|H[12])\s*\d+",
    ]
    if not labels:
        return False
    sample = labels[: min(5, len(labels))]
    matches = sum(
        1
        for label in sample
        if any(re.match(p, label, re.IGNORECASE) for p in temporal_patterns)
    )
    return matches > len(sample) / 2


def _auto_orientation(labels: list[str]) -> str:
    """Determine optimal bar orientation based on label characteristics."""
    if not labels:
        return "v"
    if _looks_temporal(labels):
        return "v"
    n_cats = len(labels)
    max_len = max(len(label) for label in labels)
    avg_len = sum(len(label) for label in labels) / n_cats
    if n_cats > 8:
        return "h"
    if max_len > 12:
        return "h"
    if avg_len > 6:
        return "h"
    if n_cats > 5 and avg_len > 4:
        return "h"
    return "v"


def _sanitize_label(label: str) -> str:
    """Remove markdown formatting and clean up label text."""
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", label)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)
    cleaned = re.sub(r"`(.+?)`", r"\1", cleaned)
    cleaned = re.sub(r"__(.+?)__", r"\1", cleaned)
    cleaned = re.sub(r"_(.+?)_", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------


def generate_bar_chart(
    title: str, metric_name: str, points: list[dict], lower_is_better: bool
):
    """Generate a Plotly comparison bar chart with modern styling."""
    import plotly.graph_objects as go

    # Sort points by value (ascending if lower_is_better, descending otherwise)
    sorted_points = sorted(
        points, key=lambda p: p["value"], reverse=not lower_is_better
    )

    # Limit to 8 data points for readability
    if len(sorted_points) > 8:
        sorted_points = sorted_points[:8]

    labels = [_sanitize_label(p["label"]) for p in sorted_points]
    values = [p["value"] for p in sorted_points]
    display_values = [p.get("display_value", str(p["value"])) for p in sorted_points]

    # Smart auto-orientation
    orientation = _auto_orientation(labels)

    # Per-bar coloring from qualitative palette
    colors = [PLOTLY_QUALITATIVE[i % len(PLOTLY_QUALITATIVE)] for i in range(len(labels))]

    if orientation == "h":
        bar_x, bar_y = values, labels
    else:
        bar_x, bar_y = labels, values

    fig = go.Figure(
        data=[
            go.Bar(
                x=bar_x,
                y=bar_y,
                orientation=orientation,
                marker={"color": colors, "line": {"color": "rgba(255,255,255,0.8)", "width": 2}},
                text=display_values,
                textposition="outside",
                textfont={
                    "size": 14,
                    "shadow": "1px 1px 2px rgba(0,0,0,0.1)",
                },
                hovertemplate="%{y}: %{x}<extra></extra>"
                if orientation == "h"
                else "%{x}: %{y}<extra></extra>",
            )
        ]
    )

    direction_text = "Lower is better" if lower_is_better else "Higher is better"
    left_margin = 200 if orientation == "h" else 80

    fig.update_layout(
        title={
            "text": f"{title}<br><sub>{metric_name} ({direction_text})</sub>",
            "font": {"size": 24, "family": FONT_FAMILY, "color": "#111827"},
            "x": 0.0,
            "xanchor": "left",
        },
        xaxis={
            "title": metric_name if orientation == "h" else "",
            "showgrid": True,
            "gridcolor": GRID_COLOR,
            "zeroline": False,
        },
        yaxis={
            "title": "" if orientation == "h" else metric_name,
            "showgrid": orientation != "h",
            "gridcolor": GRID_COLOR,
            "zeroline": False,
        },
        template="plotly_white",
        height=max(400, len(labels) * 60) if orientation == "h" else 600,
        width=1200,
        margin={"l": left_margin, "r": 100, "t": 100, "b": 80},
        font={"size": 14, "family": FONT_FAMILY, "color": "#374151"},
        legend={
            "orientation": "h",
            "y": 1.02,
            "yanchor": "bottom",
            "x": 0.5,
            "xanchor": "center",
        },
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="white",
        barcornerradius=BAR_CORNER_RADIUS,
        bargap=0.15,
    )

    return fig


def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)

        # Validate required fields
        required_fields = [
            "title",
            "metric_name",
            "points",
            "output_html",
            "output_png",
        ]
        missing = [f for f in required_fields if f not in input_data]
        if missing:
            print(
                json.dumps(
                    {"success": False, "error": f"Missing required fields: {missing}"}
                ),
                file=sys.stderr,
            )
            return 1

        title = input_data["title"]
        metric_name = input_data["metric_name"]
        points = input_data["points"]
        lower_is_better = input_data.get("lower_is_better", False)
        output_html = input_data["output_html"]
        output_png = input_data["output_png"]

        # Validate points
        if not points or not isinstance(points, list):
            print(
                json.dumps(
                    {"success": False, "error": "Points must be a non-empty list"}
                ),
                file=sys.stderr,
            )
            return 1

        for i, point in enumerate(points):
            if "label" not in point or "value" not in point:
                print(
                    json.dumps(
                        {"success": False, "error": f"Point {i} missing label or value"}
                    ),
                    file=sys.stderr,
                )
                return 1

        # Generate chart
        try:
            fig = generate_bar_chart(title, metric_name, points, lower_is_better)
        except Exception as e:
            print(
                json.dumps(
                    {"success": False, "error": f"Chart generation failed: {e}"}
                ),
                file=sys.stderr,
            )
            return 2

        # Write HTML (CDN mode for small file size)
        try:
            fig.write_html(output_html, include_plotlyjs="cdn")
            html_size = Path(output_html).stat().st_size
        except Exception as e:
            print(
                json.dumps({"success": False, "error": f"HTML write failed: {e}"}),
                file=sys.stderr,
            )
            return 3

        # Write PNG (Kaleido renderer)
        try:
            fig.write_image(output_png, width=1200, height=fig.layout.height, scale=2)
            png_size = Path(output_png).stat().st_size
        except Exception as e:
            # Clean up HTML on PNG failure
            Path(output_html).unlink(missing_ok=True)
            print(
                json.dumps({"success": False, "error": f"PNG write failed: {e}"}),
                file=sys.stderr,
            )
            return 3

        # Success! Output JSON result
        result = {
            "success": True,
            "html_path": output_html,
            "png_path": output_png,
            "html_size": html_size,
            "png_size": png_size,
            "data_points": len(points),
        }
        print(json.dumps(result))
        return 0

    except json.JSONDecodeError as e:
        print(
            json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}),
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(
            json.dumps({"success": False, "error": f"Unexpected error: {e}"}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
