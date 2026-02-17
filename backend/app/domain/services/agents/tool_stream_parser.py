"""Tool stream parser — extracts partial content from streaming LLM tool calls.

When the LLM generates a tool call (e.g. file_write), the arguments arrive as
an incrementally growing JSON string.  This module attempts to extract the
"interesting" content field (file content, code, replacement text) from that
partial JSON so the frontend can show a progressive preview.

Two strategies are used:
1. **json.loads()** — fast path when the accumulated JSON is already valid.
2. **Regex fallback** — when the JSON is truncated mid-value, we use a regex
   to pull out the content of a known string field.

The parser is intentionally lenient: it returns ``None`` when it cannot
confidently extract content rather than guessing wrong.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Final

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Function → argument key mapping
# ---------------------------------------------------------------------------
# Each entry maps a tool function name to the argument key that holds the
# "interesting" content the user wants to see streaming.

STREAMABLE_CONTENT_KEYS: Final[dict[str, str]] = {
    # File operations
    "file_write": "content",
    "file_str_replace": "new_str",
    "file_read": "file",  # Show file path being read
    # Code executor
    "code_save_artifact": "content",
    "code_execute_python": "code",
    "code_execute_javascript": "code",
    "code_execute": "code",
    # Shell/Terminal operations (show command being executed)
    "shell_exec": "command",
    "shell_write_to_process": "input",
    # Search operations (show query)
    "info_search_web": "query",
    "web_search": "query",
    "search": "query",
}

# Pre-compiled regexes keyed by field name.
# Pattern: "key" : "value…  (value may be incomplete / unterminated)
# Captures the content after the opening quote, handling JSON escapes.
_FIELD_REGEXES: dict[str, re.Pattern[str]] = {}


def _get_field_regex(field: str) -> re.Pattern[str]:
    """Return (and cache) a regex that captures *field*'s string value."""
    if field not in _FIELD_REGEXES:
        # Match: "field" followed by optional whitespace, colon, optional
        # whitespace, opening double-quote, then capture everything up to
        # an unescaped closing quote OR end-of-string (for truncated JSON).
        _FIELD_REGEXES[field] = re.compile(
            rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\]|\\.)*)"?',
            re.DOTALL,
        )
    return _FIELD_REGEXES[field]


def _unescape_json_string(raw: str) -> str:
    """Unescape a JSON-encoded string value (handles \\n, \\t, \\", \\\\, etc.).

    Falls back to the raw string on any error.
    """
    try:
        return json.loads(f'"{raw}"')
    except (json.JSONDecodeError, ValueError):
        # Best-effort: handle the most common escapes manually.
        return raw.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_streamable_function(function_name: str) -> bool:
    """Return True if *function_name* has a content field we can stream."""
    return function_name in STREAMABLE_CONTENT_KEYS


def content_type_for_function(function_name: str) -> str:
    """Return the content type hint for the frontend viewer."""
    # Code content (execution only — save artifacts are plain text)
    if function_name in (
        "code_execute_python",
        "code_execute_javascript",
        "code_execute",
    ):
        return "code"
    # Terminal/shell content
    if function_name in (
        "shell_exec",
        "shell_write_to_process",
    ):
        return "terminal"
    # Search content
    if function_name in (
        "info_search_web",
        "web_search",
        "search",
    ):
        return "search"
    # File operations — show as plain text (may contain any file content, not just code)
    if function_name in ("file_write", "file_str_replace", "code_save_artifact"):
        return "text"
    return "text"


def extract_partial_content(
    function_name: str,
    partial_json: str,
) -> str | None:
    """Extract the streamable content from *partial_json*.

    Parameters
    ----------
    function_name:
        The tool function name (e.g. ``"file_write"``).
    partial_json:
        The accumulated JSON string of tool call arguments so far.
        May be incomplete / truncated.

    Returns
    -------
    str | None
        The extracted content, or ``None`` if extraction is not possible
        (unknown function, content field not yet present, etc.).
    """
    field = STREAMABLE_CONTENT_KEYS.get(function_name)
    if not field:
        return None

    if not partial_json or len(partial_json) < 5:
        return None

    # --- Fast path: valid JSON -----------------------------------------
    try:
        parsed = json.loads(partial_json)
        value = parsed.get(field)
        if isinstance(value, str):
            return value
        return None
    except (json.JSONDecodeError, ValueError):
        pass

    # --- Regex fallback for truncated JSON -----------------------------
    regex = _get_field_regex(field)
    match = regex.search(partial_json)
    if not match:
        return None

    raw_value = match.group(1)
    if not raw_value:
        return None

    return _unescape_json_string(raw_value)
