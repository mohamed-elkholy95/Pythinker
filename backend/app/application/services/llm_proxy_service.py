"""Application-layer service for the sandbox LLM proxy.

Wraps infrastructure LLM access so that interface routes never import
directly from the infrastructure layer (DDD layer discipline).
"""
from __future__ import annotations

from typing import Any, Optional


async def proxy_chat_completion(
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: Optional[float] = None,
) -> str:
    """Forward a chat completion request through the configured LLM provider.

    Returns the assistant content string or raises if LLM is unavailable.
    """
    from app.infrastructure.external.llm.factory import get_llm

    llm = get_llm()
    if llm is None:
        raise RuntimeError("LLM not configured")

    result = await llm.ask(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return result.get("content") or ""
