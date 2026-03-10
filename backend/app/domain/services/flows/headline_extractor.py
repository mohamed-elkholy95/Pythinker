"""Extract a one-line headline from a tool result for partial output display."""

from __future__ import annotations

import re

_MAX_HEADLINE_LEN = 120


def extract_headline(tool_result: str, tool_name: str = "") -> str:
    """Return a <= 120 char headline summarising the tool result.

    Priority order:
    1. Search results — extract count and first line
    2. Browser navigation — extract page title
    3. Default — first non-empty line, truncated to 120 chars

    Args:
        tool_result: Raw text output from a tool execution.
        tool_name: Optional name of the tool for fallback messages.

    Returns:
        A non-empty headline string of at most 120 characters.
    """
    if not tool_result.strip():
        return f"{tool_name or 'Tool'} returned no result"

    # Search results — extract count and query from first line
    count_match = re.search(r"Found (\d+) results?\b", tool_result)
    if count_match:
        first_line = tool_result.split("\n")[0].strip()
        return first_line[:_MAX_HEADLINE_LEN]

    # Browser — extract page title
    title_match = re.search(r"(?:Page title|Title):\s*(.+)", tool_result)
    if title_match:
        return f"Visited: {title_match.group(1).strip()}"[:_MAX_HEADLINE_LEN]

    # Default — first non-empty line, truncated
    for line in tool_result.split("\n"):
        line = line.strip()
        if line:
            if len(line) > _MAX_HEADLINE_LEN:
                return line[: _MAX_HEADLINE_LEN - 3] + "..."
            return line

    return f"{tool_name or 'Tool'} completed"
