"""Generate comparison chart SVG artifacts from markdown reports.

DEPRECATION NOTICE (Phase 6 - Plotly Migration):
    - SVG generation methods (generate_chart, _render_bar_chart, _render_matrix_chart)
      are DEPRECATED and will be removed in a future version.
    - Use PlotlyChartOrchestrator for chart generation instead.
    - Table extraction methods (_extract_tables, _select_best_table, etc.) are still
      actively used by PlotlyChartOrchestrator and should NOT be removed.
"""

from __future__ import annotations

import html
import logging
import re
import warnings
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChartGenerationResult:
    """Result of chart generation for a report."""

    svg_content: str
    chart_kind: str
    metric_name: str | None
    data_points: int
    width: int
    height: int
    output_format: str = "svg"


@dataclass(frozen=True)
class _MarkdownTable:
    heading: str | None
    headers: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class _NumericPoint:
    label: str
    value: float
    display_value: str


@dataclass(frozen=True)
class _NumericChartSpec:
    title: str
    metric_name: str
    lower_is_better: bool
    points: list[_NumericPoint]


@dataclass(frozen=True)
class _MatrixChartSpec:
    title: str
    headers: list[str]
    rows: list[list[str]]


class ComparisonChartGenerator:
    """Generate an SVG comparison chart from markdown report content."""

    _HEADING_PATTERN = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
    _VS_PATTERN = re.compile(r"\bvs\.?\b|\bversus\b|\bcompare\b|\bcomparison\b", re.IGNORECASE)
    _NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
    _HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3,8}$")
    _COMPARISON_HINTS = (
        "comparison",
        "compare",
        "versus",
        "vs",
        "alternative",
        "option",
        "benchmark",
        "feature",
        "criteria",
        "pros",
        "cons",
        "winner",
        "price",
        "cost",
        "score",
        "rating",
        "latency",
        "performance",
    )
    _LOWER_IS_BETTER_HINTS = ("latency", "cost", "price", "time", "delay", "error", "memory")

    def generate_chart(
        self,
        report_title: str,
        markdown_content: str,
        *,
        force_generation: bool = False,
    ) -> ChartGenerationResult | None:
        """Return a chart if the report appears to be a comparison report.

        DEPRECATED: SVG chart generation is deprecated. Use PlotlyChartOrchestrator instead.
        This method is kept for backward compatibility only.
        """
        warnings.warn(
            "ComparisonChartGenerator.generate_chart() is deprecated. "
            "Use PlotlyChartOrchestrator for Plotly-based chart generation.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not markdown_content.strip():
            return None

        tables = self._extract_tables(markdown_content)
        if not tables:
            return None

        table = self._select_best_table(tables)
        if table is None:
            return None

        if not force_generation and not self._is_comparison_context(report_title, markdown_content, table):
            return None

        numeric_spec = self._build_numeric_chart_spec(table, report_title)
        if numeric_spec:
            svg, width, height = self._render_bar_chart(numeric_spec)
            return ChartGenerationResult(
                svg_content=svg,
                chart_kind="bar",
                metric_name=numeric_spec.metric_name,
                data_points=len(numeric_spec.points),
                width=width,
                height=height,
            )

        matrix_spec = self._build_matrix_chart_spec(table, report_title)
        if matrix_spec:
            svg, width, height = self._render_matrix_chart(matrix_spec)
            return ChartGenerationResult(
                svg_content=svg,
                chart_kind="matrix",
                metric_name=None,
                data_points=len(matrix_spec.rows),
                width=width,
                height=height,
            )

        return None

    # ==================================================================================
    # TABLE EXTRACTION METHODS (ACTIVELY USED BY PlotlyChartOrchestrator)
    # These methods extract and analyze markdown tables for chart generation.
    # DO NOT remove or deprecate these - they are core functionality.
    # ==================================================================================

    def _extract_tables(self, markdown_content: str) -> list[_MarkdownTable]:
        lines = markdown_content.splitlines()
        tables: list[_MarkdownTable] = []
        current_heading: str | None = None

        i = 0
        while i < len(lines):
            line = lines[i]
            heading_match = self._HEADING_PATTERN.match(line)
            if heading_match:
                current_heading = heading_match.group(1).strip()
                i += 1
                continue

            if i + 1 >= len(lines):
                break

            header_line = line
            separator_line = lines[i + 1]
            if "|" not in header_line or not self._is_separator_row(separator_line):
                i += 1
                continue

            headers = self._split_row(header_line)
            if len(headers) < 2:
                i += 1
                continue

            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines):
                row_line = lines[j]
                if not row_line.strip() or "|" not in row_line or self._is_separator_row(row_line):
                    break
                row = self._normalize_row(self._split_row(row_line), len(headers))
                if any(cell for cell in row):
                    rows.append(row)
                j += 1

            if len(rows) >= 2:
                tables.append(_MarkdownTable(heading=current_heading, headers=headers, rows=rows))

            i = j

        return tables

    def _select_best_table(self, tables: list[_MarkdownTable]) -> _MarkdownTable | None:
        best: _MarkdownTable | None = None
        best_score = -1
        for table in tables:
            score = len(table.rows) * len(table.headers)
            numeric_density = self._numeric_cell_count(table)
            score += numeric_density * 2
            if table.heading and self._VS_PATTERN.search(table.heading):
                score += 12
            if self._VS_PATTERN.search(" ".join(table.headers)):
                score += 8
            if score > best_score:
                best = table
                best_score = score
        return best

    def _is_comparison_context(self, report_title: str, markdown_content: str, table: _MarkdownTable) -> bool:
        context = " ".join(
            [
                report_title,
                table.heading or "",
                " ".join(table.headers),
                markdown_content[:2000],
            ]
        ).lower()

        if self._VS_PATTERN.search(context):
            return True

        hits = sum(1 for hint in self._COMPARISON_HINTS if hint in context)
        return hits >= 2

    def _build_numeric_chart_spec(self, table: _MarkdownTable, report_title: str) -> _NumericChartSpec | None:
        label_column = 0
        best_metric_index: int | None = None
        best_points: list[_NumericPoint] = []

        for col_index in range(1, len(table.headers)):
            points: list[_NumericPoint] = []
            seen_labels: set[str] = set()
            for row in table.rows:
                label = row[label_column].strip() or f"Item {len(points) + 1}"
                normalized_label = label.lower()
                if normalized_label in seen_labels:
                    continue

                parsed = self._parse_number(row[col_index])
                if parsed is None:
                    continue

                seen_labels.add(normalized_label)
                points.append(_NumericPoint(label=label, value=parsed, display_value=row[col_index].strip()))

            if len(points) >= 2 and len(points) > len(best_points):
                best_metric_index = col_index
                best_points = points

        if best_metric_index is None or len(best_points) < 2:
            return None

        metric_name = table.headers[best_metric_index].strip() or "Score"
        lower_is_better = any(hint in metric_name.lower() for hint in self._LOWER_IS_BETTER_HINTS)

        sorted_points = sorted(best_points, key=lambda point: point.value, reverse=not lower_is_better)
        limited_points = sorted_points[:8]

        title = table.heading or report_title or "Comparison Chart"
        return _NumericChartSpec(
            title=title,
            metric_name=metric_name,
            lower_is_better=lower_is_better,
            points=limited_points,
        )

    def _build_matrix_chart_spec(self, table: _MarkdownTable, report_title: str) -> _MatrixChartSpec | None:
        if len(table.headers) < 2 or len(table.rows) < 2:
            return None

        max_columns = min(len(table.headers), 5)
        headers = table.headers[:max_columns]
        rows = [self._normalize_row(row[:max_columns], max_columns) for row in table.rows[:8]]

        title = table.heading or report_title or "Comparison Matrix"
        return _MatrixChartSpec(title=title, headers=headers, rows=rows)

    # ==================================================================================
    # SVG RENDERING METHODS (DEPRECATED - Phase 6)
    # These methods generate SVG charts and are replaced by Plotly.
    # Kept for backward compatibility only. Use PlotlyChartOrchestrator instead.
    # ==================================================================================

    def _render_bar_chart(self, spec: _NumericChartSpec) -> tuple[str, int, int]:
        width = 1240
        left_margin = 290
        right_margin = 140
        top_margin = 180
        row_height = 78
        bottom_margin = 120
        chart_height = max(1, len(spec.points)) * row_height
        height = top_margin + chart_height + bottom_margin
        max_value = max(point.value for point in spec.points) or 1.0
        bar_max_width = width - left_margin - right_margin

        bar_blocks: list[str] = []
        for index, point in enumerate(spec.points):
            y = top_margin + index * row_height
            ratio = max(0.0, point.value) / max_value
            bar_width = max(8.0, ratio * bar_max_width)
            fill = "#2563eb" if index % 2 == 0 else "#0891b2"
            escaped_label = html.escape(self._truncate(point.label, 28))
            escaped_value = html.escape(point.display_value or f"{point.value:.2f}")

            bar_blocks.extend(
                [
                    f'<text x="{left_margin - 16}" y="{y + 38}" text-anchor="end" '
                    f'font-size="24" fill="#0f172a">{escaped_label}</text>',
                    f'<rect x="{left_margin}" y="{y + 14}" width="{bar_width:.2f}" height="34" '
                    f'rx="10" fill="{fill}" opacity="0.9" />',
                    f'<text x="{left_margin + bar_width + 12:.2f}" y="{y + 38}" text-anchor="start" '
                    f'font-size="22" fill="#0f172a">{escaped_value}</text>',
                ]
            )

        escaped_title = html.escape(self._truncate(spec.title, 80))
        escaped_metric = html.escape(spec.metric_name)
        direction = "Lower is better" if spec.lower_is_better else "Higher is better"
        escaped_direction = html.escape(direction)

        body = "\n    ".join(bar_blocks)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" data-chart-kind="bar">\n'
            "  <defs>\n"
            '    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">\n'
            '      <stop offset="0%" stop-color="#f8fbff" />\n'
            '      <stop offset="100%" stop-color="#eff6ff" />\n'
            "    </linearGradient>\n"
            "  </defs>\n"
            f'  <rect x="0" y="0" width="{width}" height="{height}" rx="28" fill="url(#bg)" />\n'
            f'  <text x="66" y="68" font-size="40" font-weight="700" fill="#0f172a">{escaped_title}</text>\n'
            f'  <text x="66" y="112" font-size="24" fill="#334155">Metric: {escaped_metric} ({escaped_direction})</text>\n'
            f'  <line x1="{left_margin}" y1="{top_margin - 8}" x2="{left_margin}" y2="{height - bottom_margin + 18}" '
            'stroke="#94a3b8" stroke-width="2" />\n'
            f"  {body}\n"
            f'  <text x="{width - 66}" y="{height - 34}" text-anchor="end" font-size="19" fill="#64748b">'
            "Generated automatically from report comparison data</text>\n"
            "</svg>\n"
        )
        return svg, width, height

    def _render_matrix_chart(self, spec: _MatrixChartSpec) -> tuple[str, int, int]:
        row_count = len(spec.rows)
        col_count = len(spec.headers)
        first_col_width = 280
        cell_width = 180
        table_width = first_col_width + max(0, col_count - 1) * cell_width
        width = table_width + 120
        row_height = 56
        table_top = 140
        height = table_top + (row_count + 1) * row_height + 70

        escaped_title = html.escape(self._truncate(spec.title, 72))

        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" data-chart-kind="matrix">',
            '  <rect x="0" y="0" width="100%" height="100%" rx="24" fill="#f8fafc" />',
            f'  <text x="52" y="70" font-size="36" font-weight="700" fill="#0f172a">{escaped_title}</text>',
            '  <text x="52" y="104" font-size="20" fill="#475569">Comparison matrix extracted from the report</text>',
        ]

        start_x = 52
        for col_index, header in enumerate(spec.headers):
            x = start_x + (0 if col_index == 0 else first_col_width + (col_index - 1) * cell_width)
            width_for_col = first_col_width if col_index == 0 else cell_width
            lines.append(
                f'  <rect x="{x}" y="{table_top}" width="{width_for_col}" height="{row_height}" '
                'fill="#1e3a8a" opacity="0.95" />'
            )
            lines.append(
                f'  <text x="{x + 12}" y="{table_top + 36}" font-size="19" font-weight="600" fill="#ffffff">'
                f"{html.escape(self._truncate(header, 18))}</text>"
            )

        for row_index, row in enumerate(spec.rows):
            y = table_top + (row_index + 1) * row_height
            row_bg = "#ffffff" if row_index % 2 == 0 else "#f1f5f9"

            for col_index, cell in enumerate(row):
                x = start_x + (0 if col_index == 0 else first_col_width + (col_index - 1) * cell_width)
                width_for_col = first_col_width if col_index == 0 else cell_width
                lines.append(
                    f'  <rect x="{x}" y="{y}" width="{width_for_col}" height="{row_height}" '
                    f'fill="{row_bg}" stroke="#cbd5e1" stroke-width="1" />'
                )
                font_weight = "600" if col_index == 0 else "400"
                max_len = 22 if col_index == 0 else 18
                lines.append(
                    f'  <text x="{x + 12}" y="{y + 36}" font-size="18" font-weight="{font_weight}" fill="#0f172a">'
                    f"{html.escape(self._truncate(cell, max_len))}</text>"
                )

        lines.append("</svg>")
        return "\n".join(lines) + "\n", width, height

    def _numeric_cell_count(self, table: _MarkdownTable) -> int:
        return sum(1 for row in table.rows for cell in row if self._parse_number(cell) is not None)

    def _is_separator_row(self, line: str) -> bool:
        cells = self._split_row(line)
        if not cells:
            return False
        return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) is not None for cell in cells)

    def _split_row(self, line: str) -> list[str]:
        stripped = line.strip()
        if "|" not in stripped:
            return []
        stripped = stripped.removeprefix("|").removesuffix("|")
        return [cell.strip() for cell in stripped.split("|")]

    def _normalize_row(self, row: list[str], target_size: int) -> list[str]:
        if len(row) >= target_size:
            return row[:target_size]
        return [*row, *([""] * (target_size - len(row)))]

    def _parse_number(self, raw_value: str) -> float | None:
        cleaned = raw_value.strip().lower()
        if not cleaned or cleaned in {"n/a", "na", "-", "--", "none"}:
            return None

        stripped = raw_value.strip()
        if self._HEX_COLOR_PATTERN.match(stripped) or stripped.startswith("--"):
            return None

        match = self._NUMBER_PATTERN.search(raw_value)
        if not match:
            return None

        number_text = match.group(0).replace(",", "")
        try:
            return float(number_text)
        except ValueError:
            logger.debug("Unable to parse numeric value from comparison cell: %s", raw_value)
            return None

    def _truncate(self, text: str, max_chars: int) -> str:
        value = text.strip()
        if len(value) <= max_chars:
            return value
        return f"{value[: max_chars - 3].rstrip()}..."
