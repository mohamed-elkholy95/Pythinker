"""Tests for report models (app.domain.models.report).

Covers ReportType, ReportSection validation, KeyFinding, Benchmark,
ComparisonItem, report types (Research, Comparison, Analysis),
ReportMetadata, CitationEntry, and StructuredReportOutput.
"""

import pytest

from app.domain.models.report import (
    AnalysisReport,
    Benchmark,
    CitationEntry,
    ComparisonItem,
    ComparisonReport,
    KeyFinding,
    ReportMetadata,
    ReportSection,
    ReportType,
    ResearchReport,
    StructuredReportOutput,
)

# ── ReportType ───────────────────────────────────────────────────────


class TestReportType:
    def test_values(self) -> None:
        assert ReportType.RESEARCH == "research"
        assert ReportType.ANALYSIS == "analysis"
        assert ReportType.COMPARISON == "comparison"
        assert ReportType.SUMMARY == "summary"
        assert ReportType.TECHNICAL == "technical"


# ── ReportSection ────────────────────────────────────────────────────


class TestReportSection:
    def test_valid_section(self) -> None:
        section = ReportSection(
            heading="Introduction",
            content="This report covers the analysis of modern frameworks.",
        )
        assert section.heading == "Introduction"
        assert section.confidence == 0.8  # default

    def test_placeholder_content_rejected(self) -> None:
        with pytest.raises(ValueError, match="placeholder"):
            ReportSection(heading="Test Section", content="This is todo content here")

    def test_placeholder_tbd_rejected(self) -> None:
        with pytest.raises(ValueError, match="placeholder"):
            ReportSection(heading="Test Section", content="This is TBD content here")

    def test_placeholder_lorem_rejected(self) -> None:
        with pytest.raises(ValueError, match="placeholder"):
            ReportSection(heading="Test Section", content="Lorem ipsum dolor sit amet")

    def test_heading_min_length(self) -> None:
        with pytest.raises(ValueError):
            ReportSection(heading="AB", content="Valid content here for the section")

    def test_content_min_length(self) -> None:
        with pytest.raises(ValueError):
            ReportSection(heading="Valid Heading", content="Short")

    def test_custom_confidence(self) -> None:
        section = ReportSection(
            heading="Findings",
            content="Detailed findings from the research analysis.",
            confidence=0.95,
        )
        assert section.confidence == 0.95

    def test_citations_default_empty(self) -> None:
        section = ReportSection(heading="Heading", content="Content that is long enough here.")
        assert section.citations == []


# ── KeyFinding ───────────────────────────────────────────────────────


class TestKeyFinding:
    def test_creation(self) -> None:
        finding = KeyFinding(
            finding="AI adoption grew 40% in 2026",
            supporting_evidence=["Survey data from 500 companies"],
            citation_ids=["[1]"],
            confidence=0.9,
        )
        assert finding.finding == "AI adoption grew 40% in 2026"
        assert finding.is_inferred is False

    def test_inferred_finding(self) -> None:
        finding = KeyFinding(
            finding="Market will likely consolidate",
            supporting_evidence=["Merger trends"],
            citation_ids=["[2]"],
            is_inferred=True,
        )
        assert finding.is_inferred is True


# ── Benchmark ────────────────────────────────────────────────────────


class TestBenchmark:
    def test_creation(self) -> None:
        bm = Benchmark(
            name="Inference Latency",
            value="150ms",
            unit="milliseconds",
            source_url="https://example.com/benchmarks",
            context="Measured on A100 GPU with batch size 1",
        )
        assert bm.name == "Inference Latency"
        assert bm.value == "150ms"


# ── ComparisonItem ───────────────────────────────────────────────────


class TestComparisonItem:
    def test_creation(self) -> None:
        item = ComparisonItem(
            name="Framework A",
            attributes={"speed": "fast", "ease_of_use": 8.5},
            pros=["Easy setup", "Good docs"],
            cons=["Limited plugins"],
        )
        assert item.name == "Framework A"
        assert len(item.pros) == 2
        assert len(item.cons) == 1


# ── ResearchReport ───────────────────────────────────────────────────


class TestResearchReport:
    def test_creation(self) -> None:
        report = ResearchReport(
            title="AI Agent Market Analysis 2026",
            executive_summary="This report examines the state of AI agent technology in 2026, covering key trends, challenges, and opportunities.",
            key_findings=[
                KeyFinding(
                    finding="Adoption rate doubled",
                    supporting_evidence=["Market data"],
                    citation_ids=["[1]"],
                ),
            ],
            sections=[
                ReportSection(
                    heading="Market Overview",
                    content="The AI agent market has grown significantly in the past year.",
                ),
            ],
        )
        assert report.report_type == "research"
        assert report.title == "AI Agent Market Analysis 2026"
        assert len(report.key_findings) == 1
        assert report.generated_at is not None


# ── ComparisonReport ─────────────────────────────────────────────────


class TestComparisonReport:
    def test_creation(self) -> None:
        report = ComparisonReport(
            title="Framework A vs Framework B Comparison",
            items=[
                ComparisonItem(name="A", attributes={"speed": "fast"}),
                ComparisonItem(name="B", attributes={"speed": "slow"}),
            ],
            comparison_criteria=["speed", "reliability"],
            winner="A",
            recommendation="Use A for performance-critical applications.",
        )
        assert report.report_type == "comparison"
        assert len(report.items) == 2
        assert report.winner == "A"


# ── AnalysisReport ───────────────────────────────────────────────────


class TestAnalysisReport:
    def test_creation(self) -> None:
        report = AnalysisReport(
            title="Security Risk Assessment for API Gateway",
            subject="API Gateway v2.0",
            analysis_type="security",
            findings=[
                KeyFinding(
                    finding="SQL injection vulnerability found",
                    supporting_evidence=["Code scan results"],
                    citation_ids=["[scan-1]"],
                ),
            ],
            risk_score=0.7,
            recommendations=["Sanitize all inputs", "Add WAF"],
        )
        assert report.report_type == "analysis"
        assert report.risk_score == 0.7
        assert len(report.recommendations) == 2


# ── ReportMetadata ───────────────────────────────────────────────────


class TestReportMetadata:
    def test_defaults(self) -> None:
        meta = ReportMetadata()
        assert meta.total_sources_consulted == 0
        assert meta.sources_used == 0
        assert meta.average_source_quality == 0.0
        assert meta.hallucination_checks_passed == 0

    def test_custom_values(self) -> None:
        meta = ReportMetadata(
            total_sources_consulted=20,
            sources_used=15,
            sources_filtered=5,
            average_source_quality=0.85,
            generation_time_seconds=45.2,
            token_usage=15000,
            hallucination_checks_passed=12,
            hallucination_checks_failed=1,
        )
        assert meta.total_sources_consulted == 20
        assert meta.hallucination_checks_failed == 1


# ── CitationEntry ────────────────────────────────────────────────────


class TestCitationEntry:
    def test_creation(self) -> None:
        from datetime import UTC, datetime

        entry = CitationEntry(
            id="[1]",
            url="https://example.com/article",
            title="Research Article",
            accessed_at=datetime(2026, 3, 26, tzinfo=UTC),
            source_type="web",
            reliability_score=0.9,
            excerpt="Key finding from the article",
        )
        assert entry.id == "[1]"
        assert entry.source_type == "web"
        assert entry.reliability_score == 0.9


# ── StructuredReportOutput ───────────────────────────────────────────


class TestStructuredReportOutput:
    def test_creation(self) -> None:
        report = ResearchReport(
            title="Test Report for Structured Output",
            executive_summary="A comprehensive test report to validate the structured output model works correctly.",
            key_findings=[
                KeyFinding(
                    finding="Tests pass",
                    supporting_evidence=["pytest output"],
                    citation_ids=["[test]"],
                ),
            ],
            sections=[
                ReportSection(
                    heading="Test Results",
                    content="All unit tests passed successfully.",
                ),
            ],
        )
        output = StructuredReportOutput(
            report=report,
            metadata=ReportMetadata(sources_used=5),
            quality_score=0.95,
            warnings=["Some sources may be outdated"],
        )
        assert output.quality_score == 0.95
        assert len(output.warnings) == 1
        assert output.report.report_type == "research"
