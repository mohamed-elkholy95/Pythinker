"""Agent runtime middleware — protocol types and pipeline executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuntimeHook(StrEnum):
    """Lifecycle hooks available to runtime middlewares."""

    before_run = "before_run"
    after_run = "after_run"
    before_step = "before_step"
    after_step = "after_step"
    before_tool = "before_tool"
    after_tool = "after_tool"


@dataclass
class RuntimeContext:
    """Shared mutable context passed through every middleware in the pipeline."""

    session_id: str
    agent_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    workspace: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)


class RuntimeMiddleware:
    """Base class for all runtime middlewares.

    Each method is a pass-through by default; subclasses override only the
    hooks they care about.
    """

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def after_run(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def before_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx

    async def after_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        return ctx


class RuntimePipeline:
    """Ordered middleware pipeline for the LeadAgentRuntime.

    Iterates registered middlewares in insertion order, passing the (possibly
    mutated) context from one middleware to the next.
    """

    __slots__ = ("_middlewares",)

    def __init__(self, middlewares: list[RuntimeMiddleware]) -> None:
        self._middlewares = list(middlewares)

    async def run_hook(self, hook: RuntimeHook, ctx: RuntimeContext) -> RuntimeContext:
        """Execute *hook* on every middleware in order, threading ctx through."""
        for middleware in self._middlewares:
            handler = getattr(middleware, hook.value)
            ctx = await handler(ctx)
        return ctx
