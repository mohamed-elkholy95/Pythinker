"""Tests for comparison chart generation from markdown reports."""

from app.domain.services.comparison_chart_generator import ComparisonChartGenerator


def test_generate_chart_from_comparison_table():
    generator = ComparisonChartGenerator()

    markdown = """# Model Comparison

## Comparison Table
| Model | Score | Price |
|-------|-------|-------|
| Alpha | 92 | 0.50 |
| Beta | 87 | 0.35 |
| Gamma | 81 | 0.25 |
"""

    result = generator.generate_chart("Model Comparison", markdown)

    assert result is not None
    assert result.chart_kind in {"bar", "matrix"}
    assert result.data_points >= 2
    assert result.width > 0
    assert result.height > 0
    assert result.output_format == "svg"
    assert "<svg" in result.svg_content


def test_generate_chart_returns_none_for_non_comparison_context_without_force():
    generator = ComparisonChartGenerator()

    markdown = """# Project Notes

| Task | Owner | Status |
|------|-------|--------|
| API cleanup | Alice | done |
| UI refresh | Bob | in progress |
"""

    result = generator.generate_chart("Project Notes", markdown)

    assert result is None


def test_force_generation_can_produce_chart_from_generic_table():
    generator = ComparisonChartGenerator()

    markdown = """# Weekly Metrics

| Team | Throughput | Incidents |
|------|------------|-----------|
| Search | 1200 | 3 |
| Infra | 900 | 2 |
"""

    result = generator.generate_chart("Weekly Metrics", markdown, force_generation=True)

    assert result is not None
    assert result.data_points >= 2
    assert "data-chart-kind" in result.svg_content
