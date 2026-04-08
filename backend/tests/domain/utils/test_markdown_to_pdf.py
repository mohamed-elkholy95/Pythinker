"""Tests for Markdown -> ReportLab PDF conversion helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import cast

from pypdf import PdfReader
from reportlab.platypus import HRFlowable, Image, ListFlowable, Paragraph, Preformatted, Table

import app.domain.utils.markdown_to_pdf as markdown_to_pdf
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


def test_markdown_to_flowables_preserves_brackets_for_numeric_citation_links() -> None:
    flowables = markdown_to_flowables("Claim [1](https://example.com/source).")
    paragraph = next(item for item in flowables if isinstance(item, Paragraph))
    paragraph = cast(Paragraph, paragraph)
    assert '[<a href="https://example.com/source">1</a>]' in paragraph.text


def test_markdown_to_flowables_renders_mermaid_placeholder_as_image() -> None:
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    flowables = markdown_to_flowables(
        "<!--MERMAID:abc123-->",
        mermaid_images={"abc123": png_bytes},
    )

    assert any(isinstance(item, Image) for item in flowables)


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
    assert "[1]" in extracted
    assert "Example Source" in extracted


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


def test_register_unicode_font_uses_fallback_font_when_preferred_missing(monkeypatch) -> None:
    class _DummyTTFont:
        def __init__(self, name: str, path: str) -> None:
            self.name = name
            self.path = path

    register_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(markdown_to_pdf.pdfmetrics, "getRegisteredFontNames", lambda: [])
    monkeypatch.setattr(
        markdown_to_pdf.pdfmetrics, "registerFont", lambda ttfont: register_calls.append((ttfont.name, ttfont.path))
    )
    monkeypatch.setattr(markdown_to_pdf, "TTFont", _DummyTTFont)
    monkeypatch.setattr(
        markdown_to_pdf,
        "_FONT_PATH_CANDIDATES",
        {
            "DejaVuSans": (Path("/tmp/missing-dejavu.ttf"),),
            "LiberationSans": (Path("/tmp/liberation.ttf"),),
            "FreeSans": (Path("/tmp/freesans.ttf"),),
            "Unifont": (Path("/tmp/unifont.otf"),),
        },
    )
    monkeypatch.setattr(Path, "exists", lambda p: p == Path("/tmp/liberation.ttf"))

    chosen = markdown_to_pdf.register_unicode_font("DejaVuSans")

    assert chosen == "LiberationSans"
    assert register_calls == [("LiberationSans", str(Path("/tmp/liberation.ttf")))]
