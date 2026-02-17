"""Structured Report Models with discriminated unions for flexible output types."""

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class ReportType(str, Enum):
    """Types of generated reports."""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    TECHNICAL = "technical"


class ReportSection(BaseModel):
    """A section within a report."""

    heading: str = Field(..., min_length=3, description="Section heading")
    content: str = Field(..., min_length=10, description="Section content (markdown)")
    citations: list[str] = Field(default_factory=list, description="Citation IDs used in this section")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @field_validator("content")
    @classmethod
    def validate_content_not_placeholder(cls, v: str) -> str:
        """Ensure content is not placeholder text."""
        placeholders = ["todo", "tbd", "lorem ipsum", "[content]", "placeholder"]
        if any(p in v.lower() for p in placeholders):
            raise ValueError("Section content appears to be placeholder text")
        return v


class KeyFinding(BaseModel):
    """A key finding with source attribution."""

    finding: str = Field(..., description="The finding statement")
    supporting_evidence: list[str] = Field(..., min_length=1, description="Evidence supporting this finding")
    citation_ids: list[str] = Field(..., min_length=1, description="Citations backing this finding")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    is_inferred: bool = Field(default=False, description="Whether this is inferred vs directly stated")


class Benchmark(BaseModel):
    """A benchmark or metric extracted from research."""

    name: str = Field(..., description="Benchmark/metric name")
    value: str = Field(..., description="The value (can be numeric or descriptive)")
    unit: str | None = Field(default=None, description="Unit of measurement")
    source_url: str = Field(..., description="URL where benchmark was found")
    context: str = Field(..., description="Context for the benchmark")
    date_reported: datetime | None = Field(default=None, description="When benchmark was reported")
    methodology_notes: str | None = Field(default=None, description="Notes on measurement methodology")


class ComparisonItem(BaseModel):
    """An item being compared in a comparison report."""

    name: str
    attributes: dict[str, str | float | bool]
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)


# Discriminated union for different report types
class ResearchReport(BaseModel):
    """Research report with findings and citations."""

    report_type: Literal["research"] = "research"
    title: str = Field(..., min_length=5)
    executive_summary: str = Field(..., min_length=50)
    key_findings: list[KeyFinding] = Field(..., min_length=1)
    sections: list[ReportSection] = Field(..., min_length=1)
    benchmarks: list[Benchmark] = Field(default_factory=list)
    methodology: str | None = Field(default=None)
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ComparisonReport(BaseModel):
    """Comparison report for multiple items."""

    report_type: Literal["comparison"] = "comparison"
    title: str = Field(..., min_length=5)
    items: list[ComparisonItem] = Field(..., min_length=2)
    comparison_criteria: list[str] = Field(..., min_length=1)
    winner: str | None = Field(default=None)
    recommendation: str | None = Field(default=None)
    sections: list[ReportSection] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalysisReport(BaseModel):
    """Technical analysis report."""

    report_type: Literal["analysis"] = "analysis"
    title: str = Field(..., min_length=5)
    subject: str = Field(..., description="Subject of analysis")
    analysis_type: str = Field(..., description="Type: risk, security, performance, etc.")
    findings: list[KeyFinding] = Field(..., min_length=1)
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Union type with discriminator
Report = Annotated[ResearchReport | ComparisonReport | AnalysisReport, Field(discriminator="report_type")]


class ReportMetadata(BaseModel):
    """Metadata about report generation."""

    total_sources_consulted: int = Field(default=0)
    sources_used: int = Field(default=0)
    sources_filtered: int = Field(default=0)
    average_source_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    generation_time_seconds: float = Field(default=0.0)
    token_usage: int = Field(default=0)
    hallucination_checks_passed: int = Field(default=0)
    hallucination_checks_failed: int = Field(default=0)


class CitationEntry(BaseModel):
    """Bibliography entry for citations."""

    id: str = Field(..., description="Citation ID (e.g., [1], [source-a])")
    url: str
    title: str
    accessed_at: datetime
    source_type: Literal["web", "document", "api", "tool_result"]
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    excerpt: str | None = Field(default=None, description="Relevant excerpt")


class StructuredReportOutput(BaseModel):
    """Complete report output with metadata and citations."""

    report: Report
    metadata: ReportMetadata
    citation_bibliography: list[CitationEntry] = Field(default_factory=list)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
