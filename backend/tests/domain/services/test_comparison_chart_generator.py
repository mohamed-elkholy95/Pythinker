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


class TestSelectBestTableRowBonus:
    """Verify larger tables are preferred over smaller high-density tables."""

    def test_larger_table_preferred_over_small_dense_table(self):
        """A 10-row table should outscore a 3-row table even if the 3-row
        table has higher numeric density per cell."""
        generator = ComparisonChartGenerator()

        markdown = """# GitHub Trending Report

## Quick Stats
| Metric | Value | Change |
|--------|-------|--------|
| Stars | 12500 | +500 |
| Forks | 3200 | +120 |
| Issues | 845 | -30 |

## Top 10 Trending Repositories
| Repository | Stars | Language | Description |
|-----------|-------|----------|-------------|
| repo-alpha | 15000 | Python | ML framework |
| repo-beta | 12000 | Rust | Systems tool |
| repo-gamma | 9500 | TypeScript | Web framework |
| repo-delta | 8200 | Go | Cloud native |
| repo-epsilon | 7100 | Python | Data science |
| repo-zeta | 6300 | JavaScript | UI library |
| repo-eta | 5800 | Rust | CLI toolkit |
| repo-theta | 4900 | Python | NLP library |
| repo-iota | 4200 | Go | API gateway |
| repo-kappa | 3700 | TypeScript | State management |
"""
        tables = generator._extract_tables(markdown)
        assert len(tables) == 2

        best = generator._select_best_table(tables)
        assert best is not None
        assert len(best.rows) == 10, f"Expected 10-row table, got {len(best.rows)}-row table"

    def test_row_count_bonus_applied(self):
        """Tables with 5+ rows should receive a bonus to prevent
        small dense tables from winning.

        Without the row bonus the small table wins:
          small: 2 rows * 5 headers = 10 + 10 numeric * 2 = 30
          large: 5 rows * 3 headers = 15 + 5 numeric * 2  = 25
        With the row bonus (rows*3 for >=5):
          large gets +15 → 40, beating the small table's 30.
        """
        generator = ComparisonChartGenerator()

        markdown = """# Report

## Small Table
| A | B | C | D | E |
|---|---|---|---|---|
| 10 | 20 | 30 | 40 | 50 |
| 60 | 70 | 80 | 90 | 100 |

## Large Table
| Name | Value | Notes |
|------|-------|-------|
| Alpha | 10 | Good |
| Beta | 20 | OK |
| Gamma | 30 | Review |
| Delta | 40 | Good |
| Epsilon | 50 | Fine |
"""
        tables = generator._extract_tables(markdown)
        best = generator._select_best_table(tables)
        assert best is not None
        assert len(best.rows) >= 5
