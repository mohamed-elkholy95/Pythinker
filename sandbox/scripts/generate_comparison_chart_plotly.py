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

import json
import sys
from pathlib import Path


def configure_kaleido():
    """Configure Kaleido defaults for consistent output.

    Note: Kaleido template API was removed in newer versions.
    Configuration is now passed directly to write_image().
    """
    pass  # No-op - configuration passed to write_image instead


def generate_bar_chart(
    title: str, metric_name: str, points: list[dict], lower_is_better: bool
):
    """Generate a Plotly bar chart."""
    import plotly.graph_objects as go

    # Sort points by value (ascending if lower_is_better, descending otherwise)
    sorted_points = sorted(
        points, key=lambda p: p["value"], reverse=not lower_is_better
    )

    # Limit to 8 data points for readability
    if len(sorted_points) > 8:
        sorted_points = sorted_points[:8]

    labels = [p["label"] for p in sorted_points]
    values = [p["value"] for p in sorted_points]
    display_values = [p.get("display_value", str(p["value"])) for p in sorted_points]

    # Alternating colors for visual distinction
    colors = ["#2563eb" if i % 2 == 0 else "#0891b2" for i in range(len(labels))]

    fig = go.Figure(
        data=[
            go.Bar(
                x=values,
                y=labels,
                orientation="h",
                marker=dict(color=colors),
                text=display_values,
                textposition="outside",
                textfont=dict(size=14),
            )
        ]
    )

    direction_text = "Lower is better" if lower_is_better else "Higher is better"
    fig.update_layout(
        title=dict(
            text=f"{title}<br><sub>{metric_name} ({direction_text})</sub>",
            font=dict(size=24),
        ),
        xaxis=dict(title=metric_name, showgrid=True, gridcolor="lightgray"),
        yaxis=dict(title="", showgrid=False),
        template="plotly_white",
        height=max(400, len(labels) * 60),  # Dynamic height based on data points
        width=1200,
        margin=dict(l=200, r=100, t=100, b=80),
        font=dict(size=14),
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

        configure_kaleido()

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

        # Write PNG (Kaleido + Chromium)
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
