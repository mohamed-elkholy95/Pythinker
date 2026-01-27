from __future__ import annotations

from difflib import unified_diff
from typing import Optional


def build_unified_diff(
    before: Optional[str],
    after: Optional[str],
    path: str,
    context_lines: int = 3,
    max_chars: int = 20000,
) -> str:
    """Build a unified diff string for two versions of content."""
    before_text = before or ""
    after_text = after or ""
    if before_text == after_text:
        return ""

    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)

    diff_iter = unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=context_lines,
    )
    diff_text = "".join(diff_iter)

    if max_chars and len(diff_text) > max_chars:
        return diff_text[:max_chars] + "\n... (diff truncated)"
    return diff_text
