"""Helpers for sanitizing user-visible assistant text."""

from __future__ import annotations

import re

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


def strip_leaked_tool_call_markup(text: str | None) -> str:
    """Remove leaked tool-call markup from user-visible text."""

    if not text:
        return ""

    cleaned = _LEAKED_TOOL_CALL_BLOCK_RE.sub("", text)
    cleaned = _ORPHANED_TOOL_CALL_END_RE.sub("", cleaned)
    cleaned = _LEAKED_INTERNAL_STATUS_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()
