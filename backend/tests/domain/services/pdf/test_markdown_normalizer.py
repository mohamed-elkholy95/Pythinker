"""Tests for PDF markdown normalization and citation/reference reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.models.source_citation import SourceCitation
from app.domain.services.pdf.markdown_normalizer import normalize_markdown_for_pdf


def test_normalizer_linkifies_inline_citations_and_builds_references_from_sources() -> None:
    sources = [
        SourceCitation(
            url="https://example.com/one",
            title="Source One",
            snippet=None,
            access_time=datetime.now(UTC),
            source_type="search",
        ),
        SourceCitation(
            url="https://example.com/two",
            title="Source Two",
            snippet=None,
            access_time=datetime.now(UTC),
            source_type="search",
        ),
    ]
    content = "# Report\n\nClaim A [1][2].\nClaim B [3]."

    normalized = normalize_markdown_for_pdf(content, sources)

    assert "[1](#ref-1)" in normalized.markdown
    assert "[2](#ref-2)" in normalized.markdown
    assert "[3](#ref-3)" in normalized.markdown
    assert "## References" in normalized.markdown
    assert "1. [Source One](https://example.com/one)" in normalized.markdown
    assert "2. [Source Two](https://example.com/two)" in normalized.markdown
    assert "3. Unresolved citation" in normalized.markdown
    assert normalized.unresolved_citations == [3]


def test_normalizer_does_not_linkify_citations_inside_code_fences() -> None:
    content = """# Report

Before [1].

```python
print('[2] should stay literal')
```
"""

    normalized = normalize_markdown_for_pdf(content, [])

    assert "Before.[1](#ref-1)" in normalized.markdown
    assert "print('[2] should stay literal')" in normalized.markdown


def test_normalizer_uses_existing_references_when_structured_sources_absent() -> None:
    content = """# Report

Result improved [2].

## References

[1] Older source
[2] https://example.com/new
"""

    normalized = normalize_markdown_for_pdf(content, [])

    assert "1. Older source" in normalized.markdown
    assert "2. https://example.com/new" in normalized.markdown
    assert normalized.unresolved_citations == []


def test_normalizer_merges_existing_references_with_structured_sources() -> None:
    sources = [
        SourceCitation(
            url="https://example.com/one",
            title="Source One",
            snippet=None,
            access_time=datetime.now(UTC),
            source_type="search",
        ),
    ]
    content = """# Report

Result improved [1] and [2].

## References

[1] stale source text
[2] https://example.com/two
"""

    normalized = normalize_markdown_for_pdf(content, sources)

    assert "1. [Source One](https://example.com/one)" in normalized.markdown
    assert "2. https://example.com/two" in normalized.markdown
    assert normalized.unresolved_citations == []
