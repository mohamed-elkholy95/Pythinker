"""Text manipulation utilities for truncation and formatting.

Provides unified text truncation functionality used across the codebase:
- Simple ellipsis truncation for UI display
- Smart truncation preserving start and end
- Line-based truncation for logs and outputs
- Dictionary value truncation for logging
- Shell output extraction for sandbox command results
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class TruncationStyle(str, Enum):
    """Truncation styles."""

    ELLIPSIS = "ellipsis"  # "text..."
    BRACKETED = "bracketed"  # "text... [N chars]"
    PRESERVE_ENDS = "preserve_ends"  # "start... [N chars] ...end"


@dataclass
class TruncationResult:
    """Result of a truncation operation."""

    content: str
    was_truncated: bool
    original_length: int
    truncated_length: int

    @property
    def chars_removed(self) -> int:
        """Number of characters removed."""
        return self.original_length - self.truncated_length


class TextTruncator:
    """Unified text truncation utility.

    Supports multiple truncation strategies:
    - Simple ellipsis for UI display
    - Smart truncation preserving start and end
    - Line-based truncation for logs and outputs
    - Dictionary value truncation for logging

    Example:
        # Simple truncation
        TextTruncator.truncate("hello world", 8)  # "hello..."

        # Preserve both ends
        TextTruncator.truncate_preserving_ends(long_text, 100)

        # Line-based truncation
        TextTruncator.truncate_lines(output, keep_first=5, keep_last=3)

        # Truncate dict values for logging
        TextTruncator.truncate_for_logging({"key": "very long value..."})
    """

    DEFAULT_ELLIPSIS = "..."
    DEFAULT_BRACKET_FORMAT = "... [{} chars]"

    @staticmethod
    def truncate(
        text: str,
        max_length: int,
        ellipsis: str = "...",
    ) -> str:
        """Simple truncation with ellipsis.

        Args:
            text: Text to truncate
            max_length: Maximum length including ellipsis
            ellipsis: Ellipsis string to append

        Returns:
            Truncated text with ellipsis if needed
        """
        if not text or len(text) <= max_length:
            return text

        # Ensure we have room for ellipsis
        if max_length <= len(ellipsis):
            return ellipsis[:max_length]

        return text[: max_length - len(ellipsis)] + ellipsis

    @staticmethod
    def truncate_with_result(
        text: str,
        max_length: int,
        ellipsis: str = "...",
    ) -> TruncationResult:
        """Truncation returning detailed result.

        Args:
            text: Text to truncate
            max_length: Maximum length including ellipsis
            ellipsis: Ellipsis string to append

        Returns:
            TruncationResult with details
        """
        original_length = len(text) if text else 0
        truncated = TextTruncator.truncate(text, max_length, ellipsis)

        return TruncationResult(
            content=truncated,
            was_truncated=len(truncated) < original_length,
            original_length=original_length,
            truncated_length=len(truncated),
        )

    @staticmethod
    def truncate_preserving_ends(
        text: str,
        max_length: int,
        end_ratio: float = 0.2,
        separator: str = "\n... [{} chars truncated] ...\n",
    ) -> str:
        """Smart truncation preserving content from both ends.

        Keeps the beginning and end of the text, removing content from the middle.
        Useful for showing context from long outputs.

        Args:
            text: Text to truncate
            max_length: Maximum length
            end_ratio: Ratio of max_length to reserve for end (default 0.2 = 20%)
            separator: Format string for truncation marker (uses .format with char count)

        Returns:
            Truncated text with start and end preserved
        """
        if not text or len(text) <= max_length:
            return text

        # Calculate lengths for start and end portions
        chars_removed = len(text) - max_length
        separator_text = separator.format(chars_removed)
        separator_len = len(separator_text)

        # Adjust available space
        available = max_length - separator_len
        if available <= 0:
            return TextTruncator.truncate(text, max_length)

        end_length = int(available * end_ratio)
        start_length = available - end_length

        if start_length <= 0 or end_length <= 0:
            return TextTruncator.truncate(text, max_length)

        return text[:start_length] + separator_text + text[-end_length:]

    @staticmethod
    def truncate_lines(
        text: str,
        max_lines: int | None = None,
        keep_first: int = 5,
        keep_last: int = 3,
    ) -> str:
        """Line-based truncation keeping first and last lines.

        Args:
            text: Text to truncate
            max_lines: Maximum total lines (alternative to keep_first/keep_last)
            keep_first: Number of lines to keep from start
            keep_last: Number of lines to keep from end

        Returns:
            Truncated text with line count indicator
        """
        if not text:
            return text

        lines = text.split("\n")
        total_lines = len(lines)

        if max_lines is not None:
            # Use max_lines to determine keep_first and keep_last
            if total_lines <= max_lines:
                return text
            keep_first = max(1, max_lines * 2 // 3)
            keep_last = max(1, max_lines - keep_first)

        if total_lines <= keep_first + keep_last:
            return text

        omitted = total_lines - keep_first - keep_last
        truncation_marker = f"\n... [{omitted} lines omitted] ...\n"

        first_part = "\n".join(lines[:keep_first])
        last_part = "\n".join(lines[-keep_last:])

        return first_part + truncation_marker + last_part

    @staticmethod
    def truncate_for_logging(
        data: dict[str, Any],
        max_value_length: int = 100,
        max_keys: int | None = None,
    ) -> dict[str, str]:
        """Truncate dictionary values for logging.

        Converts all values to strings and truncates long ones.

        Args:
            data: Dictionary to process
            max_value_length: Maximum length for each value
            max_keys: Maximum number of keys to include

        Returns:
            Dictionary with truncated string values
        """
        if not data:
            return {}

        result: dict[str, str] = {}
        keys = list(data.keys())

        if max_keys is not None:
            keys = keys[:max_keys]

        for key in keys:
            value = data[key]
            str_value = str(value)
            truncated = TextTruncator.truncate(str_value, max_value_length)
            result[key] = truncated

        if max_keys is not None and len(data) > max_keys:
            result["..."] = f"[{len(data) - max_keys} more keys]"

        return result

    @staticmethod
    def truncate_docstring(
        docstring: str,
        max_length: int = 100,
    ) -> str:
        """Extract and truncate first line of docstring.

        Useful for displaying function/class summaries.

        Args:
            docstring: Full docstring
            max_length: Maximum length

        Returns:
            First line of docstring, truncated if needed
        """
        if not docstring:
            return ""

        # Get first non-empty line
        lines = docstring.strip().split("\n")
        first_line = ""
        for line in lines:
            stripped = line.strip()
            if stripped:
                first_line = stripped
                break

        return TextTruncator.truncate(first_line, max_length)


# ── Shell Output Extraction ──────────────────────────────────────────
# Sandbox terminal output wraps command results in [CMD_BEGIN]...[CMD_END]
# markers.  Downstream JSON parsers (Plotly orchestrator, step executor)
# need the raw JSON payload without the shell framing.


def extract_json_from_shell_output(raw: str) -> str:
    """Extract a JSON payload from potentially shell-framed sandbox output.

    The sandbox terminal wraps command execution in ``[CMD_BEGIN]...[CMD_END]``
    markers followed by the command and its stdout.  This function strips the
    framing and returns just the JSON content.

    Strategy (in order):
    1. Fast path — if the input already starts with ``{`` or ``[``, return as-is.
    2. Line scan — find the last line that looks like a JSON object/array.
    3. Substring extraction — locate the first ``{`` to the last ``}``.
    4. Fallback — return the stripped input unchanged.

    Example input::

        [CMD_BEGIN]
        ubuntu@sandbox:~
        [CMD_END] python3 script.py
        {"success": true, "data_points": 8}

    Returns: ``{"success": true, "data_points": 8}``
    """
    if not raw:
        return raw

    stripped = raw.strip()

    # Fast path: already clean JSON (validate to avoid false matches like [CMD_BEGIN])
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return stripped
        except (json.JSONDecodeError, ValueError):
            pass  # Fall through to line scan

    # Line scan: find the last line that is valid JSON
    for line in reversed(stripped.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        if (candidate.startswith("{") and candidate.endswith("}")) or (
            candidate.startswith("[") and candidate.endswith("]")
        ):
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, ValueError):
                continue

    # Substring extraction: first '{' to last '}' (objects)
    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = stripped[brace_start : brace_end + 1]
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            pass

    # Substring extraction: first '[' to last ']' (arrays)
    bracket_start = stripped.find("[")
    bracket_end = stripped.rfind("]")
    if bracket_start != -1 and bracket_end > bracket_start:
        candidate = stripped[bracket_start : bracket_end + 1]
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: return stripped input
    return stripped


# Convenience functions for backward compatibility
def truncate(text: str, max_length: int = 60) -> str:
    """Simple truncate with ellipsis (backward compatible)."""
    return TextTruncator.truncate(text, max_length)


def truncate_output(content: str, max_length: int, preserve_end: bool = True) -> str:
    """Truncate output preserving structure (backward compatible)."""
    if preserve_end:
        return TextTruncator.truncate_preserving_ends(content, max_length)
    return TextTruncator.truncate(content, max_length)


def is_report_like_content(content: str) -> bool:
    """Return True when content looks like a structured report.

    Detects markdown headings, bold headers, numbered sections, or
    citation-heavy long-form content.  Used by OutputVerifier and
    ResponseGenerator to gate report-specific quality checks.
    """
    if not content:
        return False

    heading_count = len(re.findall(r"^#{1,4}\s+.+", content, re.MULTILINE))
    if heading_count >= 2:
        return True

    bold_headers = len(re.findall(r"\*\*[^*]+:\*\*", content))
    if bold_headers >= 2:
        return True

    numbered_sections = len(re.findall(r"^\d+\.\s+[A-Z]", content, re.MULTILINE))
    if numbered_sections >= 2:
        return True

    citation_count = len(re.findall(r"\[\d+\]", content))
    return bool(citation_count >= 3 and len(content) > 1000)
