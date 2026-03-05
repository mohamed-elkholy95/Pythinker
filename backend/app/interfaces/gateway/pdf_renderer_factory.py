"""Shared PDF renderer selection used by gateway and API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.services.pdf.pdf_renderer import PdfReportRenderer

if TYPE_CHECKING:
    from app.core.config import Settings


def build_configured_pdf_renderer(*, settings: Settings) -> PdfReportRenderer:
    """Return a PDF renderer configured from settings with safe fallback."""
    from app.interfaces.dependencies import build_pdf_renderer_from_settings

    return build_pdf_renderer_from_settings(settings)
