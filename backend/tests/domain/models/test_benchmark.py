"""Tests for app.domain.models.benchmark — benchmark and metric extraction models.

Covers: BenchmarkCategory, BenchmarkUnit, ExtractedBenchmark, BenchmarkComparison,
BenchmarkExtractionResult, BenchmarkQuery.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.models.benchmark import (
    BenchmarkCategory,
    BenchmarkComparison,
    BenchmarkExtractionResult,
    BenchmarkQuery,
    BenchmarkUnit,
    ExtractedBenchmark,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_benchmark(**kwargs) -> ExtractedBenchmark:
    defaults = {
        "name": "MMLU Score",
        "value": 86.5,
        "unit": BenchmarkUnit.PERCENTAGE,
        "category": BenchmarkCategory.ACCURACY,
        "source_url": "https://example.com/benchmark",
        "extracted_text": "GPT-4 scored 86.5% on MMLU",
        "subject": "GPT-4",
    }
    defaults.update(kwargs)
    return ExtractedBenchmark(**defaults)


# ---------------------------------------------------------------------------
# ExtractedBenchmark
# ---------------------------------------------------------------------------
class TestExtractedBenchmark:
    def test_creation(self):
        b = _make_benchmark()
        assert b.name == "MMLU Score"
        assert b.value == 86.5
        assert b.subject == "GPT-4"

    def test_empty_string_value_rejected(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            _make_benchmark(value="")

    def test_string_value_accepted(self):
        b = _make_benchmark(value="N/A")
        assert b.value == "N/A"

    def test_get_display_value_with_unit(self):
        b = _make_benchmark(value=86.5, unit=BenchmarkUnit.PERCENTAGE)
        assert b.get_display_value() == "86.5 percentage"

    def test_get_display_value_custom_unit(self):
        b = _make_benchmark(value="100", unit=BenchmarkUnit.CUSTOM, custom_unit="FLOPS")
        assert b.get_display_value() == "100 FLOPS"

    def test_defaults(self):
        b = _make_benchmark()
        assert b.confidence == 0.7
        assert b.is_verified is False
        assert b.comparison_baseline is None

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            _make_benchmark(confidence=-0.1)
        with pytest.raises(ValidationError):
            _make_benchmark(confidence=1.1)


# ---------------------------------------------------------------------------
# BenchmarkComparison
# ---------------------------------------------------------------------------
class TestBenchmarkComparison:
    def test_sorted_entries(self):
        comp = BenchmarkComparison(
            benchmark_name="MMLU",
            category=BenchmarkCategory.ACCURACY,
            unit=BenchmarkUnit.PERCENTAGE,
            entries=[
                {"subject": "GPT-4", "value": 86.5},
                {"subject": "Claude", "value": 88.0},
                {"subject": "Gemini", "value": 85.0},
            ],
        )
        sorted_e = comp.sorted_entries
        assert sorted_e[0]["subject"] == "Claude"
        assert sorted_e[-1]["subject"] == "Gemini"

    def test_get_ranking(self):
        comp = BenchmarkComparison(
            benchmark_name="MMLU",
            category=BenchmarkCategory.ACCURACY,
            unit=BenchmarkUnit.PERCENTAGE,
            entries=[
                {"subject": "A", "value": 90},
                {"subject": "B", "value": 80},
            ],
        )
        ranking = comp.get_ranking()
        assert ranking[0] == ("A", 90)
        assert ranking[1] == ("B", 80)

    def test_sorted_entries_handles_non_numeric(self):
        comp = BenchmarkComparison(
            benchmark_name="test",
            category=BenchmarkCategory.CUSTOM,
            unit=BenchmarkUnit.CUSTOM,
            entries=[
                {"subject": "A", "value": "N/A"},
                {"subject": "B", "value": "N/A"},
            ],
        )
        # Should not crash, returns original order
        sorted_e = comp.sorted_entries
        assert len(sorted_e) == 2

    def test_empty_entries(self):
        comp = BenchmarkComparison(
            benchmark_name="test",
            category=BenchmarkCategory.CUSTOM,
            unit=BenchmarkUnit.CUSTOM,
        )
        assert comp.sorted_entries == []
        assert comp.get_ranking() == []


# ---------------------------------------------------------------------------
# BenchmarkExtractionResult
# ---------------------------------------------------------------------------
class TestBenchmarkExtractionResult:
    def test_empty(self):
        result = BenchmarkExtractionResult()
        assert result.benchmarks == []
        assert result.comparisons == []
        assert result.sources_analyzed == 0

    def test_get_benchmarks_by_subject(self):
        result = BenchmarkExtractionResult(
            benchmarks=[
                _make_benchmark(subject="GPT-4"),
                _make_benchmark(subject="Claude-3"),
                _make_benchmark(subject="GPT-4 Turbo"),
            ]
        )
        gpt = result.get_benchmarks_by_subject("GPT-4")
        assert len(gpt) == 2  # "GPT-4" and "GPT-4 Turbo"

    def test_get_benchmarks_by_category(self):
        result = BenchmarkExtractionResult(
            benchmarks=[
                _make_benchmark(category=BenchmarkCategory.ACCURACY),
                _make_benchmark(category=BenchmarkCategory.LATENCY),
                _make_benchmark(category=BenchmarkCategory.ACCURACY),
            ]
        )
        accuracy = result.get_benchmarks_by_category(BenchmarkCategory.ACCURACY)
        assert len(accuracy) == 2

    def test_get_summary(self):
        result = BenchmarkExtractionResult(
            sources_analyzed=5,
            benchmarks_found=10,
            extraction_confidence=0.8,
            warnings=["Low confidence source"],
        )
        summary = result.get_summary()
        assert "Sources Analyzed: 5" in summary
        assert "Benchmarks Found: 10" in summary
        assert "Warnings: 1" in summary


# ---------------------------------------------------------------------------
# BenchmarkQuery
# ---------------------------------------------------------------------------
class TestBenchmarkQuery:
    def test_matches_by_subject(self):
        q = BenchmarkQuery(subject="GPT-4")
        assert q.matches(_make_benchmark(subject="GPT-4 Turbo")) is True
        assert q.matches(_make_benchmark(subject="Claude-3")) is False

    def test_matches_by_category(self):
        q = BenchmarkQuery(category=BenchmarkCategory.ACCURACY)
        assert q.matches(_make_benchmark(category=BenchmarkCategory.ACCURACY)) is True
        assert q.matches(_make_benchmark(category=BenchmarkCategory.LATENCY)) is False

    def test_matches_by_confidence(self):
        q = BenchmarkQuery(min_confidence=0.8)
        assert q.matches(_make_benchmark(confidence=0.9)) is True
        assert q.matches(_make_benchmark(confidence=0.5)) is False

    def test_matches_by_date_after(self):
        cutoff = datetime.now(UTC) - timedelta(days=30)
        q = BenchmarkQuery(date_after=cutoff)
        recent = _make_benchmark(report_date=datetime.now(UTC))
        old = _make_benchmark(report_date=datetime.now(UTC) - timedelta(days=60))
        assert q.matches(recent) is True
        assert q.matches(old) is False

    def test_matches_all_empty_query(self):
        q = BenchmarkQuery()
        assert q.matches(_make_benchmark()) is True

    def test_matches_no_report_date_passes_date_filter(self):
        q = BenchmarkQuery(date_after=datetime.now(UTC))
        b = _make_benchmark(report_date=None)
        assert q.matches(b) is True  # No date means filter doesn't apply
