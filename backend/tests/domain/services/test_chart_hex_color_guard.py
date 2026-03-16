"""Tests for the CSS hex color guard in ComparisonChartGenerator._parse_number().

Regression suite ensuring CSS design-system tables (containing hex color tokens like
#2563eb or CSS custom properties like --btn-primary-bg) are never treated as numeric
data and do not produce nonsensical bar charts.
"""

import pytest

from app.domain.services.comparison_chart_generator import (
    ComparisonChartGenerator,
    _MarkdownTable,
)


@pytest.fixture
def generator() -> ComparisonChartGenerator:
    return ComparisonChartGenerator()


# ---------------------------------------------------------------------------
# _parse_number: hex color guard
# ---------------------------------------------------------------------------


class TestParseNumberHexColorGuard:
    """_parse_number must return None for CSS hex color and custom-property values."""

    def test_six_digit_hex_color_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """#2563eb is a CSS hex color — not a number."""
        assert generator._parse_number("#2563eb") is None

    def test_three_digit_hex_color_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """#fff is a shorthand CSS hex color — not a number."""
        assert generator._parse_number("#fff") is None

    def test_eight_digit_hex_color_with_alpha_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """#504143cc is a CSS hex color with alpha channel — not a number."""
        assert generator._parse_number("#504143c") is None

    def test_css_custom_property_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """--btn-primary-bg is a CSS custom property token — not a number."""
        assert generator._parse_number("--btn-primary-bg") is None

    def test_four_digit_hex_color_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """#1d4ed8 — the digit '1' at position 1 must not be parsed as the number 1."""
        assert generator._parse_number("#1d4ed8") is None

    def test_css_custom_property_with_dash_in_name_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """--color-primary-500 is a CSS custom property — not a number."""
        assert generator._parse_number("--color-primary-500") is None

    def test_css_custom_property_bare_double_dash_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """-- alone is already in the n/a-equivalent set and must return None."""
        assert generator._parse_number("--") is None

    def test_hex_color_with_surrounding_whitespace_returns_none(self, generator: ComparisonChartGenerator) -> None:
        """Whitespace around the hex token must not bypass the guard."""
        assert generator._parse_number("  #2563eb  ") is None


# ---------------------------------------------------------------------------
# _parse_number: no-regression for valid numeric inputs
# ---------------------------------------------------------------------------


class TestParseNumberNoRegression:
    """Existing numeric parsing must be unaffected by the hex-color guard."""

    def test_plain_float_returns_float(self, generator: ComparisonChartGenerator) -> None:
        assert generator._parse_number("42.5") == pytest.approx(42.5)

    def test_comma_separated_integer_returns_float(self, generator: ComparisonChartGenerator) -> None:
        assert generator._parse_number("1,234") == pytest.approx(1234.0)

    def test_na_returns_none(self, generator: ComparisonChartGenerator) -> None:
        assert generator._parse_number("n/a") is None

    def test_empty_string_returns_none(self, generator: ComparisonChartGenerator) -> None:
        assert generator._parse_number("") is None

    def test_integer_string_returns_float(self, generator: ComparisonChartGenerator) -> None:
        assert generator._parse_number("100") == pytest.approx(100.0)

    def test_negative_number_returns_float(self, generator: ComparisonChartGenerator) -> None:
        assert generator._parse_number("-3.14") == pytest.approx(-3.14)

    def test_number_with_unit_returns_float(self, generator: ComparisonChartGenerator) -> None:
        """A value like '92ms' should still parse — the number is extracted."""
        result = generator._parse_number("92ms")
        assert result == pytest.approx(92.0)


# ---------------------------------------------------------------------------
# _numeric_cell_count: hex colors are not counted
# ---------------------------------------------------------------------------


class TestNumericCellCount:
    """_numeric_cell_count must not count hex color cells as numeric."""

    def _make_table(self, headers: list[str], rows: list[list[str]]) -> _MarkdownTable:
        return _MarkdownTable(heading=None, headers=headers, rows=rows)

    def test_hex_color_cells_not_counted(self, generator: ComparisonChartGenerator) -> None:
        table = self._make_table(
            headers=["Token", "Light", "Dark"],
            rows=[
                ["--btn-bg", "#2563eb", "#1d4ed8"],
                ["--btn-text", "#ffffff", "#ffffff"],
                ["--btn-border", "#1e40af", "#3b82f6"],
            ],
        )
        assert generator._numeric_cell_count(table) == 0

    def test_mixed_table_counts_only_numeric_cells(self, generator: ComparisonChartGenerator) -> None:
        table = self._make_table(
            headers=["Model", "Score", "Color"],
            rows=[
                ["Alpha", "92", "#2563eb"],
                ["Beta", "87", "#1d4ed8"],
            ],
        )
        # Only the "Score" cells (92, 87) are numeric — 2 cells
        assert generator._numeric_cell_count(table) == 2


# ---------------------------------------------------------------------------
# _select_best_table: hex-only table scores lower than numeric table
# ---------------------------------------------------------------------------


class TestSelectBestTable:
    """A table with only hex color values should score lower than a numeric table."""

    def _make_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        heading: str | None = None,
    ) -> _MarkdownTable:
        return _MarkdownTable(heading=heading, headers=headers, rows=rows)

    def test_numeric_table_preferred_over_hex_only_table(self, generator: ComparisonChartGenerator) -> None:
        # hex_table: 3 rows × 3 headers = 9 base score, 0 numeric cells → total 9
        # numeric_table: 3 rows × 2 headers = 6 base score, 3 numeric cells (+6) → total 12
        # numeric_table must win despite fewer columns
        hex_table = self._make_table(
            headers=["Token", "Light", "Dark"],
            rows=[
                ["--btn-bg", "#2563eb", "#1d4ed8"],
                ["--btn-text", "#ffffff", "#eeeeee"],
                ["--btn-border", "#1e40af", "#3b82f6"],
            ],
        )
        numeric_table = self._make_table(
            headers=["Model", "Score"],
            rows=[
                ["Alpha", "92"],
                ["Beta", "87"],
                ["Gamma", "81"],
            ],
        )
        selected = generator._select_best_table([hex_table, numeric_table])
        assert selected is numeric_table

    def test_select_best_table_still_returns_something_for_hex_only_input(
        self, generator: ComparisonChartGenerator
    ) -> None:
        """When there is only a hex table, _select_best_table returns it (no crash)."""
        hex_table = self._make_table(
            headers=["Token", "Value"],
            rows=[["--btn-bg", "#2563eb"], ["--btn-text", "#ffffff"]],
        )
        result = generator._select_best_table([hex_table])
        assert result is hex_table


# ---------------------------------------------------------------------------
# _build_numeric_chart_spec: hex-only value columns produce no spec
# ---------------------------------------------------------------------------


class TestBuildNumericChartSpec:
    """_build_numeric_chart_spec must return None when all value columns are hex colors."""

    def _make_table(self, headers: list[str], rows: list[list[str]]) -> _MarkdownTable:
        return _MarkdownTable(heading="Color System (CSS Custom Properties)", headers=headers, rows=rows)

    def test_returns_none_for_all_hex_color_columns(self, generator: ComparisonChartGenerator) -> None:
        """A pure CSS design-system table must not produce a chart spec."""
        table = self._make_table(
            headers=["Token", "Light Theme", "Dark Theme"],
            rows=[
                ["--btn-bg", "#2563eb", "#1d4ed8"],
                ["--btn-text", "#ffffff", "#eeeeee"],
                ["--btn-border", "#1e40af", "#3b82f6"],
                ["--btn-hover", "#1d4ed8", "#2563eb"],
                ["--btn-active", "#1e3a8a", "#1d4ed8"],
            ],
        )
        spec = generator._build_numeric_chart_spec(table, "Design Tokens")
        assert spec is None

    def test_returns_spec_for_numeric_columns(self, generator: ComparisonChartGenerator) -> None:
        """A normal numeric table must still produce a valid chart spec."""
        table = _MarkdownTable(
            heading="Model Benchmark",
            headers=["Model", "Score"],
            rows=[
                ["Alpha", "92"],
                ["Beta", "87"],
                ["Gamma", "81"],
            ],
        )
        spec = generator._build_numeric_chart_spec(table, "Model Benchmark")
        assert spec is not None
        assert len(spec.points) >= 2
