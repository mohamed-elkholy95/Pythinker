"""Renderer contract for generating report PDFs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.services.pdf.models import ReportPdfPayload


@runtime_checkable
class PdfReportRenderer(Protocol):
    """Abstraction for report PDF rendering engines."""

    async def render(self, payload: ReportPdfPayload) -> bytes:
        """Render PDF bytes for the provided report payload."""
        ...
