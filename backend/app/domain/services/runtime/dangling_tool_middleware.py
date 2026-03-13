"""Dangling Tool Call Recovery Middleware.

When a session is cancelled mid-step the LLM may have emitted an assistant
message that contains ``tool_calls`` entries for which no corresponding
``tool`` role message was ever produced.  Replaying that conversation history
verbatim causes provider API errors ("tool call without a result").

``sanitize_tool_history`` scans the message list and injects a synthetic
placeholder ``tool`` message immediately after any assistant message whose
tool call IDs are not already answered.

``DanglingToolCallMiddleware`` wraps this function as a
``RuntimeMiddleware.before_step`` hook so it runs automatically before each
agent reasoning step.
"""

from __future__ import annotations

from typing import Any

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

# ─────────────────────────── Constants ───────────────────────────────────────

_PLACEHOLDER = "[Interrupted] Tool call was cancelled and did not return a result."


# ─────────────────────────── Sanitizer ───────────────────────────────────────


def sanitize_tool_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of *messages* with dangling tool call IDs patched.

    A "dangling" tool call is one where an assistant message lists a call ID
    in its ``tool_calls`` array but no subsequent ``{"role": "tool", ...}``
    message provides the result for that ID.

    For each dangling ID a synthetic tool message is inserted immediately
    after the assistant message that declared the call.  This keeps the
    conversation history legal for all major LLM providers.

    Args:
        messages: Raw conversation message list (mutated copy is returned;
            the original list is not modified).

    Returns:
        New list with placeholder tool messages injected where needed.
    """
    if not messages:
        return []

    # Collect all tool_call_ids that already have a matching tool response.
    existing_tool_ids: set[str] = {
        msg["tool_call_id"] for msg in messages if msg.get("role") == "tool" and msg.get("tool_call_id")
    }

    result: list[dict[str, Any]] = []

    for msg in messages:
        result.append(msg)

        if msg.get("role") != "assistant":
            continue

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue

        for tc in tool_calls:
            tc_id: str | None = tc.get("id")
            if not tc_id:
                continue
            if tc_id in existing_tool_ids:
                continue

            # Inject placeholder tool response immediately after this message.
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": _PLACEHOLDER,
                }
            )
            existing_tool_ids.add(tc_id)

    return result


# ─────────────────────────── Middleware ──────────────────────────────────────


class DanglingToolCallMiddleware(RuntimeMiddleware):
    """Sanitize conversation history before each agent step.

    Reads ``ctx.metadata["message_history"]`` (if present and a list) and
    replaces it in-place with the sanitized version produced by
    ``sanitize_tool_history``.

    This prevents provider API errors caused by assistant messages that
    reference tool call IDs for which no result was ever returned (typically
    because the session was cancelled mid-flight).
    """

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        """Inject placeholder tool messages for any dangling tool call IDs."""
        history = ctx.metadata.get("message_history")
        if isinstance(history, list):
            ctx.metadata["message_history"] = sanitize_tool_history(history)
        return ctx
