"""Shared PDF renderer selection used by gateway and API routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.services.pdf.pdf_renderer import PdfReportRenderer
from app.domain.services.pdf.reportlab_pdf_renderer import ReportLabPdfRenderer

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


def build_configured_pdf_renderer(*, settings: Settings) -> PdfReportRenderer:
    """Return a PDF renderer configured from settings with safe fallback."""
    reportlab_renderer = ReportLabPdfRenderer()
    renderer_choice = (settings.telegram_pdf_renderer or "reportlab").strip().lower()
    if renderer_choice != "playwright":
        return reportlab_renderer

    try:
        from app.infrastructure.external.pdf import PlaywrightPdfRenderer

        return PlaywrightPdfRenderer(
            timeout_ms=settings.telegram_pdf_renderer_timeout_ms,
            fallback_renderer=reportlab_renderer,
        )
    except Exception as exc:
        logger.warning("Failed to initialize Playwright PDF renderer; using ReportLab fallback: %s", exc)
        return reportlab_renderer
