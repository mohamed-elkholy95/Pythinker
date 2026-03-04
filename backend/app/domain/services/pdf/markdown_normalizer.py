"""Normalize report markdown for PDF rendering with stable citation/reference mapping."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models.source_citation import SourceCitation

_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
_REFERENCES_HEADING_RE = re.compile(r"^#{1,4}\s*(references?|sources?|bibliography|citations?)\s*$", re.IGNORECASE)
_BOLD_REFERENCES_RE = re.compile(r"^\*{2}(references?|sources?|bibliography|citations?):?\*{2}\s*$", re.IGNORECASE)
_INLINE_CITATION_RE = re.compile(r"(?<!\^)\[(\d{1,3})\](?!\()(?!:\s)")
_PUNCTUATION_AFTER_CITATIONS_RE = re.compile(r" *((?:\[\d{1,3}\]\s*)+)([.!?,;])\s*$")
_ORDERED_REF_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_BRACKET_REF_RE = re.compile(r"^\s*\[(\d+)\]\s+(.+)$")
_LINK_REF_DEF_RE = re.compile(r"^\s*\[(\d+)\]:\s+(.+)$")
_UNORDERED_REF_RE = re.compile(r"^\s*[-*+]\s+(.+)$")


@dataclass(frozen=True)
class NormalizedMarkdownReport:
    """Normalized markdown plus citation/reference diagnostics."""

    markdown: str
    citation_numbers: list[int]
    unresolved_citations: list[int]
    reference_count: int


def normalize_markdown_for_pdf(content: str, sources: list[SourceCitation] | None = None) -> NormalizedMarkdownReport:
    """Normalize markdown and enforce a deterministic references section.

    Rules:
    - Linkify inline citations as markdown links: `[N](#ref-N)`.
    - Keep citations out of fenced code blocks.
    - Build references from structured sources when available.
    - Add placeholders for unresolved citation numbers to avoid mismatches.
    """
    normalized_content = _normalize_layout(content)
    body, existing_refs = _split_references_section(normalized_content)
    linked_body, citation_numbers = _linkify_inline_citations(body)
    references_block, unresolved = _build_references_block(citation_numbers, sources or [], existing_refs)

    final_markdown = linked_body.strip()
    if references_block:
        if final_markdown:
            final_markdown = f"{final_markdown}\n\n## References\n\n{references_block}".strip()
        else:
            final_markdown = f"## References\n\n{references_block}".strip()

    reference_count = len(references_block.splitlines()) if references_block else 0
    return NormalizedMarkdownReport(
        markdown=final_markdown,
        citation_numbers=citation_numbers,
        unresolved_citations=unresolved,
        reference_count=reference_count,
    )


def _normalize_layout(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _EXCESS_BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _split_references_section(markdown: str) -> tuple[str, str]:
    if not markdown:
        return "", ""

    lines = markdown.split("\n")
    in_code_fence = False
    split_index = -1

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        if _REFERENCES_HEADING_RE.match(stripped) or _BOLD_REFERENCES_RE.match(stripped):
            split_index = idx
            break

    if split_index < 0:
        return markdown, ""

    body = "\n".join(lines[:split_index]).strip()
    references = "\n".join(lines[split_index + 1 :]).strip()
    return body, references


def _linkify_inline_citations(markdown: str) -> tuple[str, list[int]]:
    if not markdown:
        return "", []

    lines = markdown.split("\n")
    in_code_fence = False
    seen: set[int] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            output.append(line)
            continue

        if in_code_fence:
            output.append(line)
            continue

        punct_normalized = _PUNCTUATION_AFTER_CITATIONS_RE.sub(
            lambda m: f"{m.group(2)}{m.group(1).rstrip()}",
            line,
        )

        def _replace(match: re.Match[str]) -> str:
            number = int(match.group(1))
            seen.add(number)
            return f"[{number}](#ref-{number})"

        output.append(_INLINE_CITATION_RE.sub(_replace, punct_normalized))

    return "\n".join(output).strip(), sorted(seen)


def _build_references_block(
    citation_numbers: list[int],
    sources: list[SourceCitation],
    existing_references: str,
) -> tuple[str, list[int]]:
    parsed_existing = _parse_existing_references(existing_references)

    if sources:
        entries = {index: _format_source_reference(source) for index, source in enumerate(sources, start=1)}
        # Preserve explicit in-document references for citation numbers not covered
        # by structured sources to avoid artificial "Unresolved citation" rows.
        for number, value in parsed_existing.items():
            entries.setdefault(number, value)
    else:
        entries = parsed_existing

    max_citation = max(citation_numbers) if citation_numbers else 0
    max_entry = max(entries) if entries else 0
    max_number = max(max_citation, max_entry)
    if max_number <= 0:
        return "", []

    unresolved: list[int] = []
    lines: list[str] = []
    for number in range(1, max_number + 1):
        entry = entries.get(number)
        if not entry:
            unresolved.append(number)
            entry = "Unresolved citation"
        lines.append(f"{number}. {entry}")

    return "\n".join(lines), unresolved


def _format_source_reference(source: SourceCitation) -> str:
    title = source.title.strip() if source.title else ""
    url = source.url.strip()
    if title:
        return f"[{title}]({url})"
    return url


def _parse_existing_references(references_text: str) -> dict[int, str]:
    if not references_text:
        return {}

    entries: dict[int, str] = {}
    next_unordered = 1
    last_number: int | None = None

    for raw_line in references_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        ordered_match = _ORDERED_REF_RE.match(line)
        if ordered_match:
            number = int(ordered_match.group(1))
            entries[number] = ordered_match.group(2).strip()
            last_number = number
            next_unordered = max(next_unordered, number + 1)
            continue

        bracket_match = _BRACKET_REF_RE.match(line)
        if bracket_match:
            number = int(bracket_match.group(1))
            entries[number] = bracket_match.group(2).strip()
            last_number = number
            next_unordered = max(next_unordered, number + 1)
            continue

        link_ref_match = _LINK_REF_DEF_RE.match(line)
        if link_ref_match:
            number = int(link_ref_match.group(1))
            entries[number] = link_ref_match.group(2).strip()
            last_number = number
            next_unordered = max(next_unordered, number + 1)
            continue

        unordered_match = _UNORDERED_REF_RE.match(line)
        if unordered_match:
            number = next_unordered
            entries[number] = unordered_match.group(1).strip()
            last_number = number
            next_unordered += 1
            continue

        if last_number is not None:
            entries[last_number] = f"{entries[last_number]} {line}".strip()

    return entries
