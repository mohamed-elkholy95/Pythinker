"""Tests for Markdown -> ReportLab PDF conversion helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import cast

from pypdf import PdfReader
from reportlab.platypus import HRFlowable, ListFlowable, Paragraph, Preformatted, Table

from app.domain.models.source_citation import SourceCitation
from app.domain.utils.markdown_to_pdf import build_pdf_bytes, markdown_to_flowables


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_markdown_to_flowables_maps_markdown_elements() -> None:
    content = """# Main Heading

Paragraph text with [Reference](https://example.com).

- bullet one
- bullet two

1. first
2. second

| Col A | Col B |
|---|---|
| A1 | B1 |
| A2 | B2 |

---

```python
print("hello")
```
"""
    flowables = markdown_to_flowables(content)

    assert any(isinstance(item, Paragraph) and item.style.name == "Heading1" for item in flowables)
    assert any(isinstance(item, ListFlowable) for item in flowables)
    assert any(isinstance(item, Table) for item in flowables)
    assert any(isinstance(item, HRFlowable) for item in flowables)
    assert any(isinstance(item, Preformatted) for item in flowables)


def test_markdown_to_flowables_preserves_links() -> None:
    flowables = markdown_to_flowables("Visit [Example](https://example.com).")
    paragraph = next(item for item in flowables if isinstance(item, Paragraph))
    paragraph = cast(Paragraph, paragraph)
    assert '<a href="https://example.com">Example</a>' in paragraph.text


def test_build_pdf_bytes_sets_metadata_and_bibliography() -> None:
    sources = [
        SourceCitation(
            url="https://example.com/source-1",
            title="Example Source",
            snippet="Snippet",
            access_time=datetime.now(UTC),
            source_type="search",
        )
    ]

    pdf_bytes = build_pdf_bytes(
        title="My Report",
        content="# Findings\n\nThis is the report body.",
        sources=sources,
        include_toc=False,
    )

    reader = PdfReader(BytesIO(pdf_bytes))
    metadata = reader.metadata
    extracted = _extract_pdf_text(pdf_bytes)

    assert metadata is not None
    assert metadata.title == "My Report"
    assert metadata.author == "Pythinker AI Agent"
    assert metadata.creator == "Pythinker / ReportLab"
    assert "References" in extracted
    assert "Example Source" in extracted
    assert "https://example.com/source-1" in extracted


def test_build_pdf_bytes_generates_toc_for_multi_section_reports() -> None:
    content = """# Title

## Section One
Body one.

## Section Two
Body two.

## Section Three
Body three.
"""
    pdf_bytes = build_pdf_bytes(
        title="TOC Report",
        content=content,
        include_toc=True,
        toc_min_sections=3,
    )

    extracted = _extract_pdf_text(pdf_bytes)
    assert "Table of Contents" in extracted


def test_build_pdf_bytes_renders_unicode_text_without_error() -> None:
    pdf_bytes = build_pdf_bytes(
        title="Unicode",
        content="# Český nadpis\n\nŽluťoučký kůň, café!",
        include_toc=False,
    )

    extracted = _extract_pdf_text(pdf_bytes)
    assert "Český nadpis" in extracted
    assert "Žluťoučký kůň, café!" in extracted
