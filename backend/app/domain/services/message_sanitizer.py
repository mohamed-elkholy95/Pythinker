"""Helpers for sanitizing user-visible assistant text."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_LEAKED_TOOL_CALL_BLOCK_RE = re.compile(
    r"\s*<(?:tool_call|function_call)\b[^>]*>.*?(?:</(?:tool_call|function_call)>|$)",
    flags=re.IGNORECASE | re.DOTALL,
)
_ORPHANED_TOOL_CALL_END_RE = re.compile(r"</(?:tool_call|function_call)>", flags=re.IGNORECASE)
_LEAKED_INTERNAL_STATUS_RE = re.compile(
    r"\s*(?:\*\*)?\[?\s*("
    r"Sandbox Browser|SYSTEM NOTE|CONTEXT PRESSURE|FOCUSED(?: CONTENT)?|AUTO-TERMINATED|Audit failure|"
    r"Step time|INFORMATIONAL|SYSTEM|Tool result|Attempted to call|Previously called"
    r"):\s*(?:"
    r"(?:Navigating to|Connecting to|Opening|Loading|Visiting|Reading|Clicking|Typing|Searching|Fetching|Inspecting|Reloading)\b[^\n]*"
    r"|[^\n]*"
    r")",
    flags=re.IGNORECASE,
)
_RAW_TOOL_PAYLOAD_KEYS = (
    "tool",
    "tool_call",
    "function",
    "function_call",
    "query",
    "arguments",
    "params",
    "top_n",
    "search_depth",
    "date_range",
    "url",
    "task",
)

# Word-boundary regex that matches any payload key as a standalone word.
# Prevents false positives where "url" matches inside "furniture" or
# "task" matches inside "multitasking".
_RAW_TOOL_PAYLOAD_KEY_WORD_RE = re.compile(
    r"\b(?:tool_call|function_call|search_depth|date_range|tool|function|query|arguments|params|top_n|url|task)\b",
    flags=re.IGNORECASE,
)

# Structural check: a JSON key followed by a colon, optionally quoted.
# This detects actual JSON key-value structure regardless of surrounding prose.
_RAW_TOOL_KEY_COLON_RE = re.compile(
    r"""["']?(?:tool_call|function_call|search_depth|date_range|tool|function|query|arguments|params|top_n|url|task)["']?\s*:""",
    flags=re.IGNORECASE,
)


def strip_leaked_tool_call_markup(text: str | None) -> str:
    """Remove leaked tool-call markup from user-visible text."""

    if not text:
        return ""

    cleaned = _LEAKED_TOOL_CALL_BLOCK_RE.sub("", text)
    cleaned = _ORPHANED_TOOL_CALL_END_RE.sub("", cleaned)
    cleaned = _LEAKED_INTERNAL_STATUS_RE.sub("", cleaned)
    cleaned = _strip_trailing_raw_tool_payload(cleaned)
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _count_word_boundary_key_matches(text: str) -> int:
    """Count how many payload keys appear as standalone words in *text*."""
    return len(_RAW_TOOL_PAYLOAD_KEY_WORD_RE.findall(text))


def _strip_trailing_raw_tool_payload(text: str) -> str:
    """Remove trailing bare JSON fragments that look like leaked tool arguments.

    The heuristic requires **multiple** word-boundary key matches before
    stripping a JSON-character-only tail.  This prevents false positives
    where a single word like "furniture" (contains "url") or "multitasking"
    (contains "task") would trigger removal of legitimate prose.

    A **single** key match is sufficient when the tail also contains a
    structural JSON ``key:`` pattern, because that strongly signals actual
    JSON rather than coincidental word overlap.
    """

    for opener in ("{", "["):
        start = text.rfind(opener)
        if start == -1:
            continue

        tail = text[start:].strip()
        if len(tail) < 8:
            continue

        key_count = _count_word_boundary_key_matches(tail)
        if key_count == 0:
            continue

        # Branch 1: entire tail is JSON-like characters AND multiple keys matched.
        # Multiple word-boundary matches make coincidence extremely unlikely.
        if key_count >= 2 and re.fullmatch(
            r'[\s\{\}\[\]":,A-Za-z0-9_\-./?=&%+!@#$%^*<>\\]+',
            tail,
        ):
            logger.debug("Stripped trailing raw tool payload (multi-key fullmatch): %.80s…", tail)
            return text[:start].rstrip()

        # Branch 2: tail contains a structural JSON key-colon pattern.
        # A single key match + actual JSON structure is a strong signal.
        if _RAW_TOOL_KEY_COLON_RE.search(tail):
            logger.debug("Stripped trailing raw tool payload (key-colon structure): %.80s…", tail)
            return text[:start].rstrip()

    return text
