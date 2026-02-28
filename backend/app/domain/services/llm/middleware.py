"""LLM Middleware Pipeline — domain-layer abstractions.

Defines the request/response dataclasses and the LLMPipeline composer
that chains LLMMiddleware callables around a base LLM handler.

Usage::

    pipeline = LLMPipeline(
        middlewares=[ConcurrencyMiddleware(), MetricsMiddleware()],
        handler=my_llm_callable,
    )
    response = await pipeline.execute(request)

Each middleware receives ``(request, next_handler)`` and must call
``next_handler(request)`` to propagate the call down the chain.  It may
mutate the request before calling next and/or mutate/wrap the response
after the call returns.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─────────────────────────── Data Transfer Objects ───────────────────────────


@dataclass
class LLMRequest:
    """Normalised input for any LLM call."""

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    enable_caching: bool = False
    response_format: dict[str, Any] | None = None
    tool_choice: str | None = None
    # Free-form bag for cross-cutting data: task_id (budget tracking),
    # session_id (tracing), provider hint, etc.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Normalised output from any LLM call."""

    content: str
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] | None = None
    finish_reason: str = "stop"
    # Populated by middleware: latency_ms, provider, attempt_count, etc.
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────── Type aliases ────────────────────────────────────

LLMCallable = Callable[[LLMRequest], Awaitable[LLMResponse]]


# ─────────────────────────── Protocol ────────────────────────────────────────


class LLMMiddleware:
    """Base class for LLM middleware.

    Subclasses override ``__call__`` and must forward to ``next_handler``::

        async def __call__(
            self, request: LLMRequest, next_handler: LLMCallable
        ) -> LLMResponse:
            # pre-processing
            response = await next_handler(request)
            # post-processing
            return response
    """

    async def __call__(
        self, request: LLMRequest, next_handler: LLMCallable
    ) -> LLMResponse:
        return await next_handler(request)


# ─────────────────────────── Pipeline ────────────────────────────────────────


class LLMPipeline:
    """Compose a list of middlewares around a base handler.

    Middlewares execute in order: the first middleware in the list is the
    outermost wrapper (runs first before the call, last after).

    Args:
        middlewares: Ordered list of middleware instances.
        handler: The innermost callable — typically wraps a concrete LLM's
            ``ask()`` method.
    """

    def __init__(
        self,
        middlewares: list[LLMMiddleware],
        handler: LLMCallable,
    ) -> None:
        self._middlewares = middlewares
        self._handler = handler
        self._chain: LLMCallable = self._build_chain()

    def _build_chain(self) -> LLMCallable:
        """Build the nested callable chain from innermost to outermost."""
        chain: LLMCallable = self._handler
        for middleware in reversed(self._middlewares):
            # Capture the current chain in a closure to avoid late-binding
            _next = chain
            _mw = middleware

            async def _call(
                request: LLMRequest,
                next_handler: LLMCallable = _next,
                mw: LLMMiddleware = _mw,
            ) -> LLMResponse:
                return await mw(request, next_handler)

            chain = _call
        return chain

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute the pipeline with the given request."""
        return await self._chain(request)

    def __repr__(self) -> str:
        names = [type(m).__name__ for m in self._middlewares]
        return f"LLMPipeline([{', '.join(names)}] → handler)"
