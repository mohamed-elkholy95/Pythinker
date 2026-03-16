"""Contract tests for Telegram PDF design/citation parity regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.platypus import Paragraph, Table

from app.domain.models.source_citation import SourceCitation
from app.domain.utils.markdown_to_pdf import build_pdf_bytes, markdown_to_flowables


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _load_fixture(name: str) -> str:
    fixture = Path(__file__).resolve().parents[3] / "fixtures" / "reports" / name
    return fixture.read_text(encoding="utf-8")


def test_pdf_generation_does_not_duplicate_references_heading_when_markdown_already_has_references() -> None:
    content = _load_fixture("sample_modal_parity_report.md")
    sources = [
        SourceCitation(
            url="https://example.com/source-1",
            title="Structured Source",
            snippet="snippet",
            access_time=datetime.now(UTC),
            source_type="search",
        )
    ]

    pdf_bytes = build_pdf_bytes(
        title="Parity Report",
        content=content,
        sources=sources,
        include_toc=False,
    )

    extracted = _extract_pdf_text(pdf_bytes)
    assert extracted.count("References") == 1


def test_markdown_tables_render_paragraph_cells_not_raw_markup_strings() -> None:
    content = """# Table Test

| Col A | Col B |
|---|---|
| **Bold** value | [Link](https://example.com) |
"""
    flowables = markdown_to_flowables(content)

    table = next(item for item in flowables if isinstance(item, Table))

    for row in table._cellvalues:
        for cell in row:
            assert isinstance(cell, Paragraph)


def test_pdf_title_metadata_strips_non_text_symbol_glyphs() -> None:
    pdf_bytes = build_pdf_bytes(
        title="🔬 Research Report: Agent Memory",
        content="# Body\n\ncontent",
        include_toc=False,
    )

    reader = PdfReader(BytesIO(pdf_bytes))
    metadata = reader.metadata

    assert metadata is not None
    assert metadata.title is not None
    assert "🔬" not in metadata.title
