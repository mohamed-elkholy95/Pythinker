"""Markdown to ReportLab conversion utilities for Telegram PDF delivery."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable
from reportlab.platypus.tableofcontents import TableOfContents

from app.domain.models.source_citation import SourceCitation

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
_ORDERED_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?[\s:\-]+\|[\s:\-|]+\|?\s*$")
_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_REFERENCES_HEADING_RE = re.compile(r"(?mi)^#{1,6}\s*(references?|sources?|bibliography|citations?)\s*$")

_FONT_PATH_CANDIDATES: dict[str, tuple[Path, ...]] = {
    "DejaVuSans": (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/local/share/fonts/DejaVuSans.ttf"),
        Path("/Library/Fonts/DejaVu Sans.ttf"),
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
    ),
    "LiberationSans": (
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/Library/Fonts/LiberationSans-Regular.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ),
    "FreeSans": (
        Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        Path("/usr/local/share/fonts/FreeSans.ttf"),
    ),
    "Unifont": (
        Path("/usr/share/fonts/opentype/unifont/unifont.otf"),
        Path("/usr/local/share/fonts/unifont.otf"),
    ),
}
_FONT_FALLBACK_ORDER: tuple[str, ...] = ("DejaVuSans", "LiberationSans", "FreeSans", "Unifont")
_FONT_KEY_ALIASES: dict[str, str] = {
    "dejavusans": "DejaVuSans",
    "liberationsans": "LiberationSans",
    "freesans": "FreeSans",
    "unifont": "Unifont",
}
_FONT_FALLBACK_WARNED: set[tuple[str, str]] = set()


def _normalize_font_key(name: str) -> str:
    return re.sub(r"[\s_-]+", "", name).lower()


def _font_search_order(preferred_font: str) -> list[str]:
    requested = preferred_font.strip() or "DejaVuSans"
    canonical = _FONT_KEY_ALIASES.get(_normalize_font_key(requested), requested)
    order = [canonical]
    for fallback in _FONT_FALLBACK_ORDER:
        if fallback not in order:
            order.append(fallback)
    return order


def _font_paths(font_name: str) -> tuple[Path, ...]:
    known = _FONT_PATH_CANDIDATES.get(font_name)
    if known:
        return known
    direct_path = Path(font_name)
    if direct_path.suffix.lower() in {".ttf", ".ttc", ".otf"}:
        return (direct_path,)
    return ()


def _log_fallback_once(requested: str, chosen: str, path: Path | None = None) -> None:
    key = (requested, chosen)
    if key in _FONT_FALLBACK_WARNED:
        return
    _FONT_FALLBACK_WARNED.add(key)
    if path is not None:
        logger.warning("Unicode font %s not found, using fallback %s (%s)", requested, chosen, path)
        return
    logger.warning("Unicode font %s not found, using fallback %s", requested, chosen)


def register_unicode_font(preferred_font: str = "DejaVuSans") -> str:
    """Register a Unicode-capable TTF font and return the chosen font name."""
    requested = preferred_font.strip() or "DejaVuSans"
    for font_name in _font_search_order(requested):
        if font_name in pdfmetrics.getRegisteredFontNames():
            if font_name != requested:
                _log_fallback_once(requested, font_name)
            return font_name

        for path in _font_paths(font_name):
            if not path.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
                if font_name != requested:
                    _log_fallback_once(requested, font_name, path)
                return font_name
            except Exception:
                logger.debug("Failed to register font %s from %s", font_name, path, exc_info=True)

    logger.warning("Unicode font %s not found, falling back to Helvetica", requested)
    return "Helvetica"


def markdown_to_flowables(content: str, *, styles: StyleSheet1 | None = None) -> list[Flowable]:
    """Convert Markdown content into ReportLab flowables."""
    safe_content = content or ""
    sheet = styles or _build_styles()

    flowables: list[Flowable] = []
    paragraph_lines: list[str] = []
    lines = safe_content.splitlines()
    idx = 0

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        text = _inline_markdown_to_xml(" ".join(line.strip() for line in paragraph_lines if line.strip()))
        if text:
            flowables.append(Paragraph(text, sheet["BodyText"]))
            flowables.append(Spacer(1, 6))
        paragraph_lines.clear()

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            idx += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            idx += 1
            code_lines: list[str] = []
            while idx < len(lines) and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            # consume trailing ``` when present
            if idx < len(lines):
                idx += 1
            flowables.append(Preformatted("\n".join(code_lines), sheet["Code"]))
            flowables.append(Spacer(1, 6))
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_paragraph()
            level = min(len(heading_match.group(1)), 3)
            text = _inline_markdown_to_xml(heading_match.group(2).strip())
            flowables.append(Paragraph(text, sheet[f"Heading{level}"]))
            flowables.append(Spacer(1, 6))
            idx += 1
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            flowables.append(HRFlowable(color=colors.HexColor("#C8CED8"), thickness=1))
            flowables.append(Spacer(1, 6))
            idx += 1
            continue

        if _looks_like_table(lines, idx):
            flush_paragraph()
            rows, consumed = _parse_table(lines[idx:], sheet)
            table = Table(rows, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C8CED8")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("FONTNAME", (0, 0), (-1, -1), sheet["BodyText"].fontName),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ]
                )
            )
            flowables.append(table)
            flowables.append(Spacer(1, 6))
            idx += consumed
            continue

        bullet_match = _BULLET_RE.match(line)
        ordered_match = _ORDERED_RE.match(line)
        if bullet_match or ordered_match:
            flush_paragraph()
            list_flowable, consumed = _parse_list(lines[idx:], sheet)
            flowables.append(list_flowable)
            flowables.append(Spacer(1, 6))
            idx += consumed
            continue

        paragraph_lines.append(line)
        idx += 1

    flush_paragraph()
    return flowables


def build_pdf_bytes(
    *,
    title: str,
    content: str,
    sources: list[SourceCitation] | None = None,
    include_toc: bool = True,
    toc_min_sections: int = 3,
    author: str = "Pythinker AI Agent",
    subject: str | None = None,
    creator: str = "Pythinker / ReportLab",
    preferred_font: str = "DejaVuSans",
) -> bytes:
    """Render Markdown content into PDF bytes with metadata and optional TOC."""
    font_name = register_unicode_font(preferred_font)
    styles = _build_styles(font_name=font_name)
    output = BytesIO()
    safe_title = _sanitize_pdf_title(title)

    heading_count = _count_markdown_headings(content)
    should_include_toc = include_toc and heading_count >= toc_min_sections
    effective_subject = subject or (content[:100].strip() if content else "Report")

    doc = _TocDocTemplate(
        output,
        pagesize=A4,
        title=safe_title,
        author=author,
        subject=effective_subject,
        creator=creator,
    )

    story: list[Flowable] = [
        Paragraph(_inline_markdown_to_xml(safe_title), styles["Title"]),
        Spacer(1, 12),
    ]

    if should_include_toc:
        toc = TableOfContents()
        toc.levelStyles = [
            ParagraphStyle(name="TOCLevel1", parent=styles["BodyText"], leftIndent=10, firstLineIndent=-6),
            ParagraphStyle(name="TOCLevel2", parent=styles["BodyText"], leftIndent=22, firstLineIndent=-6),
            ParagraphStyle(name="TOCLevel3", parent=styles["BodyText"], leftIndent=34, firstLineIndent=-6),
        ]
        story.append(Paragraph("Table of Contents", styles["Heading2"]))
        story.append(Spacer(1, 6))
        story.append(toc)
        story.append(PageBreak())

    story.extend(markdown_to_flowables(content, styles=styles))
    include_sources = not _has_references_heading(content)
    story.extend(_sources_to_flowables(sources or [], styles, include_heading=include_sources))

    doc.multiBuild(story)
    output.seek(0)
    return output.getvalue()


class _TocDocTemplate(BaseDocTemplate):
    """Doc template that registers heading flowables for table-of-contents."""

    def __init__(self, *args, title: str, author: str, subject: str, creator: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._title = title
        self._author = author
        self._subject = subject
        self._creator = creator
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="default", frames=[frame], onPage=self._on_page)])

    def _on_page(self, canvas, _doc) -> None:
        canvas.setTitle(self._title)
        canvas.setAuthor(self._author)
        canvas.setSubject(self._subject)
        canvas.setCreator(self._creator)

    def afterFlowable(self, flowable: Flowable) -> None:  # noqa: N802
        if not isinstance(flowable, Paragraph):
            return
        style_name = getattr(flowable.style, "name", "")
        if not style_name.startswith("Heading"):
            return
        try:
            level = max(0, int(style_name.replace("Heading", "")) - 1)
        except ValueError:
            return
        self.notify("TOCEntry", (level, flowable.getPlainText(), self.page))


def _sources_to_flowables(
    sources: Iterable[SourceCitation],
    styles: StyleSheet1,
    *,
    include_heading: bool = True,
) -> list[Flowable]:
    items = list(sources)
    if not items:
        return []
    if not include_heading:
        return []

    flowables: list[Flowable] = [PageBreak(), Paragraph("References", styles["Heading2"]), Spacer(1, 6)]
    for idx, source in enumerate(items, start=1):
        line = f'[{idx}] <b>{_escape_xml(source.title)}</b> — <a href="{_escape_xml(source.url)}">{_escape_xml(source.url)}</a>'
        flowables.append(Paragraph(line, styles["BodyText"]))
        if source.snippet:
            flowables.append(Paragraph(_escape_xml(source.snippet), styles["BodyText"]))
        flowables.append(Spacer(1, 4))
    return flowables


def _build_styles(*, font_name: str | None = None) -> StyleSheet1:
    resolved_font = font_name or register_unicode_font("DejaVuSans")
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = resolved_font
    styles["BodyText"].fontName = resolved_font
    styles["Title"].fontName = resolved_font
    styles["Heading1"].fontName = resolved_font
    styles["Heading2"].fontName = resolved_font
    styles["Heading3"].fontName = resolved_font
    styles["Heading1"].spaceAfter = 8
    styles["Heading2"].spaceAfter = 6
    styles["Heading3"].spaceAfter = 4
    code_style = ParagraphStyle(
        name="Code",
        parent=styles["BodyText"],
        fontName="Courier",
        fontSize=9,
        leading=11,
        backColor=colors.HexColor("#F5F7FA"),
        leftIndent=6,
        rightIndent=6,
        borderPadding=4,
    )
    if "Code" in styles.byName:
        styles.byName["Code"] = code_style
    else:
        styles.add(code_style)
    return styles


def _parse_list(lines: list[str], styles: StyleSheet1) -> tuple[ListFlowable, int]:
    items: list[ListItem] = []
    consumed = 0
    ordered = False

    for line in lines:
        bullet_match = _BULLET_RE.match(line)
        ordered_match = _ORDERED_RE.match(line)
        if not bullet_match and not ordered_match:
            break
        consumed += 1
        ordered = ordered or bool(ordered_match)
        text = bullet_match.group(1) if bullet_match else ordered_match.group(2)
        paragraph = Paragraph(_inline_markdown_to_xml(text.strip()), styles["BodyText"])
        items.append(ListItem(paragraph))

    list_flowable = ListFlowable(
        items,
        bulletType="1" if ordered else "bullet",
        start="1",
        leftIndent=14,
        bulletFontName=styles["BodyText"].fontName,
    )
    return list_flowable, consumed


def _looks_like_table(lines: list[str], idx: int) -> bool:
    if idx + 1 >= len(lines):
        return False
    current = lines[idx]
    divider = lines[idx + 1]
    return "|" in current and _TABLE_DIVIDER_RE.match(divider or "") is not None


def _parse_table(lines: list[str], styles: StyleSheet1) -> tuple[list[list[Paragraph]], int]:
    rows: list[list[Paragraph]] = []
    consumed = 0
    for line in lines:
        if "|" not in line:
            break
        if _TABLE_DIVIDER_RE.match(line):
            consumed += 1
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append([Paragraph(_inline_markdown_to_xml(cell), styles["BodyText"]) for cell in cells])
        consumed += 1

    if not rows:
        return [[Paragraph("", styles["BodyText"])]], max(consumed, 1)
    # Normalize row lengths for ReportLab table rendering.
    max_cols = max(len(row) for row in rows)
    normalized_rows = [row + [Paragraph("", styles["BodyText"])] * (max_cols - len(row)) for row in rows]
    return normalized_rows, consumed


def _inline_markdown_to_xml(text: str) -> str:
    escaped = _escape_xml(text)
    escaped = _INLINE_LINK_RE.sub(r'<a href="\2">\1</a>', escaped)
    escaped = _INLINE_BOLD_RE.sub(r"<b>\1</b>", escaped)
    escaped = _INLINE_ITALIC_RE.sub(r"<i>\1</i>", escaped)
    return _INLINE_CODE_RE.sub(r'<font face="Courier">\1</font>', escaped)


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _count_markdown_headings(content: str) -> int:
    return sum(1 for line in content.splitlines() if _HEADING_RE.match(line))


def _has_references_heading(content: str) -> bool:
    return _REFERENCES_HEADING_RE.search(content or "") is not None


def _sanitize_pdf_title(title: str) -> str:
    text = (title or "").strip()
    if not text:
        return "Report"

    filtered_chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        # Remove symbol/other and surrogate characters (common emoji buckets)
        if category in {"So", "Cs"}:
            continue
        filtered_chars.append(char)

    sanitized = "".join(filtered_chars).strip()
    return sanitized or "Report"
