"""Playwright-powered PDF renderer for modal-parity report output."""

from __future__ import annotations

import base64
import contextlib
import logging
import re
from datetime import UTC
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from playwright.async_api import async_playwright

from app.core import prometheus_metrics as pm
from app.domain.services.pdf.markdown_normalizer import normalize_markdown_for_pdf
from app.domain.services.pdf.mermaid_preprocessor import MermaidPreprocessor
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.pdf.pdf_renderer import PdfReportRenderer

logger = logging.getLogger(__name__)

_REFERENCES_HEADING_RE = re.compile(r"^(references?|sources?|bibliography|citations?)$", re.IGNORECASE)
_BRACKET_REFERENCE_RE = re.compile(r"\[(\d{1,3})\]")
_INLINE_CITATION_LABEL_RE = re.compile(r"^\d{1,3}$")
_GITHUB_ALERT_RE = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$", re.IGNORECASE | re.DOTALL)
_ALERT_TITLES = {
    "note": "Note",
    "tip": "Tip",
    "important": "Important",
    "warning": "Warning",
    "caution": "Caution",
}


class PlaywrightPdfRenderer(PdfReportRenderer):
    """Render report PDFs through Chromium for CSS-accurate layout parity."""

    def __init__(
        self,
        *,
        timeout_ms: int = 20_000,
        fallback_renderer: PdfReportRenderer | None = None,
        mermaid: MermaidPreprocessor | None = None,
    ) -> None:
        self._timeout_ms = max(1_000, int(timeout_ms))
        self._fallback_renderer = fallback_renderer
        self._mermaid = mermaid

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
        markdown_content = payload.markdown_content
        if self._mermaid is not None:
            markdown_content, mermaid_images = await self._mermaid.preprocess_markdown(markdown_content)
            markdown_content = _replace_mermaid_placeholders_with_markdown_images(markdown_content, mermaid_images)

        normalized = normalize_markdown_for_pdf(markdown_content, payload.sources)
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
        body_html = _decorate_inline_citation_links(body_html)
        body_html = _decorate_reference_ids(body_html)
        body_html = _decorate_alert_blockquotes(body_html)

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


def _replace_mermaid_placeholders_with_markdown_images(content: str, mermaid_images: dict[str, bytes]) -> str:
    """Replace Mermaid placeholders with inline PNG markdown images."""
    rendered = content
    for key, png_bytes in mermaid_images.items():
        encoded = base64.b64encode(png_bytes).decode("ascii")
        rendered = rendered.replace(f"<!--MERMAID:{key}-->", f"![Mermaid diagram](data:image/png;base64,{encoded})")
    return rendered


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
    anchored_numbers: set[int] = set()
    sibling = references_heading.find_next_sibling()
    while sibling is not None:
        if sibling.name in {"h1", "h2", "h3", "h4"}:
            break
        if sibling.name in {"ol", "ul"}:
            for item in sibling.find_all("li", recursive=False):
                item["id"] = f"ref-{number}"
                anchored_numbers.add(number)
                number += 1
        else:
            _decorate_bracket_reference_ids(soup, sibling, anchored_numbers)
        sibling = sibling.find_next_sibling()

    return str(soup)


def _decorate_inline_citation_links(html: str) -> str:
    """Render numeric citation links with visible markdown-style brackets."""
    soup = BeautifulSoup(html, "html.parser")

    for anchor in soup.find_all("a"):
        label = anchor.get_text(" ", strip=True)
        if not _INLINE_CITATION_LABEL_RE.fullmatch(label):
            continue
        anchor.string = f"[{label}]"

    return str(soup)


def _decorate_alert_blockquotes(html: str) -> str:
    """Convert GitHub alert blockquotes into styled PDF callouts."""
    soup = BeautifulSoup(html, "html.parser")

    for blockquote in soup.find_all("blockquote"):
        paragraphs = blockquote.find_all("p", recursive=False)
        if not paragraphs:
            continue

        first_paragraph = paragraphs[0]
        first_text = first_paragraph.get_text("\n", strip=False).lstrip()
        match = _GITHUB_ALERT_RE.match(first_text)
        if not match:
            continue

        alert_kind = match.group(1).lower()
        blockquote["class"] = [*blockquote.get("class", []), "alert", f"alert-{alert_kind}"]

        title_node = soup.new_tag("p")
        title_node["class"] = ["alert-title"]
        title_node.string = _ALERT_TITLES.get(alert_kind, alert_kind.title())
        blockquote.insert(0, title_node)

        _strip_alert_marker(first_paragraph)
        if not first_paragraph.get_text(" ", strip=True) and not first_paragraph.find(True):
            first_paragraph.decompose()

    return str(soup)


def _decorate_bracket_reference_ids(
    soup: BeautifulSoup,
    node,
    anchored_numbers: set[int],
) -> None:
    """Attach anchors to bracket-style references like ``[1] Source``."""
    for text_node in list(node.find_all(string=True)):
        parent = text_node.parent
        if parent is not None and parent.name in {"code", "pre", "a"}:
            continue

        text = str(text_node)
        if "[" not in text:
            continue

        matches = list(_BRACKET_REFERENCE_RE.finditer(text))
        if not matches:
            continue

        cursor = 0
        replacement_parts: list[object] = []
        for match in matches:
            if match.start() > cursor:
                replacement_parts.append(text[cursor : match.start()])

            number = int(match.group(1))
            marker = match.group(0)
            if number not in anchored_numbers:
                marker_node = soup.new_tag("span")
                marker_node["id"] = f"ref-{number}"
                marker_node.string = marker
                replacement_parts.append(marker_node)
                anchored_numbers.add(number)
            else:
                replacement_parts.append(marker)
            cursor = match.end()

        if cursor < len(text):
            replacement_parts.append(text[cursor:])

        for part in replacement_parts:
            text_node.insert_before(part)
        text_node.extract()


def _strip_alert_marker(paragraph) -> None:
    """Remove the leading GitHub alert marker from a paragraph in-place."""
    for child in list(paragraph.contents):
        if not isinstance(child, NavigableString):
            if str(child).strip():
                break
            continue

        raw_text = str(child)
        stripped = raw_text.lstrip()
        if not stripped:
            continue

        match = _GITHUB_ALERT_RE.match(stripped)
        if not match:
            break

        leading = raw_text[: len(raw_text) - len(stripped)]
        replacement = match.group(2)
        if replacement:
            child.replace_with(f"{leading}{replacement}")
        else:
            child.extract()
        return


def _renderer_label(renderer: PdfReportRenderer) -> str:
    """Convert renderer instance class to a stable metric label."""
    class_name = renderer.__class__.__name__.lower().lstrip("_")
    if "reportlab" in class_name:
        return "reportlab"
    if "playwright" in class_name:
        return "playwright"
    return class_name.removesuffix("pdfrenderer")
