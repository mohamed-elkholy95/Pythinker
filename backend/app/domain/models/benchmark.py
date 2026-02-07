"""Benchmark and metric extraction models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BenchmarkCategory(str, Enum):
    """Categories of benchmarks."""

    PERFORMANCE = "performance"
    ACCURACY = "accuracy"
    EFFICIENCY = "efficiency"
    COST = "cost"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    QUALITY = "quality"
    CUSTOM = "custom"


class BenchmarkUnit(str, Enum):
    """Common benchmark units."""

    PERCENTAGE = "percentage"
    MILLISECONDS = "ms"
    SECONDS = "s"
    TOKENS_PER_SEC = "tokens/s"
    REQUESTS_PER_SEC = "req/s"
    USD = "usd"
    USD_PER_MILLION = "usd/1m_tokens"
    COUNT = "count"
    RATIO = "ratio"
    BYTES = "bytes"
    KILOBYTES = "kb"
    MEGABYTES = "mb"
    GIGABYTES = "gb"
    CUSTOM = "custom"


class ExtractedBenchmark(BaseModel):
    """A benchmark extracted from research content."""

    name: str = Field(..., description="Benchmark name (e.g., 'MMLU Score')")
    value: float | str = Field(..., description="Benchmark value")
    unit: BenchmarkUnit = Field(default=BenchmarkUnit.CUSTOM)
    custom_unit: str | None = Field(default=None)
    category: BenchmarkCategory = Field(default=BenchmarkCategory.CUSTOM)

    # Source attribution
    source_url: str = Field(..., description="URL where benchmark was found")
    source_title: str | None = Field(default=None)
    extracted_text: str = Field(..., description="Original text containing the benchmark")

    # Context
    subject: str = Field(..., description="What is being benchmarked (e.g., 'GPT-4')")
    comparison_baseline: str | None = Field(default=None, description="Baseline for comparison")
    test_conditions: str | None = Field(default=None, description="Test conditions/methodology")

    # Metadata
    report_date: datetime | None = Field(default=None)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    is_verified: bool = Field(default=False)

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: float | str) -> float | str:
        """Ensure value is meaningful."""
        if isinstance(v, str) and not v.strip():
            raise ValueError("Benchmark value cannot be empty")
        return v

    def get_display_value(self) -> str:
        """Get a formatted display value with unit."""
        unit_str = self.custom_unit if self.unit == BenchmarkUnit.CUSTOM else self.unit.value
        if unit_str:
            return f"{self.value} {unit_str}"
        return str(self.value)


class BenchmarkComparison(BaseModel):
    """Comparison of benchmarks across subjects."""

    benchmark_name: str
    category: BenchmarkCategory
    unit: BenchmarkUnit

    entries: list[dict[str, Any]] = Field(
        default_factory=list, description="List of {subject, value, source_url} dicts"
    )

    winner: str | None = Field(default=None)
    analysis: str | None = Field(default=None)

    @property
    def sorted_entries(self) -> list[dict[str, Any]]:
        """Entries sorted by value (descending for most metrics)."""
        try:
            return sorted(self.entries, key=lambda x: float(x.get("value", 0)), reverse=True)
        except (ValueError, TypeError):
            return self.entries

    def get_ranking(self) -> list[tuple[str, Any]]:
        """Get ranked list of (subject, value) tuples."""
        sorted_items = self.sorted_entries
        return [(e.get("subject", "Unknown"), e.get("value")) for e in sorted_items]


class BenchmarkExtractionResult(BaseModel):
    """Result of benchmark extraction from research."""

    benchmarks: list[ExtractedBenchmark] = Field(default_factory=list)
    comparisons: list[BenchmarkComparison] = Field(default_factory=list)

    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sources_analyzed: int = Field(default=0)
    benchmarks_found: int = Field(default=0)

    warnings: list[str] = Field(default_factory=list)

    def get_benchmarks_by_subject(self, subject: str) -> list[ExtractedBenchmark]:
        """Get all benchmarks for a specific subject."""
        return [b for b in self.benchmarks if subject.lower() in b.subject.lower()]

    def get_benchmarks_by_category(self, category: BenchmarkCategory) -> list[ExtractedBenchmark]:
        """Get all benchmarks in a category."""
        return [b for b in self.benchmarks if b.category == category]

    def get_summary(self) -> str:
        """Get a human-readable summary of extraction results."""
        lines = [
            "Benchmark Extraction Results:",
            f"  Sources Analyzed: {self.sources_analyzed}",
            f"  Benchmarks Found: {self.benchmarks_found}",
            f"  Comparisons Built: {len(self.comparisons)}",
            f"  Confidence: {self.extraction_confidence:.1%}",
        ]

        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")

        return "\n".join(lines)


class BenchmarkQuery(BaseModel):
    """Query parameters for benchmark search."""

    subject: str | None = Field(default=None, description="Subject to filter by")
    category: BenchmarkCategory | None = Field(default=None)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    date_after: datetime | None = Field(default=None)
    date_before: datetime | None = Field(default=None)

    def matches(self, benchmark: ExtractedBenchmark) -> bool:
        """Check if a benchmark matches this query."""
        if self.subject and self.subject.lower() not in benchmark.subject.lower():
            return False

        if self.category and benchmark.category != self.category:
            return False

        if benchmark.confidence < self.min_confidence:
            return False

        if self.date_after and benchmark.report_date:
            if benchmark.report_date < self.date_after:
                return False

        if self.date_before and benchmark.report_date:
            if benchmark.report_date > self.date_before:
                return False

        return True
