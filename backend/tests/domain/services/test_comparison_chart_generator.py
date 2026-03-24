"""Tests for comparison chart generation from markdown reports.

NOTE (Phase 6): SVG generation methods are deprecated in favor of Plotly.
Tests for generate_chart() are kept for backward compatibility verification.
Active tests focus on table extraction methods used by PlotlyChartOrchestrator.
"""

import warnings

from app.domain.services.comparison_chart_generator import ComparisonChartGenerator


def test_generate_chart_from_comparison_table():
    """DEPRECATED TEST: Tests legacy SVG generation (backward compatibility only)."""
    generator = ComparisonChartGenerator()

    markdown = """# Model Comparison

## Comparison Table
| Model | Score | Price |
|-------|-------|-------|
| Alpha | 92 | 0.50 |
| Beta | 87 | 0.35 |
| Gamma | 81 | 0.25 |
"""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = generator.generate_chart("Model Comparison", markdown)

    assert result is not None
    assert result.chart_kind in {"bar", "matrix"}
    assert result.data_points >= 2
    assert result.width > 0
    assert result.height > 0
    assert result.output_format == "svg"
    assert "<svg" in result.svg_content


def test_generate_chart_returns_none_for_non_comparison_context_without_force():
    """DEPRECATED TEST: Tests legacy SVG generation (backward compatibility only)."""
    generator = ComparisonChartGenerator()

    markdown = """# Project Notes

| Task | Owner | Status |
|------|-------|--------|
| API cleanup | Alice | done |
| UI refresh | Bob | in progress |
"""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = generator.generate_chart("Project Notes", markdown)

    assert result is None


def test_force_generation_can_produce_chart_from_generic_table():
    """DEPRECATED TEST: Tests legacy SVG generation (backward compatibility only)."""
    generator = ComparisonChartGenerator()

    markdown = """# Weekly Metrics

| Team | Throughput | Incidents |
|------|------------|-----------|
| Search | 1200 | 3 |
| Infra | 900 | 2 |
"""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = generator.generate_chart("Weekly Metrics", markdown, force_generation=True)

    assert result is not None
    assert result.data_points >= 2
    assert "data-chart-kind" in result.svg_content


# ==================================================================================
# ACTIVE TESTS: Table extraction methods used by PlotlyChartOrchestrator
# ==================================================================================


def test_extract_tables_from_markdown():
    """Test table extraction - actively used by PlotlyChartOrchestrator."""
    generator = ComparisonChartGenerator()

    markdown = """# Model Comparison

## Performance Results
| Model | Latency (ms) | Throughput |
|-------|--------------|------------|
| GPT-4 | 120 | 850 |
| Claude | 95 | 920 |
| Gemini | 110 | 880 |

Some text here.

## Another Table
| Feature | Value |
|---------|-------|
| Speed | Fast |
| Cost | Low |
"""

    tables = generator._extract_tables(markdown)

    assert len(tables) == 2
    assert tables[0].heading == "Performance Results"
    assert len(tables[0].headers) == 3
    assert len(tables[0].rows) == 3
    assert tables[1].heading == "Another Table"
    assert len(tables[1].rows) == 2


def test_select_best_table():
    """Test best table selection - actively used by PlotlyChartOrchestrator."""
    generator = ComparisonChartGenerator()

    markdown = """# Comparison Report

| Small | Data |
|-------|------|
| A | 1 |

## Main Comparison vs Results
| Model | Latency | Score | Price |
|-------|---------|-------|-------|
| Alpha | 100 | 92 | 0.50 |
| Beta | 85 | 87 | 0.35 |
| Gamma | 95 | 81 | 0.25 |
"""

    tables = generator._extract_tables(markdown)
    best_table = generator._select_best_table(tables)

    assert best_table is not None
    assert best_table.heading == "Main Comparison vs Results"
    assert len(best_table.rows) == 3  # Should select the larger table with "vs" hint


def test_is_comparison_context():
    """Test comparison context detection - actively used by PlotlyChartOrchestrator."""
    generator = ComparisonChartGenerator()

    markdown_comparison = """# API Performance Comparison

We compare three models:
| Model | Latency |
|-------|---------|
| A | 100 |
| B | 85 |
"""

    markdown_generic = """# Project Status

| Task | Status |
|------|--------|
| Deploy | Done |
| Test | Pending |
"""

    tables_comparison = generator._extract_tables(markdown_comparison)
    tables_generic = generator._extract_tables(markdown_generic)

    assert generator._is_comparison_context("API Performance Comparison", markdown_comparison, tables_comparison[0])
    assert not generator._is_comparison_context("Project Status", markdown_generic, tables_generic[0])


def test_build_numeric_chart_spec():
    """Test numeric chart spec building - actively used by PlotlyChartOrchestrator."""
    generator = ComparisonChartGenerator()

    markdown = """## Latency Benchmark
| Model | Latency (ms) | Throughput |
|-------|--------------|------------|
| GPT-4 | 120 | 850 |
| Claude | 95 | 920 |
| Gemini | 110 | 880 |
"""

    tables = generator._extract_tables(markdown)
    spec = generator._build_numeric_chart_spec(tables[0], "Latency Benchmark")

    assert spec is not None
    assert spec.title == "Latency Benchmark"
    assert spec.metric_name == "Latency (ms)"
    assert spec.lower_is_better is True  # Latency is lower-is-better
    assert len(spec.points) == 3
    # Should be sorted by latency (lower first)
    assert spec.points[0].label == "Claude"
    assert spec.points[0].value == 95


def test_build_numeric_chart_spec_strips_markdown_from_labels():
    """Labels with markdown formatting should be cleaned."""
    generator = ComparisonChartGenerator()

    markdown = """## Score Comparison
| Product | Score |
|---------|-------|
| **Alpha** | 95 |
| **Beta** | 87 |
| `Gamma` | 81 |
"""

    tables = generator._extract_tables(markdown)
    spec = generator._build_numeric_chart_spec(tables[0], "Score Comparison")

    assert spec is not None
    labels = [p.label for p in spec.points]
    assert "Alpha" in labels
    assert "Beta" in labels
    assert "Gamma" in labels
    # No markdown syntax should remain
    assert all("**" not in label and "`" not in label for label in labels)


def test_build_numeric_chart_spec_rejects_spec_sheet():
    """A single-product spec sheet (heterogeneous units) should NOT produce a chart."""
    generator = ComparisonChartGenerator()

    # This is the exact pattern from the bug: a MacBook spec table
    markdown = """## Technical Specifications
| **Spec** | **Value** |
|----------|-----------|
| **Starting Price** | ~$2,499 |
| **Storage (base config)** | 512 GB SSD |
| **Memory Bandwidth** | 273 GB/s |
| **Unified Memory** | 24 GB |
| **GPU Cores** | 20-core |
| **Neural Engine** | 16-core (enhanced) |
| **CPU Cores** | 15-core (11P + 4E) |
| **Display Size Options** | 14" Liquid Retina XDR |
"""

    tables = generator._extract_tables(markdown)
    assert len(tables) >= 1

    spec = generator._build_numeric_chart_spec(tables[0], "MacBook Pro M5 Pro Specs")
    # Should return None — this is a spec sheet, not a comparison
    assert spec is None


def test_build_numeric_chart_spec_accepts_valid_comparison():
    """A valid comparison (same metric, comparable items) should still produce a chart."""
    generator = ComparisonChartGenerator()

    markdown = """## Price Comparison
| Laptop | Price ($) |
|--------|-----------|
| MacBook Pro | 2499 |
| ThinkPad X1 | 1899 |
| Dell XPS 15 | 1799 |
"""

    tables = generator._extract_tables(markdown)
    spec = generator._build_numeric_chart_spec(tables[0], "Price Comparison")

    assert spec is not None
    assert len(spec.points) == 3
    # Magnitude ratio is ~1.4 — well under threshold
    assert spec.metric_name == "Price ($)"


def test_strip_markdown():
    """Test markdown stripping helper."""
    gen = ComparisonChartGenerator()

    assert gen._strip_markdown("**bold text**") == "bold text"
    assert gen._strip_markdown("*italic*") == "italic"
    assert gen._strip_markdown("`code`") == "code"
    assert gen._strip_markdown("__underline bold__") == "underline bold"
    assert gen._strip_markdown("[link](http://example.com)") == "link"
    assert gen._strip_markdown("no formatting") == "no formatting"
    assert gen._strip_markdown("**Starting Price**") == "Starting Price"


def test_is_heterogeneous_data_magnitude_spread():
    """Values with >100x magnitude spread should be rejected."""
    from app.domain.services.comparison_chart_generator import _NumericPoint

    gen = ComparisonChartGenerator()

    points = [
        _NumericPoint(label="Price", value=2499, display_value="$2,499"),
        _NumericPoint(label="Memory", value=24, display_value="24 GB"),
        _NumericPoint(label="Cores", value=20, display_value="20-core"),
    ]
    assert gen._is_heterogeneous_data(points) is True


def test_is_heterogeneous_data_uniform_values():
    """Values with similar magnitudes should NOT be rejected."""
    from app.domain.services.comparison_chart_generator import _NumericPoint

    gen = ComparisonChartGenerator()

    points = [
        _NumericPoint(label="Model A", value=92, display_value="92%"),
        _NumericPoint(label="Model B", value=87, display_value="87%"),
        _NumericPoint(label="Model C", value=81, display_value="81%"),
    ]
    assert gen._is_heterogeneous_data(points) is False


# ===========================================================================
# Bug fix: Credit card / product feature tables should NOT produce charts
# ===========================================================================


def test_parse_number_rejects_citation_references():
    """Citation numbers like [23][24][31] should NOT be parsed as numeric values."""
    gen = ComparisonChartGenerator()
    assert gen._parse_number("[23][24][31]") is None
    assert gen._parse_number("[5]") is None
    assert gen._parse_number("[1][2]") is None


def test_parse_number_accepts_plain_numbers():
    """Regular numbers should still be parsed correctly."""
    gen = ComparisonChartGenerator()
    assert gen._parse_number("3%") == 3.0
    assert gen._parse_number("$0") == 0.0
    assert gen._parse_number("5.5") == 5.5
    assert gen._parse_number("1,200") == 1200.0


def test_build_numeric_chart_spec_rejects_credit_card_features():
    """A single credit card's features should NOT produce a bar chart.

    This is the exact bug: the system extracted numbers from mixed-type
    feature values (3% cash back, $0 fee, 5% travel portal) and created
    a nonsensical bar chart with citation numbers as the tallest bars.
    """
    gen = ComparisonChartGenerator()

    markdown = """## Robinhood Gold Card Features
| Feature | Details | Source |
|---------|---------|--------|
| Annual Fee | $0 | [23] |
| Foreign Transaction Fee | $0 | [24] |
| Rewards Rate | 3% flat cash back | [23][24][31] |
| Travel Portal | 5% travel portal | [23] |
| Sign-up Bonus | None | [31] |
"""

    tables = gen._extract_tables(markdown)
    spec = gen._build_numeric_chart_spec(tables[0], "Robinhood Gold Card")
    # Must return None — this is a single-product feature list, not a comparison
    assert spec is None


def test_is_heterogeneous_detects_financial_spec_sheet():
    """Financial product features (fee, rate, reward) should be detected as spec-sheet data."""
    from app.domain.services.comparison_chart_generator import _NumericPoint

    gen = ComparisonChartGenerator()

    points = [
        _NumericPoint(label="Annual Fee", value=0.0, display_value="$0"),
        _NumericPoint(label="Foreign Transaction Fee", value=0.0, display_value="$0"),
        _NumericPoint(label="Rewards Rate", value=3.0, display_value="3%"),
        _NumericPoint(label="Travel Portal", value=5.0, display_value="5%"),
    ]
    assert gen._is_heterogeneous_data(points) is True


def test_lower_is_better_includes_fee():
    """The 'fee' keyword should be detected as lower-is-better."""
    gen = ComparisonChartGenerator()
    assert any(
        hint in "annual fee" for hint in gen._LOWER_IS_BETTER_HINTS
    ), "Expected 'fee' to be in _LOWER_IS_BETTER_HINTS"
