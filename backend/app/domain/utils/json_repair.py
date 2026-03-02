"""Universal JSON extraction and repair for LLM responses.

LLMs frequently return JSON in non-standard ways:
- Wrapped in markdown code fences (```json ... ```)
- Prefixed with prose ("Here is the JSON: {...}")
- Truncated mid-object (streaming cutoff, token limit)
- Single-quoted strings instead of double quotes
- Trailing commas before closing braces
- JavaScript-style comments (//, /* */)
- Numeric keys without quotes

This module lives in domain/utils because it has no infrastructure
dependencies (stdlib + pydantic only) and is used by domain services.

The infrastructure module app.infrastructure.external.llm.json_repair
re-exports from here for backward compatibility with existing infra consumers.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_json_text(text: str) -> str | None:
    """Extract JSON string from LLM response text.

    Handles:
    - Bare JSON (just returns as-is)
    - Markdown code fences: ```json ... ``` or ``` ... ```
    - Inline prose with JSON embedded: "Here is the result: {...}"
    - Multiple JSON objects (returns the first/largest valid one)
    """
    if not text or not text.strip():
        return None

    stripped = text.strip()

    if _is_valid_json(stripped):
        return stripped

    fence_match = re.search(
        r"```(?:json|JSON)?\s*\n?([\s\S]*?)\n?```",
        stripped,
        re.IGNORECASE,
    )
    if fence_match:
        candidate = fence_match.group(1).strip()
        if _is_valid_json(candidate):
            return candidate
        repaired = _repair_json_string(candidate)
        if repaired is not None:
            return repaired

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

    repaired = _repair_json_string(stripped)
    if repaired is not None:
        return repaired

    return None


def parse_json_response(
    text: str,
    *,
    default: Any = None,
) -> "dict[str, Any] | list | None":
    """Parse JSON from an LLM response string.

    Extracts and repairs JSON, returning a Python dict or list.
    Returns `default` (None by default) if no valid JSON is found.
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


# ─────────────────────────── Internal helpers ───────────────────────────


def _is_valid_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _extract_outermost_structure(text: str, open_char: str, close_char: str) -> str | None:
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

    return text[start:] if depth > 0 else None


def _repair_json_string(text: str) -> str | None:
    if not text or not text.strip():
        return None

    candidate = text.strip()

    candidate = re.sub(r"^```(?:json)?\s*\n?", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\n?```\s*$", "", candidate)
    candidate = candidate.strip()

    if _is_valid_json(candidate):
        return candidate

    candidate = _remove_js_comments(candidate)
    if _is_valid_json(candidate):
        return candidate

    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    if _is_valid_json(candidate):
        return candidate

    candidate = _close_open_structures(candidate)
    if candidate is not None and _is_valid_json(candidate):
        return candidate

    if len(text) < 2000:
        single_fixed = _fix_single_quotes(candidate or text.strip())
        if _is_valid_json(single_fixed):
            return single_fixed

    return None


def _remove_js_comments(text: str) -> str:
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

        if ch == "/" and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch == "/":
                while i < len(text) and text[i] != "\n":
                    i += 1
                continue
            if next_ch == "*":
                i += 2
                while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue

        result.append(ch)
        i += 1

    return "".join(result)


def _close_open_structures(text: str) -> str | None:
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

    if in_string:
        text = text + '"'

    suffix = "".join(reversed(stack))
    repaired = text + suffix

    if _is_valid_json(repaired):
        return repaired

    return None


def _fix_single_quotes(text: str) -> str:
    result = re.sub(r"'([^'\\]*)'", r'"\1"', text)
    return re.sub(r"(\b\w+\b)\s*:", r'"\1":', result)
