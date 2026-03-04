"""ReportLab-backed PDF renderer."""

from __future__ import annotations

from app.core import prometheus_metrics as pm
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.pdf_renderer import PdfReportRenderer
from app.domain.utils.markdown_to_pdf import build_pdf_bytes


class ReportLabPdfRenderer(PdfReportRenderer):
    """Render PDF bytes using the existing ReportLab pipeline."""

    async def render(self, payload: ReportPdfPayload) -> bytes:
        pm.telegram_pdf_renderer_invocations_total.inc({"renderer": "reportlab"})
        pdf_bytes = build_pdf_bytes(
            title=payload.title,
            content=payload.markdown_content,
            sources=payload.sources,
            include_toc=payload.include_toc,
            toc_min_sections=payload.toc_min_sections,
            author=payload.author,
            subject=payload.subject,
            creator=payload.creator,
            preferred_font=payload.preferred_font,
        )
        pm.telegram_pdf_renderer_success_total.inc({"renderer": "reportlab"})
        return pdf_bytes
