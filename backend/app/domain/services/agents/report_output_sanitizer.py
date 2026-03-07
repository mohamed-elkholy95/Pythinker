"""Utilities for normalizing final report presentation."""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6}\s+)(.+)$")
_BLOCKQUOTE_RE = re.compile(r"^(>\s+)(.+)$")
_DECORATIVE_PREFIXES: tuple[str, ...] = (
    "⚠️",
    "⚠",
    "🔬",
    "📊",
    "🔍",
    "📎",
    "🎯",
    "💡",
    "🏆",
)


def sanitize_report_output(content: str) -> str:
    """Remove decorative emoji prefixes from report headings and notices."""
    if not content:
        return content

    lines = content.split("\n")
    output: list[str] = []
    in_code_fence = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            output.append(line)
            continue

        if in_code_fence:
            output.append(line)
            continue

        output.append(_sanitize_line(line))

    return "\n".join(output)


def _sanitize_line(line: str) -> str:
    heading_match = _HEADING_RE.match(line)
    if heading_match:
        prefix, rest = heading_match.groups()
        return f"{prefix}{_strip_decorative_prefixes(rest)}"

    blockquote_match = _BLOCKQUOTE_RE.match(line)
    if blockquote_match:
        prefix, rest = blockquote_match.groups()
        return f"{prefix}{_strip_decorative_prefixes(rest)}"

    return line


def _strip_decorative_prefixes(text: str) -> str:
    cleaned = text.lstrip()

    while True:
        for prefix in _DECORATIVE_PREFIXES:
            if cleaned.startswith(f"{prefix} "):
                cleaned = cleaned[len(prefix) :].lstrip()
                break
        else:
            return cleaned
