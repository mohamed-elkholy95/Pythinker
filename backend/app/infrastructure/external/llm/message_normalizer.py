"""Universal message normalizer for LLM providers.

Centralises provider-specific message fixups that were previously scattered
across ``OpenAILLM`` (2206 lines) and ``AnthropicLLM``.  Driven by
``ProviderCapabilities`` so adding a new provider requires only a registry
entry, not touching existing code.

Key transformations:
1. System message position — GLM requires system to be position 0.
2. Content format coercion — GLM only accepts string content, not blocks.
3. ``reasoning_content`` stripping — thinking-API providers inject this
   field; it must be removed before replaying messages.
4. Orphaned ``tool_calls`` repair — assistant messages whose tool_call
   responses are missing get converted to plain text.
5. Role alternation enforcement — GLM rejects consecutive same-role msgs.

This module is infrastructure — it may import from ``domain/external/`` for
ProviderCapabilities but never from ``domain/services/``.

Usage::

    caps = get_capabilities("glm-4-air")
    normalised = normalize_for_provider(messages, caps, provider_type="glm")
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from typing import Any

from app.domain.external.llm_capabilities import ProviderCapabilities

logger = logging.getLogger(__name__)


# ─────────────────────────── Helpers ─────────────────────────────────────────


def coerce_content_to_text(content: Any) -> str:
    """Convert structured/mixed content to a plain string.

    GLM and older models only accept ``string`` content, not content-block
    lists.  This function flattens list content to newline-joined text.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
                else:
                    block_type = item.get("type", "unknown")
                    logger.debug(
                        "Dropping non-text content block (type=%s) during string coercion",
                        block_type,
                    )
                # Drop non-text blocks (for example image blocks) when coercing
                # to plain text for providers that cannot accept multimodal content.
                continue
            if item is not None:
                parts.append(str(item))
        return "\n".join(p for p in parts if p).strip()
    with contextlib.suppress(Exception):
        return json.dumps(content, ensure_ascii=False, default=str)
    return str(content)


def _strip_reasoning_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove ``reasoning_content`` injected by thinking-mode APIs.

    Kimi/thinking providers return ``reasoning_content`` in assistant messages.
    When replaying history, the API rejects messages that *should* have
    reasoning_content but don't — stripping avoids the mismatch entirely.
    """
    cleaned = []
    for msg in messages:
        msg_copy = dict(msg)
        msg_copy.pop("reasoning_content", None)
        # Ensure content is present for assistant messages with tool_calls
        if msg_copy.get("role") == "assistant" and msg_copy.get("tool_calls") and msg_copy.get("content") is None:
            msg_copy["content"] = ""
        cleaned.append(msg_copy)
    return cleaned


def _tool_calls_to_text(tool_calls: list[dict[str, Any]]) -> str:
    """Convert tool_calls to a readable text snippet for context preservation."""
    import json

    parts = []
    for tc in tool_calls:
        func = tc.get("function", {})
        name = func.get("name", "unknown")
        raw_args = func.get("arguments", "{}")
        # Ensure args is a string (may be a parsed dict after internal processing)
        args_str = raw_args if isinstance(raw_args, str) else json.dumps(raw_args, ensure_ascii=False)
        # Truncate large arguments for readability
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        parts.append(f"[Previously called {name}]")
    return "\n".join(parts)


def _convert_orphaned_assistant(msg: dict[str, Any]) -> dict[str, Any]:
    """Convert an orphaned assistant+tool_calls message to plain text."""
    tool_calls = msg.get("tool_calls", [])
    original_content = msg.get("content") or ""
    tool_text = _tool_calls_to_text(tool_calls)
    combined = f"{original_content}\n{tool_text}".strip() if original_content else tool_text
    converted = dict(msg)
    converted.pop("tool_calls", None)
    converted["content"] = combined
    return converted


def _normalize_roles_and_content(
    messages: list[dict[str, Any]],
    string_only: bool,
) -> list[dict[str, Any]]:
    """Apply role normalisation and optional content coercion.

    Args:
        messages: Raw message list.
        string_only: If True, coerce all content to strings (GLM).

    Returns:
        Normalised message list.
    """
    # Standard fields per role (OpenAI Chat Completions spec)
    _standard_fields: dict[str, set[str]] = {
        "system": {"role", "content", "name"},
        "user": {"role", "content", "name"},
        "assistant": {"role", "content", "tool_calls", "name", "refusal"},
        "tool": {"role", "content", "tool_call_id", "name"},
    }

    sanitized: list[dict[str, Any]] = []
    for msg in messages:
        msg_copy = dict(msg)
        # Deep-copy tool_calls to avoid mutating originals
        if "tool_calls" in msg_copy and isinstance(msg_copy["tool_calls"], list):
            msg_copy["tool_calls"] = [
                {**tc, "function": dict(tc["function"])}
                if isinstance(tc, dict) and "function" in tc
                else dict(tc)
                if isinstance(tc, dict)
                else tc
                for tc in msg_copy["tool_calls"]
            ]

        role = msg_copy.get("role", "user")

        # 1. Normalize "developer" role (used by some OpenAI clients)
        if role == "developer":
            msg_copy["role"] = "system"
            role = "system"

        # 2. Content handling
        content = msg_copy.get("content")
        if content is None:
            msg_copy["content"] = ""
        elif string_only and not isinstance(content, str):
            msg_copy["content"] = coerce_content_to_text(content)

        # 3. Fix tool message field names
        if role == "tool" and "function_name" in msg_copy:
            if "name" not in msg_copy:
                msg_copy["name"] = msg_copy["function_name"]
            del msg_copy["function_name"]

        # 4. Remove non-standard fields
        allowed = _standard_fields.get(role, {"role", "content"})
        extra_keys = {k for k in msg_copy if k not in allowed and not k.startswith("_")}
        for key in extra_keys:
            del msg_copy[key]

        # 5a. Ensure required tool message fields
        if role == "tool":
            if not msg_copy.get("name"):
                msg_copy["name"] = "unknown_tool"
            else:
                msg_copy["name"] = str(msg_copy["name"])
            if not msg_copy.get("tool_call_id"):
                msg_copy["tool_call_id"] = f"call_{uuid.uuid4().hex[:8]}"
            else:
                msg_copy["tool_call_id"] = str(msg_copy["tool_call_id"])

        # 5b. Validate tool_calls structure
        if msg_copy.get("tool_calls"):
            valid_calls: list[dict[str, Any]] = []
            for tc in msg_copy["tool_calls"]:
                if isinstance(tc, dict) and tc.get("function"):
                    tc.setdefault("id", f"call_{uuid.uuid4().hex[:8]}")
                    tc.setdefault("type", "function")
                    func = tc["function"]
                    func.setdefault("name", "unknown")
                    if func.get("arguments") is None:
                        func["arguments"] = "{}"
                    elif not isinstance(func["arguments"], str):
                        func["arguments"] = json.dumps(func["arguments"])
                    valid_calls.append(tc)
            if valid_calls:
                msg_copy["tool_calls"] = valid_calls
            else:
                msg_copy.pop("tool_calls", None)

        sanitized.append(msg_copy)

    return sanitized


def _enforce_role_alternation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge consecutive same-role messages (GLM error 1214 prevention)."""
    deduped: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if (
            deduped
            and deduped[-1].get("role") == role
            and role in ("user", "assistant")
            and not msg.get("tool_calls")
            and not deduped[-1].get("tool_calls")
        ):
            prev = deduped[-1].get("content") or ""
            curr = msg.get("content") or ""
            deduped[-1]["content"] = f"{prev}\n{curr}".strip()
        else:
            deduped.append(msg)
    return deduped


def _enforce_system_first(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Move all system messages to position 0 (GLM requirement)."""
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system_msgs = [m for m in messages if m.get("role") != "system"]

    if not system_msgs:
        return messages

    # Merge multiple system messages
    if len(system_msgs) > 1:
        merged = "\n".join(m.get("content") or "" for m in system_msgs).strip()
        system_msgs = [{"role": "system", "content": merged}]

    result = system_msgs + non_system_msgs

    # Ensure the first non-system message is "user", not "assistant"
    first_non_system = next((m for m in result if m.get("role") != "system"), None)
    if first_non_system and first_non_system.get("role") == "assistant":
        insert_pos = len(system_msgs)
        result.insert(insert_pos, {"role": "user", "content": "Please continue."})

    return result


# ─────────────────────────── Public API ──────────────────────────────────────


def normalize_for_provider(
    messages: list[dict[str, Any]],
    capabilities: ProviderCapabilities,
    provider_type: str = "openai",
) -> list[dict[str, Any]]:
    """Normalise a message list for the target provider.

    Applies all necessary transformations based on ``capabilities``:

    1. Strip ``reasoning_content`` (always — safe no-op for non-thinking APIs).
    2. Role normalisation + non-standard field removal.
    3. Content coercion to string when ``capabilities.content_format == "string_only"``.
    4. Role alternation enforcement (merge consecutive same-role messages).
    5. System message moved to position 0 when
       ``capabilities.system_message_position == "first_only"``.

    Args:
        messages: Raw message list from the conversation.
        capabilities: Provider capability descriptor.
        provider_type: Provider name (informational, used for logging).

    Returns:
        Normalised message list (always a new list; input is never mutated).
    """
    if not messages:
        return messages

    # 1. Strip reasoning_content
    result = _strip_reasoning_content(messages)

    # 2. Role normalisation + content coercion + field filtering
    string_only = capabilities.content_format == "string_only"
    result = _normalize_roles_and_content(result, string_only=string_only)

    # 3. Role alternation (prevents consecutive same-role errors)
    result = _enforce_role_alternation(result)

    # 4. System-first constraint
    if capabilities.system_message_position == "first_only":
        result = _enforce_system_first(result)

    logger.debug(
        "normalize_for_provider: provider=%s msgs_in=%d msgs_out=%d string_only=%s",
        provider_type,
        len(messages),
        len(result),
        string_only,
    )
    return result
