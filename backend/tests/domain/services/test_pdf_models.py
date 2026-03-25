"""Tests for ReportPdfPayload domain model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.source_citation import SourceCitation
from app.domain.services.pdf.models import ReportPdfPayload


def _make_citation(
    url: str = "https://example.com",
    title: str = "Example Source",
    source_type: str = "search",
    snippet: str | None = None,
) -> SourceCitation:
    return SourceCitation(
        url=url,
        title=title,
        snippet=snippet,
        access_time=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        source_type=source_type,  # type: ignore[arg-type]
    )


@pytest.mark.unit
class TestReportPdfPayloadRequiredFields:
    def test_minimal_construction(self) -> None:
        payload = ReportPdfPayload(
            title="AI Frameworks Report",
            markdown_content="# Overview\n\nContent here.",
        )
        assert payload.title == "AI Frameworks Report"
        assert payload.markdown_content == "# Overview\n\nContent here."

    def test_missing_title_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReportPdfPayload(markdown_content="# Content")  # type: ignore[call-arg]

    def test_missing_markdown_content_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReportPdfPayload(title="Report Title")  # type: ignore[call-arg]

    def test_both_required_fields_missing_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReportPdfPayload()  # type: ignore[call-arg]


@pytest.mark.unit
class TestReportPdfPayloadDefaults:
    def test_sources_default_empty_list(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.sources == []

    def test_author_default(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.author == "Pythinker AI Agent"

    def test_subject_default_none(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.subject is None

    def test_creator_default(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.creator == "Pythinker / ReportLab"

    def test_include_toc_default_true(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.include_toc is True

    def test_toc_min_sections_default_three(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.toc_min_sections == 3

    def test_preferred_font_default(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.preferred_font == "DejaVuSans"

    def test_generated_at_default_utc_aware(self) -> None:
        payload = ReportPdfPayload(title="T", markdown_content="M")
        assert payload.generated_at.tzinfo is not None
        assert payload.generated_at.tzinfo == UTC

    def test_generated_at_is_recent(self) -> None:
        before = datetime.now(UTC)
        payload = ReportPdfPayload(title="T", markdown_content="M")
        after = datetime.now(UTC)
        assert before <= payload.generated_at <= after


@pytest.mark.unit
class TestReportPdfPayloadExplicitFields:
    def test_author_override(self) -> None:
        payload = ReportPdfPayload(
            title="Custom Report",
            markdown_content="content",
            author="Research Bot",
        )
        assert payload.author == "Research Bot"

    def test_subject_set(self) -> None:
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            subject="AI Landscape 2026",
        )
        assert payload.subject == "AI Landscape 2026"

    def test_creator_override(self) -> None:
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            creator="Custom / PDFLib",
        )
        assert payload.creator == "Custom / PDFLib"

    def test_include_toc_false(self) -> None:
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            include_toc=False,
        )
        assert payload.include_toc is False

    def test_toc_min_sections_override(self) -> None:
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            toc_min_sections=5,
        )
        assert payload.toc_min_sections == 5

    def test_toc_min_sections_one(self) -> None:
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            toc_min_sections=1,
        )
        assert payload.toc_min_sections == 1

    def test_preferred_font_override(self) -> None:
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            preferred_font="Helvetica",
        )
        assert payload.preferred_font == "Helvetica"

    def test_generated_at_explicit(self) -> None:
        t = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            generated_at=t,
        )
        assert payload.generated_at == t


@pytest.mark.unit
class TestReportPdfPayloadWithSources:
    def test_single_search_citation(self) -> None:
        payload = ReportPdfPayload(
            title="Report",
            markdown_content="content",
            sources=[_make_citation()],
        )
        assert len(payload.sources) == 1
        assert payload.sources[0].url == "https://example.com"
        assert payload.sources[0].source_type == "search"

    def test_multiple_mixed_citations(self) -> None:
        citations = [
            _make_citation(
                url="https://search.example.com",
                title="Search Result",
                source_type="search",
            ),
            _make_citation(
                url="https://browser.example.com",
                title="Browser Page",
                source_type="browser",
                snippet="A page snippet",
            ),
            _make_citation(
                url="file:///tmp/report.csv",
                title="Data File",
                source_type="file",
            ),
        ]
        payload = ReportPdfPayload(
            title="Mixed Sources Report",
            markdown_content="# Analysis\n\nFindings...",
            sources=citations,
        )
        assert len(payload.sources) == 3
        assert payload.sources[0].source_type == "search"
        assert payload.sources[1].source_type == "browser"
        assert payload.sources[1].snippet == "A page snippet"
        assert payload.sources[2].source_type == "file"

    def test_sources_with_snippets(self) -> None:
        payload = ReportPdfPayload(
            title="Snippet Report",
            markdown_content="content",
            sources=[
                _make_citation(snippet="First 200 chars of the page...")
            ],
        )
        assert payload.sources[0].snippet == "First 200 chars of the page..."

    def test_sources_without_snippets(self) -> None:
        payload = ReportPdfPayload(
            title="No Snippet Report",
            markdown_content="content",
            sources=[_make_citation(snippet=None)],
        )
        assert payload.sources[0].snippet is None

    def test_source_lists_are_independent(self) -> None:
        p1 = ReportPdfPayload(title="T1", markdown_content="M1")
        p2 = ReportPdfPayload(title="T2", markdown_content="M2")
        p1.sources.append(_make_citation())
        assert p2.sources == []


@pytest.mark.unit
class TestReportPdfPayloadTocSettings:
    def test_toc_enabled_with_min_sections(self) -> None:
        payload = ReportPdfPayload(
            title="T",
            markdown_content="M",
            include_toc=True,
            toc_min_sections=4,
        )
        assert payload.include_toc is True
        assert payload.toc_min_sections == 4

    def test_toc_disabled_min_sections_irrelevant(self) -> None:
        payload = ReportPdfPayload(
            title="T",
            markdown_content="M",
            include_toc=False,
            toc_min_sections=10,
        )
        assert payload.include_toc is False
        assert payload.toc_min_sections == 10


@pytest.mark.unit
class TestReportPdfPayloadSerialization:
    def test_roundtrip_no_sources(self) -> None:
        t = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)
        payload = ReportPdfPayload(
            title="Serialization Test Report",
            markdown_content="# Heading\n\nBody.",
            author="Test Author",
            subject="Testing",
            creator="Test Runner",
            include_toc=False,
            toc_min_sections=2,
            preferred_font="Helvetica",
            generated_at=t,
        )
        data = payload.model_dump()
        payload2 = ReportPdfPayload.model_validate(data)
        assert payload2.title == payload.title
        assert payload2.markdown_content == payload.markdown_content
        assert payload2.author == payload.author
        assert payload2.subject == payload.subject
        assert payload2.creator == payload.creator
        assert payload2.include_toc == payload.include_toc
        assert payload2.toc_min_sections == payload.toc_min_sections
        assert payload2.preferred_font == payload.preferred_font
        assert payload2.sources == []

    def test_roundtrip_with_sources(self) -> None:
        payload = ReportPdfPayload(
            title="Report with Sources",
            markdown_content="content",
            sources=[
                _make_citation(
                    url="https://example.com/ref",
                    title="Reference",
                    source_type="search",
                    snippet="snippet text",
                )
            ],
        )
        data = payload.model_dump()
        payload2 = ReportPdfPayload.model_validate(data)
        assert len(payload2.sources) == 1
        assert payload2.sources[0].url == "https://example.com/ref"
        assert payload2.sources[0].snippet == "snippet text"

    def test_json_roundtrip(self) -> None:
        payload = ReportPdfPayload(
            title="JSON Report",
            markdown_content="# Section\n\nText.",
            author="JSON Author",
        )
        json_str = payload.model_dump_json()
        payload2 = ReportPdfPayload.model_validate_json(json_str)
        assert payload2.title == "JSON Report"
        assert payload2.author == "JSON Author"
        assert payload2.include_toc is True
