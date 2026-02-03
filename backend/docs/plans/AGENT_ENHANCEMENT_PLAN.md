# Agent Enhancement Implementation Plan

## Overview

This plan enhances the Pythinker agent system with four key capabilities based on latest LangChain/LangGraph best practices:

1. **Structured Reporting** - Type-safe, validated report outputs
2. **Source Filtering** - Relevance scoring and quality filtering
3. **Benchmark Extraction** - Trajectory evaluation and quality metrics
4. **Citation Discipline** - Strict source attribution and verification

---

## Phase 1: Enhanced Structured Reporting

### 1.1 Report Output Models

**File:** `backend/app/domain/models/report.py`

```python
"""Structured Report Models with discriminated unions for flexible output types."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

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
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ComparisonReport(BaseModel):
    """Comparison report for multiple items."""

    report_type: Literal["comparison"] = "comparison"
    title: str = Field(..., min_length=5)
    items: list[ComparisonItem] = Field(..., min_length=2)
    comparison_criteria: list[str] = Field(..., min_length=1)
    winner: str | None = Field(default=None)
    recommendation: str | None = Field(default=None)
    sections: list[ReportSection] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


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
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# Union type with discriminator
Report = Annotated[
    Union[ResearchReport, ComparisonReport, AnalysisReport],
    Field(discriminator="report_type")
]


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


class StructuredReportOutput(BaseModel):
    """Complete report output with metadata and citations."""

    report: Report
    metadata: ReportMetadata
    citation_bibliography: list["CitationEntry"] = Field(default_factory=list)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class CitationEntry(BaseModel):
    """Bibliography entry for citations."""

    id: str = Field(..., description="Citation ID (e.g., [1], [source-a])")
    url: str
    title: str
    accessed_at: datetime
    source_type: Literal["web", "document", "api", "tool_result"]
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    excerpt: str | None = Field(default=None, description="Relevant excerpt")


# Update forward reference
StructuredReportOutput.model_rebuild()
```

### 1.2 Report Generator Service

**File:** `backend/app/domain/services/report_generator.py`

```python
"""Report generation service with structured output validation."""

from datetime import datetime
import json
import logging
from typing import Any

from pydantic import ValidationError

from app.domain.external.llm import LLM
from app.domain.models.report import (
    Report,
    ReportMetadata,
    StructuredReportOutput,
    CitationEntry,
)
from app.domain.models.source_attribution import AttributionSummary

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates structured reports with validation and retry."""

    MAX_RETRIES = 3

    def __init__(self, llm: LLM):
        self.llm = llm

    async def generate(
        self,
        research_data: dict[str, Any],
        report_type: str,
        citations: list[CitationEntry],
        attribution_summary: AttributionSummary,
    ) -> StructuredReportOutput:
        """Generate a validated structured report.

        Args:
            research_data: Compiled research data
            report_type: Type of report to generate
            citations: Available citations
            attribution_summary: Source attribution summary

        Returns:
            Validated StructuredReportOutput
        """
        start_time = datetime.utcnow()

        # Build prompt with schema
        prompt = self._build_prompt(research_data, report_type, citations)

        # Attempt generation with retries
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.llm.generate(
                    prompt,
                    response_format={"type": "json_object"},
                )

                # Parse and validate
                report = self._parse_report(response.content, report_type)

                # Build metadata
                metadata = ReportMetadata(
                    total_sources_consulted=attribution_summary.total_claims,
                    sources_used=attribution_summary.verified_claims,
                    sources_filtered=attribution_summary.unavailable_claims,
                    average_source_quality=attribution_summary.average_confidence,
                    generation_time_seconds=(datetime.utcnow() - start_time).total_seconds(),
                    token_usage=response.usage.total_tokens if response.usage else 0,
                )

                # Calculate quality score
                quality_score = self._calculate_quality_score(report, citations)

                return StructuredReportOutput(
                    report=report,
                    metadata=metadata,
                    citation_bibliography=citations,
                    quality_score=quality_score,
                    warnings=self._generate_warnings(report, attribution_summary),
                )

            except ValidationError as e:
                last_error = e
                logger.warning(f"Report validation failed (attempt {attempt + 1}): {e}")
                prompt = self._build_retry_prompt(prompt, str(e))

        raise ValueError(f"Failed to generate valid report after {self.MAX_RETRIES} attempts: {last_error}")

    def _parse_report(self, content: str, report_type: str) -> Report:
        """Parse and validate report content."""
        data = json.loads(content)
        data["report_type"] = report_type

        # Use discriminated union parsing
        from app.domain.models.report import ResearchReport, ComparisonReport, AnalysisReport

        type_map = {
            "research": ResearchReport,
            "comparison": ComparisonReport,
            "analysis": AnalysisReport,
        }

        model_class = type_map.get(report_type)
        if not model_class:
            raise ValueError(f"Unknown report type: {report_type}")

        return model_class.model_validate(data)

    def _calculate_quality_score(self, report: Report, citations: list[CitationEntry]) -> float:
        """Calculate overall report quality score."""
        scores = []

        # Citation coverage
        if hasattr(report, "key_findings"):
            cited_findings = sum(1 for f in report.key_findings if f.citation_ids)
            scores.append(cited_findings / len(report.key_findings) if report.key_findings else 0)

        # Section completeness
        if hasattr(report, "sections"):
            scores.append(min(len(report.sections) / 3, 1.0))  # Target 3+ sections

        # Source reliability
        if citations:
            avg_reliability = sum(c.reliability_score for c in citations) / len(citations)
            scores.append(avg_reliability)

        return sum(scores) / len(scores) if scores else 0.5

    def _generate_warnings(self, report: Report, attribution: AttributionSummary) -> list[str]:
        """Generate warnings about report quality."""
        warnings = []

        if attribution.has_paywall_sources:
            warnings.append("Some sources were behind paywalls - information may be incomplete")

        if attribution.inferred_claims > attribution.verified_claims:
            warnings.append("Report contains more inferred than verified claims")

        if attribution.average_confidence < 0.6:
            warnings.append("Overall source confidence is low - verify key claims independently")

        return warnings

    def _build_prompt(self, data: dict, report_type: str, citations: list[CitationEntry]) -> str:
        """Build generation prompt with schema."""
        # Implementation details...
        pass

    def _build_retry_prompt(self, original: str, error: str) -> str:
        """Build retry prompt with validation feedback."""
        return f"""{original}

VALIDATION ERROR - Please fix:
{error}

Ensure your response is valid JSON matching the required schema."""
```

---

## Phase 2: Source Filtering System

### 2.1 Source Quality Models

**File:** `backend/app/domain/models/source_quality.py`

```python
"""Source quality assessment and filtering models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SourceReliability(str, Enum):
    """Source reliability tiers."""

    HIGH = "high"           # Academic, official docs, reputable news
    MEDIUM = "medium"       # Known tech blogs, established platforms
    LOW = "low"             # Forums, social media, unknown sources
    UNKNOWN = "unknown"     # Cannot determine


class ContentFreshness(str, Enum):
    """Content freshness categories."""

    CURRENT = "current"     # < 6 months
    RECENT = "recent"       # 6-18 months
    DATED = "dated"         # 18-36 months
    STALE = "stale"         # > 36 months
    UNKNOWN = "unknown"


class SourceQualityScore(BaseModel):
    """Comprehensive source quality assessment."""

    url: str
    domain: str

    # Scoring components (0.0 to 1.0)
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness_score: float = Field(default=0.5, ge=0.0, le=1.0)
    content_depth_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # Metadata
    reliability_tier: SourceReliability = SourceReliability.UNKNOWN
    freshness_category: ContentFreshness = ContentFreshness.UNKNOWN
    publication_date: datetime | None = None
    author_authority: float | None = None

    # Flags
    is_primary_source: bool = False
    has_citations: bool = False
    is_paywalled: bool = False
    requires_login: bool = False

    # Computed
    @property
    def composite_score(self) -> float:
        """Weighted composite quality score."""
        weights = {
            "reliability": 0.35,
            "relevance": 0.30,
            "freshness": 0.20,
            "depth": 0.15,
        }
        return (
            self.reliability_score * weights["reliability"]
            + self.relevance_score * weights["relevance"]
            + self.freshness_score * weights["freshness"]
            + self.content_depth_score * weights["depth"]
        )

    @property
    def passes_threshold(self) -> bool:
        """Check if source passes minimum quality threshold."""
        return self.composite_score >= 0.4 and not self.is_paywalled


class SourceFilterConfig(BaseModel):
    """Configuration for source filtering."""

    min_composite_score: float = Field(default=0.4, ge=0.0, le=1.0)
    min_reliability_score: float = Field(default=0.3, ge=0.0, le=1.0)
    min_relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    max_age_days: int | None = Field(default=365 * 2)  # 2 years default

    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)

    require_https: bool = True
    allow_paywalled: bool = False
    prefer_primary_sources: bool = True

    # Domain tier overrides
    high_reliability_domains: list[str] = Field(
        default_factory=lambda: [
            "arxiv.org", "github.com", "docs.python.org",
            "pytorch.org", "tensorflow.org", "huggingface.co",
            "openai.com", "anthropic.com", "nature.com",
            "acm.org", "ieee.org", "research.google",
        ]
    )
    medium_reliability_domains: list[str] = Field(
        default_factory=lambda: [
            "medium.com", "dev.to", "stackoverflow.com",
            "towardsdatascience.com", "analyticsvidhya.com",
        ]
    )


class FilteredSourceResult(BaseModel):
    """Result of source filtering operation."""

    accepted_sources: list[SourceQualityScore] = Field(default_factory=list)
    rejected_sources: list[SourceQualityScore] = Field(default_factory=list)
    rejection_reasons: dict[str, str] = Field(default_factory=dict)

    @property
    def acceptance_rate(self) -> float:
        """Percentage of sources accepted."""
        total = len(self.accepted_sources) + len(self.rejected_sources)
        return len(self.accepted_sources) / total if total > 0 else 0.0
```

### 2.2 Source Filter Service

**File:** `backend/app/domain/services/source_filter.py`

```python
"""Source filtering and quality assessment service."""

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from app.domain.models.source_quality import (
    ContentFreshness,
    FilteredSourceResult,
    SourceFilterConfig,
    SourceQualityScore,
    SourceReliability,
)

logger = logging.getLogger(__name__)


class SourceFilterService:
    """Filters and scores sources based on quality criteria."""

    def __init__(self, config: SourceFilterConfig | None = None):
        self.config = config or SourceFilterConfig()

    def filter_sources(
        self,
        sources: list[dict],
        query: str,
    ) -> FilteredSourceResult:
        """Filter sources based on quality criteria.

        Args:
            sources: Raw source data (url, content, metadata)
            query: Original search query for relevance scoring

        Returns:
            FilteredSourceResult with accepted/rejected sources
        """
        result = FilteredSourceResult()

        for source in sources:
            score = self.assess_quality(source, query)

            rejection_reason = self._check_rejection(score)
            if rejection_reason:
                result.rejected_sources.append(score)
                result.rejection_reasons[score.url] = rejection_reason
            else:
                result.accepted_sources.append(score)

        # Sort accepted by composite score
        result.accepted_sources.sort(key=lambda s: s.composite_score, reverse=True)

        logger.info(
            f"Source filtering: {len(result.accepted_sources)} accepted, "
            f"{len(result.rejected_sources)} rejected"
        )

        return result

    def assess_quality(self, source: dict, query: str) -> SourceQualityScore:
        """Assess quality of a single source."""
        url = source.get("url", "")
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        # Determine reliability tier
        reliability_tier = self._assess_reliability_tier(domain)
        reliability_score = self._tier_to_score(reliability_tier)

        # Assess freshness
        pub_date = self._extract_publication_date(source)
        freshness_cat, freshness_score = self._assess_freshness(pub_date)

        # Assess relevance to query
        relevance_score = self._assess_relevance(source, query)

        # Assess content depth
        depth_score = self._assess_content_depth(source)

        return SourceQualityScore(
            url=url,
            domain=domain,
            reliability_score=reliability_score,
            relevance_score=relevance_score,
            freshness_score=freshness_score,
            content_depth_score=depth_score,
            reliability_tier=reliability_tier,
            freshness_category=freshness_cat,
            publication_date=pub_date,
            is_primary_source=self._is_primary_source(source, domain),
            has_citations=self._has_citations(source),
            is_paywalled=source.get("is_paywalled", False),
            requires_login=source.get("requires_login", False),
        )

    def _assess_reliability_tier(self, domain: str) -> SourceReliability:
        """Determine source reliability tier from domain."""
        if any(d in domain for d in self.config.high_reliability_domains):
            return SourceReliability.HIGH
        if any(d in domain for d in self.config.medium_reliability_domains):
            return SourceReliability.MEDIUM
        if any(d in domain for d in self.config.blocked_domains):
            return SourceReliability.LOW
        return SourceReliability.UNKNOWN

    def _tier_to_score(self, tier: SourceReliability) -> float:
        """Convert reliability tier to numeric score."""
        return {
            SourceReliability.HIGH: 0.9,
            SourceReliability.MEDIUM: 0.65,
            SourceReliability.LOW: 0.3,
            SourceReliability.UNKNOWN: 0.5,
        }[tier]

    def _assess_freshness(self, pub_date: datetime | None) -> tuple[ContentFreshness, float]:
        """Assess content freshness from publication date."""
        if not pub_date:
            return ContentFreshness.UNKNOWN, 0.5

        age = datetime.utcnow() - pub_date

        if age < timedelta(days=180):
            return ContentFreshness.CURRENT, 1.0
        elif age < timedelta(days=540):
            return ContentFreshness.RECENT, 0.75
        elif age < timedelta(days=1080):
            return ContentFreshness.DATED, 0.5
        else:
            return ContentFreshness.STALE, 0.25

    def _assess_relevance(self, source: dict, query: str) -> float:
        """Assess relevance of source to query using keyword matching."""
        content = source.get("content", "") + " " + source.get("title", "")
        content_lower = content.lower()

        # Extract query terms
        query_terms = set(re.findall(r'\w+', query.lower()))

        if not query_terms:
            return 0.5

        # Count matching terms
        matches = sum(1 for term in query_terms if term in content_lower)
        base_score = matches / len(query_terms)

        # Boost for exact phrase match
        if query.lower() in content_lower:
            base_score = min(base_score + 0.2, 1.0)

        return base_score

    def _assess_content_depth(self, source: dict) -> float:
        """Assess depth/comprehensiveness of content."""
        content = source.get("content", "")

        # Simple heuristics
        word_count = len(content.split())

        if word_count > 2000:
            return 0.9
        elif word_count > 1000:
            return 0.7
        elif word_count > 500:
            return 0.5
        elif word_count > 200:
            return 0.3
        else:
            return 0.1

    def _check_rejection(self, score: SourceQualityScore) -> str | None:
        """Check if source should be rejected."""
        if score.composite_score < self.config.min_composite_score:
            return f"Composite score {score.composite_score:.2f} below threshold {self.config.min_composite_score}"

        if score.reliability_score < self.config.min_reliability_score:
            return f"Reliability score {score.reliability_score:.2f} below threshold"

        if score.relevance_score < self.config.min_relevance_score:
            return f"Relevance score {score.relevance_score:.2f} below threshold"

        if score.is_paywalled and not self.config.allow_paywalled:
            return "Source is paywalled"

        if self.config.blocked_domains:
            if any(d in score.domain for d in self.config.blocked_domains):
                return f"Domain {score.domain} is blocked"

        return None

    def _extract_publication_date(self, source: dict) -> datetime | None:
        """Extract publication date from source metadata."""
        # Try various date fields
        for field in ["published_date", "date", "publish_date", "created_at"]:
            if field in source and source[field]:
                try:
                    if isinstance(source[field], datetime):
                        return source[field]
                    return datetime.fromisoformat(source[field].replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
        return None

    def _is_primary_source(self, source: dict, domain: str) -> bool:
        """Determine if source is a primary source."""
        primary_indicators = ["official", "documentation", "docs", "api", "reference"]
        title = source.get("title", "").lower()
        return any(ind in title or ind in domain for ind in primary_indicators)

    def _has_citations(self, source: dict) -> bool:
        """Check if source has its own citations/references."""
        content = source.get("content", "")
        citation_patterns = [r'\[\d+\]', r'et al\.', r'References', r'Bibliography']
        return any(re.search(p, content) for p in citation_patterns)
```

---

## Phase 3: Benchmark Extraction

### 3.1 Benchmark Models

**File:** `backend/app/domain/models/benchmark.py`

```python
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
    def validate_value(cls, v):
        """Ensure value is meaningful."""
        if isinstance(v, str) and not v.strip():
            raise ValueError("Benchmark value cannot be empty")
        return v


class BenchmarkComparison(BaseModel):
    """Comparison of benchmarks across subjects."""

    benchmark_name: str
    category: BenchmarkCategory
    unit: BenchmarkUnit

    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {subject, value, source_url} dicts"
    )

    winner: str | None = Field(default=None)
    analysis: str | None = Field(default=None)

    @property
    def sorted_entries(self) -> list[dict]:
        """Entries sorted by value (descending for most metrics)."""
        try:
            return sorted(
                self.entries,
                key=lambda x: float(x.get("value", 0)),
                reverse=True
            )
        except (ValueError, TypeError):
            return self.entries


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
```

### 3.2 Benchmark Extractor Service

**File:** `backend/app/domain/services/benchmark_extractor.py`

```python
"""Benchmark extraction service using LLM."""

import json
import logging
import re
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.benchmark import (
    BenchmarkCategory,
    BenchmarkComparison,
    BenchmarkExtractionResult,
    BenchmarkUnit,
    ExtractedBenchmark,
)

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """Extract all benchmarks, metrics, and quantitative data from the following content.

For each benchmark found, provide:
1. name: The benchmark name (e.g., "MMLU Score", "Latency", "Accuracy")
2. value: The numeric or descriptive value
3. unit: The unit of measurement
4. category: One of [performance, accuracy, efficiency, cost, latency, throughput, quality, custom]
5. subject: What is being measured (e.g., "GPT-4", "Claude 3", "System X")
6. extracted_text: The exact text where you found this benchmark
7. comparison_baseline: If compared to something, what is the baseline
8. test_conditions: Any mentioned test conditions or methodology

Content to analyze:
---
{content}
---

Source URL: {url}

Respond with a JSON object:
{{
  "benchmarks": [
    {{
      "name": "...",
      "value": "...",
      "unit": "...",
      "category": "...",
      "subject": "...",
      "extracted_text": "...",
      "comparison_baseline": "...",
      "test_conditions": "...",
      "confidence": 0.0-1.0
    }}
  ],
  "extraction_notes": "Any notes about the extraction"
}}"""


class BenchmarkExtractor:
    """Extracts benchmarks from research content."""

    def __init__(self, llm: LLM):
        self.llm = llm

        # Common benchmark patterns for rule-based extraction
        self.patterns = [
            # Percentage patterns: "achieves 95.2% accuracy"
            (r'(\w+(?:\s+\w+)?)\s+(?:achieves?|scores?|reaches?|attains?)\s+([\d.]+)%',
             BenchmarkUnit.PERCENTAGE),
            # Latency patterns: "latency of 50ms"
            (r'latency\s+(?:of\s+)?([\d.]+)\s*(ms|milliseconds?|s|seconds?)',
             None),
            # Token throughput: "1000 tokens/second"
            (r'([\d,]+)\s*tokens?[/\s]+(second|s|sec)',
             BenchmarkUnit.TOKENS_PER_SEC),
            # Cost patterns: "$0.01 per 1M tokens"
            (r'\$?([\d.]+)\s*(?:per|/)\s*(?:1?M|million)?\s*tokens?',
             BenchmarkUnit.USD_PER_MILLION),
        ]

    async def extract(
        self,
        sources: list[dict[str, Any]],
    ) -> BenchmarkExtractionResult:
        """Extract benchmarks from multiple sources.

        Args:
            sources: List of {url, content, title} dicts

        Returns:
            BenchmarkExtractionResult with all found benchmarks
        """
        all_benchmarks: list[ExtractedBenchmark] = []
        warnings: list[str] = []

        for source in sources:
            try:
                # Try LLM extraction first
                llm_benchmarks = await self._extract_with_llm(source)
                all_benchmarks.extend(llm_benchmarks)

                # Supplement with rule-based extraction
                rule_benchmarks = self._extract_with_rules(source)

                # Add rule-based benchmarks not already found by LLM
                existing_values = {(b.name.lower(), str(b.value)) for b in llm_benchmarks}
                for rb in rule_benchmarks:
                    if (rb.name.lower(), str(rb.value)) not in existing_values:
                        all_benchmarks.append(rb)

            except Exception as e:
                logger.warning(f"Benchmark extraction failed for {source.get('url')}: {e}")
                warnings.append(f"Failed to extract from {source.get('url')}: {str(e)[:100]}")

        # Build comparisons
        comparisons = self._build_comparisons(all_benchmarks)

        # Calculate overall confidence
        confidence = (
            sum(b.confidence for b in all_benchmarks) / len(all_benchmarks)
            if all_benchmarks else 0.0
        )

        return BenchmarkExtractionResult(
            benchmarks=all_benchmarks,
            comparisons=comparisons,
            extraction_confidence=confidence,
            sources_analyzed=len(sources),
            benchmarks_found=len(all_benchmarks),
            warnings=warnings,
        )

    async def _extract_with_llm(self, source: dict) -> list[ExtractedBenchmark]:
        """Extract benchmarks using LLM."""
        content = source.get("content", "")[:8000]  # Limit content length
        url = source.get("url", "")

        prompt = EXTRACTION_PROMPT.format(content=content, url=url)

        response = await self.llm.generate(
            prompt,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response.content)
            benchmarks = []

            for b in data.get("benchmarks", []):
                try:
                    # Map unit string to enum
                    unit = self._map_unit(b.get("unit", "custom"))
                    category = self._map_category(b.get("category", "custom"))

                    benchmarks.append(ExtractedBenchmark(
                        name=b["name"],
                        value=b["value"],
                        unit=unit,
                        category=category,
                        source_url=url,
                        source_title=source.get("title"),
                        extracted_text=b.get("extracted_text", ""),
                        subject=b.get("subject", "Unknown"),
                        comparison_baseline=b.get("comparison_baseline"),
                        test_conditions=b.get("test_conditions"),
                        confidence=float(b.get("confidence", 0.7)),
                    ))
                except Exception as e:
                    logger.debug(f"Failed to parse benchmark: {e}")
                    continue

            return benchmarks

        except json.JSONDecodeError:
            logger.warning("LLM response was not valid JSON")
            return []

    def _extract_with_rules(self, source: dict) -> list[ExtractedBenchmark]:
        """Extract benchmarks using regex patterns."""
        content = source.get("content", "")
        url = source.get("url", "")
        benchmarks = []

        for pattern, default_unit in self.patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                try:
                    groups = match.groups()
                    name = groups[0] if len(groups) > 1 else "Metric"
                    value = groups[-1] if len(groups) > 0 else groups[0]

                    # Get surrounding context
                    start = max(0, match.start() - 100)
                    end = min(len(content), match.end() + 100)
                    context = content[start:end]

                    benchmarks.append(ExtractedBenchmark(
                        name=name,
                        value=value,
                        unit=default_unit or BenchmarkUnit.CUSTOM,
                        category=BenchmarkCategory.CUSTOM,
                        source_url=url,
                        extracted_text=context,
                        subject="Unknown",
                        confidence=0.5,  # Lower confidence for rule-based
                    ))
                except Exception:
                    continue

        return benchmarks

    def _build_comparisons(self, benchmarks: list[ExtractedBenchmark]) -> list[BenchmarkComparison]:
        """Build comparison tables from benchmarks with same name."""
        # Group by benchmark name
        by_name: dict[str, list[ExtractedBenchmark]] = {}
        for b in benchmarks:
            key = b.name.lower().strip()
            if key not in by_name:
                by_name[key] = []
            by_name[key].append(b)

        comparisons = []
        for name, group in by_name.items():
            if len(group) >= 2:  # Only create comparison if 2+ entries
                entries = [
                    {
                        "subject": b.subject,
                        "value": b.value,
                        "source_url": b.source_url,
                    }
                    for b in group
                ]

                # Determine winner if numeric
                winner = None
                try:
                    sorted_entries = sorted(
                        entries,
                        key=lambda x: float(x["value"]),
                        reverse=True
                    )
                    winner = sorted_entries[0]["subject"]
                except (ValueError, TypeError):
                    pass

                comparisons.append(BenchmarkComparison(
                    benchmark_name=group[0].name,
                    category=group[0].category,
                    unit=group[0].unit,
                    entries=entries,
                    winner=winner,
                ))

        return comparisons

    def _map_unit(self, unit_str: str) -> BenchmarkUnit:
        """Map unit string to enum."""
        unit_map = {
            "percentage": BenchmarkUnit.PERCENTAGE,
            "%": BenchmarkUnit.PERCENTAGE,
            "ms": BenchmarkUnit.MILLISECONDS,
            "milliseconds": BenchmarkUnit.MILLISECONDS,
            "s": BenchmarkUnit.SECONDS,
            "seconds": BenchmarkUnit.SECONDS,
            "tokens/s": BenchmarkUnit.TOKENS_PER_SEC,
            "req/s": BenchmarkUnit.REQUESTS_PER_SEC,
            "usd": BenchmarkUnit.USD,
            "$": BenchmarkUnit.USD,
        }
        return unit_map.get(unit_str.lower(), BenchmarkUnit.CUSTOM)

    def _map_category(self, cat_str: str) -> BenchmarkCategory:
        """Map category string to enum."""
        try:
            return BenchmarkCategory(cat_str.lower())
        except ValueError:
            return BenchmarkCategory.CUSTOM
```

---

## Phase 4: Citation Discipline System

### 4.1 Enhanced Citation Models

**File:** `backend/app/domain/models/citation_discipline.py`

```python
"""Enhanced citation models for strict source discipline."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class CitationRequirement(str, Enum):
    """How strictly citations are required."""

    STRICT = "strict"       # Every factual claim must be cited
    MODERATE = "moderate"   # Major claims must be cited
    RELAXED = "relaxed"     # Citations encouraged but not required


class ClaimType(str, Enum):
    """Type of claim being made."""

    FACTUAL = "factual"           # Verifiable fact
    STATISTICAL = "statistical"   # Numeric/statistical claim
    QUOTATION = "quotation"       # Direct quote
    INFERENCE = "inference"       # Derived conclusion
    OPINION = "opinion"           # Subjective statement
    COMMON_KNOWLEDGE = "common"   # Generally known facts


class CitedClaim(BaseModel):
    """A claim with mandatory citation tracking."""

    claim_text: str = Field(..., description="The claim being made")
    claim_type: ClaimType = Field(...)

    # Citation requirements based on claim type
    citation_ids: list[str] = Field(default_factory=list)
    supporting_excerpts: list[str] = Field(default_factory=list)

    # Verification status
    is_verified: bool = Field(default=False)
    verification_method: str | None = Field(default=None)

    # Confidence and caveats
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_caveat: bool = Field(default=False)
    caveat_text: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_citation_requirements(self) -> "CitedClaim":
        """Ensure citations match claim type requirements."""
        # Factual and statistical claims MUST have citations
        if self.claim_type in (ClaimType.FACTUAL, ClaimType.STATISTICAL, ClaimType.QUOTATION):
            if not self.citation_ids:
                self.requires_caveat = True
                self.caveat_text = f"[Unverified {self.claim_type.value} claim]"
                self.confidence = min(self.confidence, 0.3)

        # Inferences should note they are inferred
        if self.claim_type == ClaimType.INFERENCE and not self.caveat_text:
            self.caveat_text = "[Inferred from available data]"

        return self


class CitationValidationResult(BaseModel):
    """Result of citation validation for content."""

    is_valid: bool = Field(default=False)
    total_claims: int = Field(default=0)
    cited_claims: int = Field(default=0)
    uncited_factual_claims: int = Field(default=0)

    # Detailed breakdown
    claims: list[CitedClaim] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    weak_citations: list[str] = Field(default_factory=list)

    # Scores
    citation_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_quality: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def overall_score(self) -> float:
        """Overall citation discipline score."""
        return (self.citation_coverage * 0.6 + self.citation_quality * 0.4)

    def get_report(self) -> str:
        """Generate human-readable validation report."""
        lines = [
            f"Citation Validation Report",
            f"=" * 40,
            f"Total Claims: {self.total_claims}",
            f"Cited Claims: {self.cited_claims}",
            f"Uncited Factual Claims: {self.uncited_factual_claims}",
            f"",
            f"Citation Coverage: {self.citation_coverage:.1%}",
            f"Citation Quality: {self.citation_quality:.1%}",
            f"Overall Score: {self.overall_score:.1%}",
        ]

        if self.missing_citations:
            lines.extend([
                f"",
                f"Missing Citations:",
                *[f"  - {c}" for c in self.missing_citations[:5]],
            ])

        if self.weak_citations:
            lines.extend([
                f"",
                f"Weak Citations (low confidence sources):",
                *[f"  - {c}" for c in self.weak_citations[:5]],
            ])

        return "\n".join(lines)


class CitationConfig(BaseModel):
    """Configuration for citation requirements."""

    requirement_level: CitationRequirement = CitationRequirement.MODERATE
    min_coverage_score: float = Field(default=0.7, ge=0.0, le=1.0)
    min_quality_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # What requires citations
    require_citations_for: list[ClaimType] = Field(
        default_factory=lambda: [
            ClaimType.FACTUAL,
            ClaimType.STATISTICAL,
            ClaimType.QUOTATION,
        ]
    )

    # Source quality requirements
    min_source_reliability: float = Field(default=0.4, ge=0.0, le=1.0)
    prefer_primary_sources: bool = True
    max_age_days: int | None = Field(default=730)  # 2 years
```

### 4.2 Citation Validator Service

**File:** `backend/app/domain/services/citation_validator.py`

```python
"""Citation validation and enforcement service."""

import json
import logging
import re
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.citation_discipline import (
    CitationConfig,
    CitationValidationResult,
    CitedClaim,
    ClaimType,
)
from app.domain.models.source_quality import SourceQualityScore

logger = logging.getLogger(__name__)


CLAIM_EXTRACTION_PROMPT = """Analyze the following content and extract all claims that require citations.

For each claim, identify:
1. claim_text: The exact claim being made
2. claim_type: One of [factual, statistical, quotation, inference, opinion, common]
3. needs_citation: Whether this claim requires a source citation
4. existing_citation: Any citation ID already present (e.g., [1], [source-a])

Content to analyze:
---
{content}
---

Available citations:
{citations}

Respond with JSON:
{{
  "claims": [
    {{
      "claim_text": "...",
      "claim_type": "...",
      "needs_citation": true/false,
      "existing_citation": "..." or null,
      "confidence": 0.0-1.0
    }}
  ]
}}"""


class CitationValidator:
    """Validates and enforces citation discipline in content."""

    def __init__(self, llm: LLM, config: CitationConfig | None = None):
        self.llm = llm
        self.config = config or CitationConfig()

    async def validate(
        self,
        content: str,
        available_citations: dict[str, dict[str, Any]],
        source_scores: dict[str, SourceQualityScore] | None = None,
    ) -> CitationValidationResult:
        """Validate citation discipline in content.

        Args:
            content: The content to validate
            available_citations: Dict of citation_id -> {url, title, excerpt}
            source_scores: Optional quality scores for sources

        Returns:
            CitationValidationResult with detailed analysis
        """
        # Extract claims using LLM
        claims = await self._extract_claims(content, available_citations)

        # Validate each claim
        validated_claims: list[CitedClaim] = []
        missing_citations: list[str] = []
        weak_citations: list[str] = []

        for claim_data in claims:
            claim = self._validate_claim(claim_data, available_citations, source_scores)
            validated_claims.append(claim)

            # Track issues
            if claim.claim_type in self.config.require_citations_for:
                if not claim.citation_ids:
                    missing_citations.append(claim.claim_text[:100])
                elif source_scores:
                    # Check citation quality
                    for cid in claim.citation_ids:
                        if cid in available_citations:
                            url = available_citations[cid].get("url", "")
                            if url in source_scores:
                                if source_scores[url].reliability_score < self.config.min_source_reliability:
                                    weak_citations.append(f"{claim.claim_text[:50]}... (source: {url})")

        # Calculate scores
        total = len(validated_claims)
        cited = sum(1 for c in validated_claims if c.citation_ids)
        uncited_factual = sum(
            1 for c in validated_claims
            if c.claim_type in self.config.require_citations_for and not c.citation_ids
        )

        coverage = cited / total if total > 0 else 0.0

        # Quality based on source reliability
        quality_scores = []
        for claim in validated_claims:
            if claim.citation_ids and source_scores:
                for cid in claim.citation_ids:
                    if cid in available_citations:
                        url = available_citations[cid].get("url", "")
                        if url in source_scores:
                            quality_scores.append(source_scores[url].reliability_score)

        quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.5

        is_valid = (
            coverage >= self.config.min_coverage_score
            and quality >= self.config.min_quality_score
            and uncited_factual == 0
        )

        return CitationValidationResult(
            is_valid=is_valid,
            total_claims=total,
            cited_claims=cited,
            uncited_factual_claims=uncited_factual,
            claims=validated_claims,
            missing_citations=missing_citations,
            weak_citations=weak_citations,
            citation_coverage=coverage,
            citation_quality=quality,
        )

    async def _extract_claims(
        self,
        content: str,
        citations: dict[str, dict],
    ) -> list[dict]:
        """Extract claims from content using LLM."""
        # Format citations for prompt
        citation_str = "\n".join(
            f"[{cid}]: {c.get('title', 'Unknown')} - {c.get('url', 'No URL')}"
            for cid, c in citations.items()
        )

        prompt = CLAIM_EXTRACTION_PROMPT.format(
            content=content[:6000],
            citations=citation_str or "No citations available",
        )

        response = await self.llm.generate(
            prompt,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response.content)
            return data.get("claims", [])
        except json.JSONDecodeError:
            logger.warning("Failed to parse claim extraction response")
            # Fallback to basic extraction
            return self._extract_claims_basic(content)

    def _extract_claims_basic(self, content: str) -> list[dict]:
        """Basic claim extraction using heuristics."""
        claims = []

        # Split into sentences
        sentences = re.split(r'[.!?]+', content)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue

            # Determine claim type based on patterns
            claim_type = ClaimType.FACTUAL.value

            if re.search(r'\d+%|\d+\.\d+|million|billion', sentence):
                claim_type = ClaimType.STATISTICAL.value
            elif re.search(r'["\'](.*?)["\']', sentence):
                claim_type = ClaimType.QUOTATION.value
            elif re.search(r'\bI think\b|\bbelieve\b|\bopinion\b', sentence, re.I):
                claim_type = ClaimType.OPINION.value
            elif re.search(r'\btherefore\b|\bthus\b|\bimplies\b', sentence, re.I):
                claim_type = ClaimType.INFERENCE.value

            # Check for existing citations
            citation_match = re.search(r'\[(\d+|[\w-]+)\]', sentence)

            claims.append({
                "claim_text": sentence,
                "claim_type": claim_type,
                "needs_citation": claim_type in ["factual", "statistical", "quotation"],
                "existing_citation": citation_match.group(1) if citation_match else None,
                "confidence": 0.5,
            })

        return claims

    def _validate_claim(
        self,
        claim_data: dict,
        citations: dict[str, dict],
        source_scores: dict[str, SourceQualityScore] | None,
    ) -> CitedClaim:
        """Validate a single claim."""
        claim_type = ClaimType(claim_data.get("claim_type", "factual"))

        # Find citation IDs
        citation_ids = []
        if claim_data.get("existing_citation"):
            citation_ids.append(claim_data["existing_citation"])

        # Also extract any inline citations
        inline_citations = re.findall(r'\[(\d+|[\w-]+)\]', claim_data.get("claim_text", ""))
        citation_ids.extend(inline_citations)
        citation_ids = list(set(citation_ids))  # Dedupe

        # Get supporting excerpts
        excerpts = []
        for cid in citation_ids:
            if cid in citations and citations[cid].get("excerpt"):
                excerpts.append(citations[cid]["excerpt"])

        # Determine verification status
        is_verified = bool(citation_ids) and claim_type != ClaimType.INFERENCE

        return CitedClaim(
            claim_text=claim_data.get("claim_text", ""),
            claim_type=claim_type,
            citation_ids=citation_ids,
            supporting_excerpts=excerpts,
            is_verified=is_verified,
            confidence=float(claim_data.get("confidence", 0.5)),
        )

    def enforce_citations(
        self,
        content: str,
        validation_result: CitationValidationResult,
    ) -> str:
        """Add caveats to content for uncited claims.

        Args:
            content: Original content
            validation_result: Validation result with claims

        Returns:
            Content with caveats added for uncited claims
        """
        modified = content

        for claim in validation_result.claims:
            if claim.requires_caveat and claim.caveat_text:
                # Insert caveat after the claim
                if claim.claim_text in modified:
                    modified = modified.replace(
                        claim.claim_text,
                        f"{claim.claim_text} {claim.caveat_text}",
                        1  # Only replace first occurrence
                    )

        return modified
```

---

## Phase 5: Integration

### 5.1 Enhanced Research Flow

**File:** `backend/app/domain/services/flows/enhanced_research.py`

```python
"""Enhanced research flow integrating all four improvements."""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator

from app.domain.external.llm import LLM
from app.domain.external.search import SearchEngine
from app.domain.models.benchmark import BenchmarkExtractionResult
from app.domain.models.citation_discipline import CitationConfig, CitationValidationResult
from app.domain.models.event import BaseEvent
from app.domain.models.report import StructuredReportOutput
from app.domain.models.source_quality import FilteredSourceResult, SourceFilterConfig
from app.domain.services.benchmark_extractor import BenchmarkExtractor
from app.domain.services.citation_validator import CitationValidator
from app.domain.services.report_generator import ReportGenerator
from app.domain.services.source_filter import SourceFilterService

logger = logging.getLogger(__name__)


class EnhancedResearchFlow:
    """Research flow with structured reporting, source filtering,
    benchmark extraction, and citation discipline."""

    def __init__(
        self,
        llm: LLM,
        search_engine: SearchEngine,
        source_filter_config: SourceFilterConfig | None = None,
        citation_config: CitationConfig | None = None,
    ):
        self.llm = llm
        self.search_engine = search_engine

        # Initialize services
        self.source_filter = SourceFilterService(source_filter_config)
        self.benchmark_extractor = BenchmarkExtractor(llm)
        self.citation_validator = CitationValidator(llm, citation_config)
        self.report_generator = ReportGenerator(llm)

    async def research(
        self,
        query: str,
        report_type: str = "research",
        max_sources: int = 10,
    ) -> AsyncGenerator[BaseEvent | StructuredReportOutput, None]:
        """Execute enhanced research flow.

        Args:
            query: Research query
            report_type: Type of report to generate
            max_sources: Maximum sources to use

        Yields:
            Progress events and final StructuredReportOutput
        """
        start_time = datetime.utcnow()

        # Step 1: Search and gather sources
        logger.info(f"Searching for: {query}")
        raw_sources = await self._search(query)

        # Step 2: Filter sources by quality
        logger.info(f"Filtering {len(raw_sources)} sources")
        filter_result = self.source_filter.filter_sources(raw_sources, query)

        sources = filter_result.accepted_sources[:max_sources]
        logger.info(f"Using {len(sources)} sources after filtering")

        # Step 3: Extract benchmarks
        logger.info("Extracting benchmarks")
        source_data = [
            {"url": s.url, "content": self._get_content(s.url, raw_sources), "title": ""}
            for s in sources
        ]
        benchmark_result = await self.benchmark_extractor.extract(source_data)

        # Step 4: Build citations
        citations = self._build_citations(sources, raw_sources)
        source_scores = {s.url: s for s in sources}

        # Step 5: Generate report
        logger.info("Generating structured report")
        research_data = {
            "query": query,
            "sources": source_data,
            "benchmarks": benchmark_result.benchmarks,
            "comparisons": benchmark_result.comparisons,
        }

        from app.domain.models.source_attribution import AttributionSummary
        attribution = AttributionSummary(
            total_claims=len(sources),
            verified_claims=len([s for s in sources if s.reliability_score > 0.7]),
            average_confidence=sum(s.composite_score for s in sources) / len(sources) if sources else 0,
        )

        report_output = await self.report_generator.generate(
            research_data=research_data,
            report_type=report_type,
            citations=list(citations.values()),
            attribution_summary=attribution,
        )

        # Step 6: Validate citations in report
        logger.info("Validating citations")
        report_content = self._extract_report_content(report_output.report)
        citation_validation = await self.citation_validator.validate(
            content=report_content,
            available_citations={c.id: {"url": c.url, "title": c.title, "excerpt": c.excerpt}
                               for c in report_output.citation_bibliography},
            source_scores=source_scores,
        )

        # Add citation warnings
        if not citation_validation.is_valid:
            report_output.warnings.extend([
                f"Citation coverage: {citation_validation.citation_coverage:.1%}",
                f"Uncited factual claims: {citation_validation.uncited_factual_claims}",
            ])

        # Final output
        yield report_output

    async def _search(self, query: str) -> list[dict]:
        """Execute search and return raw results."""
        results = await self.search_engine.search(query, max_results=20)
        return [
            {
                "url": r.url,
                "title": r.title,
                "content": r.content or r.snippet or "",
                "snippet": r.snippet,
            }
            for r in results
        ]

    def _get_content(self, url: str, sources: list[dict]) -> str:
        """Get content for a URL from raw sources."""
        for s in sources:
            if s.get("url") == url:
                return s.get("content", "")
        return ""

    def _build_citations(
        self,
        filtered_sources: list,
        raw_sources: list[dict],
    ) -> dict[str, Any]:
        """Build citation entries from filtered sources."""
        from app.domain.models.report import CitationEntry

        citations = {}
        for i, source in enumerate(filtered_sources):
            cid = f"[{i + 1}]"
            raw = next((s for s in raw_sources if s.get("url") == source.url), {})

            citations[cid] = CitationEntry(
                id=cid,
                url=source.url,
                title=raw.get("title", "Unknown"),
                accessed_at=datetime.utcnow(),
                source_type="web",
                reliability_score=source.reliability_score,
                excerpt=raw.get("snippet"),
            )

        return citations

    def _extract_report_content(self, report: Any) -> str:
        """Extract text content from report for validation."""
        parts = []

        if hasattr(report, "executive_summary"):
            parts.append(report.executive_summary)

        if hasattr(report, "sections"):
            for section in report.sections:
                parts.append(section.content)

        if hasattr(report, "key_findings"):
            for finding in report.key_findings:
                parts.append(finding.finding)

        return "\n\n".join(parts)
```

---

## Implementation Phases

| Phase | Component | Priority | Dependencies |
|-------|-----------|----------|--------------|
| 1 | Report Models | P0 | None |
| 1 | Report Generator | P0 | Report Models |
| 2 | Source Quality Models | P0 | None |
| 2 | Source Filter Service | P0 | Source Quality Models |
| 3 | Benchmark Models | P1 | None |
| 3 | Benchmark Extractor | P1 | Benchmark Models |
| 4 | Citation Discipline Models | P1 | None |
| 4 | Citation Validator | P1 | Citation Models |
| 5 | Enhanced Research Flow | P2 | All above |

---

## Testing Strategy

### Unit Tests
- Model validation tests for all new Pydantic models
- Service tests with mocked LLM responses
- Source filtering edge cases

### Integration Tests
- End-to-end research flow with real LLM
- Citation validation on sample reports
- Benchmark extraction accuracy

### Evaluation Metrics
- Citation coverage percentage
- Source quality distribution
- Benchmark extraction precision/recall
- Report structure completeness

---

## Configuration

Add to `backend/app/core/config.py`:

```python
class ResearchConfig(BaseSettings):
    """Research enhancement configuration."""

    # Source filtering
    source_min_reliability: float = 0.4
    source_min_relevance: float = 0.5
    source_max_age_days: int = 730

    # Citation discipline
    citation_requirement: str = "moderate"  # strict, moderate, relaxed
    citation_min_coverage: float = 0.7

    # Benchmark extraction
    benchmark_extraction_enabled: bool = True
    benchmark_min_confidence: float = 0.5

    # Report generation
    report_max_retries: int = 3
    report_include_methodology: bool = True
```

---

## Migration Notes

1. Existing `SourceAttribution` and `SourceCitation` models remain compatible
2. New models extend functionality without breaking changes
3. Gradual rollout via feature flags recommended
4. Monitor LLM token usage as extraction increases calls
