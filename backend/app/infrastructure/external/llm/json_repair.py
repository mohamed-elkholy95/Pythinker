"""Universal JSON extraction and repair for LLM responses.

LLMs frequently return JSON in non-standard ways:
- Wrapped in markdown code fences (```json ... ```)
- Prefixed with prose ("Here is the JSON: {...}")
- Truncated mid-object (streaming cutoff, token limit)
- Single-quoted strings instead of double quotes
- Trailing commas before closing braces
- JavaScript-style comments (//, /* */)
- Numeric keys without quotes

This module provides a universal parser/repairer that works for any provider
(OpenAI, Anthropic, GLM, Ollama, etc.) with a consistent interface.
"""

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────── Public API ───────────────────────────


def extract_json_text(text: str) -> str | None:
    """Extract JSON string from LLM response text.

    Handles:
    - Bare JSON (just returns as-is)
    - Markdown code fences: ```json ... ``` or ``` ... ```
    - Inline prose with JSON embedded: "Here is the result: {...}"
    - Multiple JSON objects (returns the first/largest valid one)

    Args:
        text: Raw LLM response text

    Returns:
        Raw JSON string, or None if no JSON found
    """
    if not text or not text.strip():
        return None

    stripped = text.strip()

    # Fast path: already valid JSON
    if _is_valid_json(stripped):
        return stripped

    # 1. Try markdown code fences (most common LLM format)
    #    ```json {...} ``` or ``` {...} ```
    fence_match = re.search(
        r"```(?:json|JSON)?\s*\n?([\s\S]*?)\n?```",
        stripped,
        re.IGNORECASE,
    )
    if fence_match:
        candidate = fence_match.group(1).strip()
        if _is_valid_json(candidate):
            return candidate
        # Try repair even from fence content
        repaired = _repair_json_string(candidate)
        if repaired is not None:
            return repaired

    # 2. Find outermost JSON object {} or array []
    obj = _extract_outermost_structure(stripped, "{", "}")
    if obj and _is_valid_json(obj):
        return obj
    if obj:
        repaired = _repair_json_string(obj)
        if repaired is not None:
            return repaired

    arr = _extract_outermost_structure(stripped, "[", "]")
    if arr and _is_valid_json(arr):
        return arr
    if arr:
        repaired = _repair_json_string(arr)
        if repaired is not None:
            return repaired

    # 3. Try repair on the full text (last resort)
    repaired = _repair_json_string(stripped)
    if repaired is not None:
        return repaired

    return None


def parse_json_response(
    text: str,
    *,
    default: Any = None,
) -> dict[str, Any] | list | None:
    """Parse JSON from an LLM response string.

    Extracts and repairs JSON, returning a Python dict or list.
    Returns `default` (None by default) if no valid JSON is found.

    Args:
        text: Raw LLM response text
        default: Value to return if parsing fails

    Returns:
        Parsed Python object, or `default` on failure
    """
    json_text = extract_json_text(text)
    if json_text is None:
        logger.debug(f"No JSON found in response text ({len(text)} chars)")
        return default

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.warning(f"JSON extracted but failed to parse: {exc}")
        return default


def parse_json_model(
    text: str,
    model: type[T],
    *,
    strict: bool = False,
) -> T | None:
    """Parse and validate JSON against a Pydantic model.

    Args:
        text: Raw LLM response text
        model: Pydantic model class to validate against
        strict: If True, raise ValidationError on schema mismatch.
                If False, return None on failure (default).

    Returns:
        Validated model instance, or None on failure

    Raises:
        ValidationError: Only when strict=True and schema validation fails
    """
    data = parse_json_response(text)
    if data is None:
        if strict:
            raise ValueError(f"No valid JSON found in response: {text[:200]!r}")
        return None

    try:
        return model.model_validate(data)
    except ValidationError as exc:
        if strict:
            raise
        logger.debug(f"JSON parsed but failed Pydantic validation: {exc}")
        return None


def repair_json(text: str) -> str:
    """Attempt to repair malformed JSON string.

    Handles:
    - Truncated JSON (missing closing braces/brackets)
    - Trailing commas before } or ]
    - Single-quoted strings
    - JavaScript-style comments

    Args:
        text: Potentially malformed JSON string

    Returns:
        Repaired JSON string, or '{}' if repair fails
    """
    result = _repair_json_string(text)
    return result if result is not None else "{}"


# ─────────────────────────── Internal helpers ───────────────────────────


def _is_valid_json(text: str) -> bool:
    """Check if text is valid JSON without raising."""
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _extract_outermost_structure(text: str, open_char: str, close_char: str) -> str | None:
    """Find the outermost balanced { } or [ ] block in text.

    Scans for the first open_char and matches the corresponding close_char,
    accounting for nesting. Ignores chars inside strings.

    Args:
        text: Text to search
        open_char: Opening bracket character
        close_char: Closing bracket character

    Returns:
        The outermost block as a string, or None if not found
    """
    start = text.find(open_char)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\" and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    # Truncated — return partial from start
    return text[start:] if depth > 0 else None


def _repair_json_string(text: str) -> str | None:
    """Attempt to repair a potentially malformed JSON string.

    Applies a series of transformations in order:
    1. Strip leading/trailing prose
    2. Remove JavaScript comments
    3. Fix trailing commas
    4. Fix single quotes → double quotes (simple cases)
    5. Close unclosed braces/brackets

    Returns:
        Valid JSON string, or None if repair fails
    """
    if not text or not text.strip():
        return None

    candidate = text.strip()

    # Step 1: Strip code fences if present (already extracted, but just in case)
    candidate = re.sub(r"^```(?:json)?\s*\n?", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\n?```\s*$", "", candidate)
    candidate = candidate.strip()

    # Fast path: already valid after fence strip
    if _is_valid_json(candidate):
        return candidate

    # Step 2: Remove JavaScript-style comments
    # // single-line comments (but not inside strings)
    candidate = _remove_js_comments(candidate)
    if _is_valid_json(candidate):
        return candidate

    # Step 3: Fix trailing commas before ] or }
    # e.g. [1, 2, 3,] → [1, 2, 3]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    if _is_valid_json(candidate):
        return candidate

    # Step 4: Balance unclosed braces/brackets
    candidate = _close_open_structures(candidate)
    if candidate is not None and _is_valid_json(candidate):
        return candidate

    # Step 5: Try simple single-quote fix (risky, may break valid content)
    # Only attempt for small/simple payloads
    if len(text) < 2000:
        single_fixed = _fix_single_quotes(candidate or text.strip())
        if _is_valid_json(single_fixed):
            return single_fixed

    return None


def _remove_js_comments(text: str) -> str:
    """Remove JavaScript-style // and /* */ comments from JSON-like text."""
    result = []
    i = 0
    in_string = False
    escape_next = False

    while i < len(text):
        ch = text[i]

        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue

        if ch == "\\" and in_string:
            result.append(ch)
            escape_next = True
            i += 1
            continue

        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue

        if in_string:
            result.append(ch)
            i += 1
            continue

        # Outside string — check for comments
        if ch == "/" and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch == "/":
                # Single-line comment — skip to end of line
                while i < len(text) and text[i] != "\n":
                    i += 1
                continue
            if next_ch == "*":
                # Block comment — skip to */
                i += 2
                while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2  # skip */
                continue

        result.append(ch)
        i += 1

    return "".join(result)


def _close_open_structures(text: str) -> str | None:
    """Close unclosed JSON braces and brackets.

    Counts unmatched open braces/brackets and appends the missing closers.
    Handles strings correctly (ignores brackets inside quoted strings).
    """
    if not text:
        return None

    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue

        if ch == "\\" and in_string:
            escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]") and stack and stack[-1] == ch:
            stack.pop()

    # Close any open string (truncated mid-string)
    if in_string:
        text = text + '"'

    # Append missing closers in LIFO order
    suffix = "".join(reversed(stack))
    repaired = text + suffix

    # Validate the repaired text
    if _is_valid_json(repaired):
        return repaired

    # Still invalid — might have trailing garbage after a valid JSON block
    return None


def _fix_single_quotes(text: str) -> str:
    """Convert single-quoted JSON to double-quoted.

    Very simple approach — replaces unescaped single-quoted strings.
    Only safe for simple cases without embedded single quotes in values.
    """
    # Replace 'key': or 'value' patterns
    # This regex is intentionally simple and conservative
    result = re.sub(r"'([^'\\]*)'", r'"\1"', text)
    # Also fix key: value without any quotes around keys
    return re.sub(r"(\b\w+\b)\s*:", r'"\1":', result)


# ─────────────────────────── Convenience formatters ───────────────────────────


def format_tool_result(result: Any) -> str:
    """Serialize a tool result to a JSON string for inclusion in messages.

    Ensures the result is always a valid JSON string regardless of type:
    - dict/list → JSON serialized
    - str → returned as-is if valid JSON, else wrapped in {"result": ...}
    - Other → JSON serialized

    Args:
        result: Tool result (any type)

    Returns:
        Valid JSON string
    """
    if isinstance(result, str):
        if _is_valid_json(result):
            return result
        return json.dumps({"result": result}, ensure_ascii=False)

    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"result": str(result)}, ensure_ascii=False)


def extract_text_from_response(response: dict[str, Any]) -> str:
    """Extract plain text content from a normalized LLM response dict.

    Works with OpenAI-format responses (what all providers return after normalization).

    Args:
        response: LLM response dict with role/content/tool_calls

    Returns:
        Text content string (empty string if not found)
    """
    content = response.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Handle content block lists (Anthropic format before normalization)
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""
