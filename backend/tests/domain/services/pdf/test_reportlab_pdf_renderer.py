"""Tests for ReportLab PDF renderer Mermaid preprocessing."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.domain.models.source_citation import SourceCitation
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.reportlab_pdf_renderer import ReportLabPdfRenderer


@pytest.mark.asyncio
async def test_reportlab_renderer_passes_preprocessed_mermaid_images(mocker) -> None:
    png_bytes = b"png-bytes"
    payload = ReportPdfPayload(
        title="Mermaid Report",
        markdown_content="```mermaid\ngraph TD\n  A-->B\n```",
        sources=[
            SourceCitation(
                url="https://example.com",
                title="Example",
                snippet="",
                access_time=datetime.now(UTC),
                source_type="search",
            )
        ],
    )

    mocker.patch(
        "app.domain.services.pdf.reportlab_pdf_renderer.MermaidPreprocessor.preprocess_markdown",
        AsyncMock(return_value=("<!--MERMAID:abc123-->", {"abc123": png_bytes})),
    )
    build_pdf_bytes = mocker.patch(
        "app.domain.services.pdf.reportlab_pdf_renderer.build_pdf_bytes",
        return_value=b"%PDF-1.4 test",
    )

    renderer = ReportLabPdfRenderer(sandbox_base_url="http://sandbox:8080")
    result = await renderer.render(payload)

    assert result == b"%PDF-1.4 test"
    build_pdf_bytes.assert_called_once()
    assert build_pdf_bytes.call_args.kwargs["content"] == "<!--MERMAID:abc123-->"
    assert build_pdf_bytes.call_args.kwargs["mermaid_images"] == {"abc123": png_bytes}
