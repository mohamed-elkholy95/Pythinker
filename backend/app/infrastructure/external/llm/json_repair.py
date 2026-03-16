"""Universal JSON extraction and repair for LLM responses.

Infrastructure wrapper around app.domain.utils.json_repair.

Core extraction/parsing logic (no infrastructure dependencies) lives in the
domain layer. This module re-exports the public API for backward compatibility
and adds infrastructure-level helpers that depend on Pydantic models.
"""

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

# Re-export domain utilities so infrastructure callers keep their existing
# import paths without introducing domain ← infra dependency.
from app.domain.utils.json_repair import extract_json_text, parse_json_response  # noqa: F401

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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


def format_tool_result(result: Any) -> str:
    """Serialize a tool result to a JSON string for inclusion in messages.

    Ensures the result is always a valid JSON string regardless of type:
    - dict/list → JSON serialized
    - str → returned as-is if valid JSON, else wrapped in {"result": ...}
    - Other → JSON serialized
    """
    if isinstance(result, str):
        try:
            json.loads(result)
            return result
        except (json.JSONDecodeError, ValueError):
            pass
        return json.dumps({"result": result}, ensure_ascii=False)

    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"result": str(result)}, ensure_ascii=False)


def extract_text_from_response(response: dict[str, Any]) -> str:
    """Extract plain text content from a normalized LLM response dict.

    Works with OpenAI-format responses (what all providers return after normalization).
    """
    content = response.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""
