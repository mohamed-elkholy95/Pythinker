"""Agent Middleware Protocol and data types.

Defines the lifecycle hook contract for composable middleware that intercepts
agent execution at 9 points: before/after execution, step, model, tool_call,
and on_error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.domain.models.event import BaseEvent
from app.domain.models.tool_permission import PermissionTier
from app.domain.models.tool_result import ToolResult


class MiddlewareSignal(StrEnum):
    """Control signals returned by middleware to influence execution flow."""

    CONTINUE = "continue"
    SKIP_TOOL = "skip_tool"
    INJECT = "inject"
    FORCE = "force"
    ABORT = "abort"


@dataclass(slots=True)
class MiddlewareContext:
    """Mutable shared context passed through the middleware chain."""

    agent_id: str
    session_id: str
    iteration_count: int = 0
    step_iteration_count: int = 0
    elapsed_seconds: float = 0.0
    wall_clock_budget: float = 600.0
    token_budget_ratio: float = 0.0
    active_tier: PermissionTier = PermissionTier.DANGER
    active_phase: str | None = None
    research_depth: str | None = None
    step_start_time: float = 0.0
    stuck_recovery_exhausted: bool = False
    injected_messages: list[dict[str, Any]] = field(default_factory=list)
    emitted_events: list[BaseEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCallInfo:
    """Immutable normalized tool call data passed to middleware."""

    call_id: str
    function_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MiddlewareResult:
    """Immutable result from a middleware hook invocation."""

    signal: MiddlewareSignal = MiddlewareSignal.CONTINUE
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def ok() -> MiddlewareResult:
        """Convenience factory for CONTINUE result."""
        return MiddlewareResult()


@runtime_checkable
class AgentMiddleware(Protocol):
    """Protocol for agent execution middleware."""

    @property
    def name(self) -> str: ...

    async def before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def before_model(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def after_model(self, ctx: MiddlewareContext, response: dict[str, Any]) -> MiddlewareResult: ...
    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult: ...
    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult: ...
    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def after_execution(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult: ...
