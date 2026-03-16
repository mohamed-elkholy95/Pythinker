"""Tests for ReportLab PDF renderer Mermaid preprocessing."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.domain.models.source_citation import SourceCitation
from app.domain.services.pdf.mermaid_preprocessor import MermaidPreprocessor
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.reportlab_pdf_renderer import ReportLabPdfRenderer


def _make_mermaid_preprocessor() -> MermaidPreprocessor:
    """Build a MermaidPreprocessor with a mock httpx client for tests."""
    mock_client = MagicMock(spec=httpx.AsyncClient)
    return MermaidPreprocessor(http_client=mock_client)


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
        "app.domain.services.pdf.mermaid_preprocessor.MermaidPreprocessor.preprocess_markdown",
        AsyncMock(return_value=("<!--MERMAID:abc123-->", {"abc123": png_bytes})),
    )
    build_pdf_bytes = mocker.patch(
        "app.domain.services.pdf.reportlab_pdf_renderer.build_pdf_bytes",
        return_value=b"%PDF-1.4 test",
    )

    renderer = ReportLabPdfRenderer(mermaid=_make_mermaid_preprocessor())
    result = await renderer.render(payload)

    assert result == b"%PDF-1.4 test"
    build_pdf_bytes.assert_called_once()
    assert build_pdf_bytes.call_args.kwargs["content"] == "<!--MERMAID:abc123-->"
    assert build_pdf_bytes.call_args.kwargs["mermaid_images"] == {"abc123": png_bytes}
