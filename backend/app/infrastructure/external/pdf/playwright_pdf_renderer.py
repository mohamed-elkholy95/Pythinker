"""Playwright-powered PDF renderer for modal-parity report output."""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import UTC
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from playwright.async_api import async_playwright

from app.core import prometheus_metrics as pm
from app.domain.services.pdf.markdown_normalizer import normalize_markdown_for_pdf
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.pdf_renderer import PdfReportRenderer

logger = logging.getLogger(__name__)

_REFERENCES_HEADING_RE = re.compile(r"^(references?|sources?|bibliography|citations?)$", re.IGNORECASE)


class PlaywrightPdfRenderer(PdfReportRenderer):
    """Render report PDFs through Chromium for CSS-accurate layout parity."""

    def __init__(
        self,
        *,
        timeout_ms: int = 20_000,
        fallback_renderer: PdfReportRenderer | None = None,
    ) -> None:
        self._timeout_ms = max(1_000, int(timeout_ms))
        self._fallback_renderer = fallback_renderer

        assets_root = Path(__file__).resolve().parent
        template_root = assets_root / "templates"
        css_path = assets_root / "styles" / "report_document.css"

        env = Environment(
            loader=FileSystemLoader(str(template_root)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._template = env.get_template("report_document.html")
        self._css = css_path.read_text(encoding="utf-8")
        self._markdown = MarkdownIt("gfm-like", {"html": False, "linkify": False, "typographer": False})

    async def render(self, payload: ReportPdfPayload) -> bytes:
        pm.telegram_pdf_renderer_invocations_total.inc({"renderer": "playwright"})
        normalized = normalize_markdown_for_pdf(payload.markdown_content, payload.sources)
        if normalized.unresolved_citations:
            pm.telegram_pdf_citation_integrity_total.inc({"status": "unresolved"})
            logger.warning(
                ("telegram.pdf.citation.unresolved title=%s citation_numbers=%s unresolved=%s reference_count=%s"),
                payload.title,
                normalized.citation_numbers,
                normalized.unresolved_citations,
                normalized.reference_count,
            )
        else:
            pm.telegram_pdf_citation_integrity_total.inc({"status": "ok"})

        body_html = self._markdown.render(normalized.markdown)
        body_html = _decorate_reference_ids(body_html)

        html = self._template.render(
            title=(payload.title or "Report").strip() or "Report",
            author=(payload.author or "Pythinker AI Agent").strip() or "Pythinker AI Agent",
            generated_date=payload.generated_at.astimezone(UTC).strftime("%B %-d, %Y")
            if hasattr(payload.generated_at, "astimezone")
            else "",
            css=self._css,
            body_html=body_html,
        )

        try:
            pdf_bytes = await self._render_with_playwright(html)
            pm.telegram_pdf_renderer_success_total.inc({"renderer": "playwright"})
            return pdf_bytes
        except Exception as exc:
            logger.warning("Playwright PDF renderer failed: %s", exc)
            if self._fallback_renderer is not None:
                pm.telegram_pdf_renderer_fallback_total.inc(
                    {
                        "from_renderer": "playwright",
                        "to_renderer": _renderer_label(self._fallback_renderer),
                        "reason": type(exc).__name__.lower(),
                    }
                )
                return await self._fallback_renderer.render(payload)
            raise

    async def _render_with_playwright(self, html: str) -> bytes:
        browser = None
        context = None
        page = None
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(html, wait_until="networkidle", timeout=self._timeout_ms)
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )

        with contextlib.suppress(Exception):
            if page is not None:
                await page.close()
        with contextlib.suppress(Exception):
            if context is not None:
                await context.close()
        with contextlib.suppress(Exception):
            if browser is not None:
                await browser.close()

        return pdf_bytes


def _decorate_reference_ids(html: str) -> str:
    """Attach stable id anchors (ref-N) to references list items."""
    soup = BeautifulSoup(html, "html.parser")
    headings = soup.find_all(["h1", "h2", "h3", "h4"])

    references_heading = None
    for heading in headings:
        text = heading.get_text(" ", strip=True)
        if _REFERENCES_HEADING_RE.match(text):
            references_heading = heading
            break

    if references_heading is None:
        return str(soup)

    number = 1
    sibling = references_heading.find_next_sibling()
    while sibling is not None:
        if sibling.name in {"h1", "h2", "h3", "h4"}:
            break
        if sibling.name in {"ol", "ul"}:
            for item in sibling.find_all("li", recursive=False):
                item["id"] = f"ref-{number}"
                number += 1
        sibling = sibling.find_next_sibling()

    return str(soup)


def _renderer_label(renderer: PdfReportRenderer) -> str:
    """Convert renderer instance class to a stable metric label."""
    class_name = renderer.__class__.__name__.lower().lstrip("_")
    if "reportlab" in class_name:
        return "reportlab"
    if "playwright" in class_name:
        return "playwright"
    return class_name.removesuffix("pdfrenderer")
