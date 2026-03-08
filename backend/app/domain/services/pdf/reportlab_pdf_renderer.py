"""ReportLab-backed PDF renderer with optional Mermaid diagram support."""

from __future__ import annotations

import logging

from app.core import prometheus_metrics as pm
from app.domain.services.pdf.mermaid_preprocessor import MermaidPreprocessor
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.pdf_renderer import PdfReportRenderer
from app.domain.utils.markdown_to_pdf import build_pdf_bytes

logger = logging.getLogger(__name__)


class ReportLabPdfRenderer(PdfReportRenderer):
    """Render PDF bytes using the existing ReportLab pipeline.

    When a sandbox_base_url is provided, Mermaid code blocks are pre-rendered
    to PNG via the sandbox mmdc CLI before PDF generation.
    """

    def __init__(self, *, sandbox_base_url: str | None = None) -> None:
        self._mermaid: MermaidPreprocessor | None = None
        if sandbox_base_url:
            self._mermaid = MermaidPreprocessor(sandbox_base_url=sandbox_base_url)

    async def render(self, payload: ReportPdfPayload) -> bytes:
        pm.telegram_pdf_renderer_invocations_total.inc({"renderer": "reportlab"})

        content = payload.markdown_content
        mermaid_images: dict[str, bytes] = {}

        # Pre-render mermaid blocks if sandbox is available
        if self._mermaid:
            try:
                content, mermaid_images = await self._mermaid.preprocess_markdown(content)
                if mermaid_images:
                    logger.info("Pre-rendered %d Mermaid diagram(s) for PDF", len(mermaid_images))
            except Exception:
                logger.warning("Mermaid preprocessing failed, using raw markdown", exc_info=True)

        pdf_bytes = build_pdf_bytes(
            title=payload.title,
            content=content,
            sources=payload.sources,
            include_toc=payload.include_toc,
            toc_min_sections=payload.toc_min_sections,
            author=payload.author,
            subject=payload.subject,
            creator=payload.creator,
            preferred_font=payload.preferred_font,
            mermaid_images=mermaid_images or None,
        )
        pm.telegram_pdf_renderer_success_total.inc({"renderer": "reportlab"})
        return pdf_bytes
