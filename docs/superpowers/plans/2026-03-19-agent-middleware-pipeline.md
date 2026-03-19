# Agent Middleware Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose BaseAgent's god-class cross-cutting concerns into a composable middleware pipeline, aligned with 2026 agent architecture patterns.

**Architecture:** Chain of Responsibility pipeline with 9 lifecycle hooks (`before_execution`, `before_step`, `before_model`, `after_model`, `before_tool_call`, `after_tool_call`, `after_step`, `after_execution`, `on_error`). Each existing embedded service (StuckDetector, HallucinationDetector, SecurityAssessor, etc.) becomes a thin middleware adapter. Pipeline is session-scoped, created by factory, injected into BaseAgent.

**Tech Stack:** Python 3.12+, `@dataclass(frozen=True, slots=True)`, `Protocol`/`@runtime_checkable`, `StrEnum`, pytest, existing domain services (unchanged)

**Spec:** `docs/superpowers/specs/2026-03-19-agent-middleware-pipeline-design.md`

**Scope:** This plan covers **Phases 1-2** (Foundation + Adapters + BaseAgent integration). Phase 3 (refactor `_execute_inner()` to use pipeline instead of inline service calls) and Phase 4 (modify `execution.py`, `plan_act.py`, eliminate globals) will be a follow-up plan after Phase 1-2 is validated.

---

## File Structure

### New Files (Foundation)
| File | Responsibility |
|------|---------------|
| `backend/app/domain/services/agents/middleware.py` | Protocol, data types (MiddlewareSignal, MiddlewareContext, ToolCallInfo, MiddlewareResult) |
| `backend/app/domain/services/agents/base_middleware.py` | BaseMiddleware with no-op defaults for all 9 hooks |
| `backend/app/domain/services/agents/middleware_pipeline.py` | MiddlewarePipeline — chains middleware, runs hooks |
| `backend/app/domain/services/agents/agent_context.py` | AgentServiceContext — session-scoped container |
| `backend/app/domain/services/agents/agent_context_factory.py` | Factory builds context with configured middleware |

### New Files (Middleware Adapters)
| File | Wraps | Primary Hooks |
|------|-------|---------------|
| `backend/app/domain/services/agents/middleware_adapters/__init__.py` | Exports | — |
| `backend/app/domain/services/agents/middleware_adapters/stuck_detection.py` | `StuckDetector` | `before_tool_call`, `after_step` |
| `backend/app/domain/services/agents/middleware_adapters/hallucination_guard.py` | `ToolHallucinationDetector` | `before_execution`, `before_step`, `before_tool_call` |
| `backend/app/domain/services/agents/middleware_adapters/security_assessment.py` | `SecurityAssessor` | `before_tool_call` |
| `backend/app/domain/services/agents/middleware_adapters/efficiency_monitor.py` | `ToolEfficiencyMonitor` | `before_step`, `after_tool_call` |
| `backend/app/domain/services/agents/middleware_adapters/url_failure_guard.py` | `UrlFailureGuard` | `before_tool_call`, `after_tool_call` |
| `backend/app/domain/services/agents/middleware_adapters/error_handler.py` | `ErrorHandler` | `on_error` |
| `backend/app/domain/services/agents/middleware_adapters/wall_clock_pressure.py` | (extracted logic) | `before_step`, `before_tool_call` |
| `backend/app/domain/services/agents/middleware_adapters/token_budget.py` | `TokenBudgetManager` | `before_step`, `before_model` |

### New Test Files
| File | Tests |
|------|-------|
| `backend/tests/domain/services/agents/test_middleware_types.py` | Data types, MiddlewareSignal, frozen dataclasses |
| `backend/tests/domain/services/agents/test_middleware_pipeline.py` | Pipeline ordering, signal propagation, error handling |
| `backend/tests/domain/services/agents/test_mw_stuck_detection.py` | StuckDetectionMiddleware adapter |
| `backend/tests/domain/services/agents/test_mw_hallucination_guard.py` | HallucinationGuardMiddleware adapter |
| `backend/tests/domain/services/agents/test_mw_security_assessment.py` | SecurityAssessmentMiddleware adapter |
| `backend/tests/domain/services/agents/test_mw_efficiency_monitor.py` | EfficiencyMonitorMiddleware adapter |
| `backend/tests/domain/services/agents/test_mw_url_failure_guard.py` | UrlFailureGuardMiddleware adapter |
| `backend/tests/domain/services/agents/test_mw_error_handler.py` | ErrorHandlerMiddleware adapter |
| `backend/tests/domain/services/agents/test_mw_wall_clock_pressure.py` | WallClockPressureMiddleware adapter |
| `backend/tests/domain/services/agents/test_mw_token_budget.py` | TokenBudgetMiddleware adapter |
| `backend/tests/domain/services/agents/test_agent_context_factory.py` | Factory builds correct pipeline |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/domain/services/agents/base.py` | Add `service_context` param, `_build_default_pipeline()`, pipeline integration in `_execute_inner()` |

---

## Task 1: Core Data Types (`middleware.py`)

**Files:**
- Create: `backend/app/domain/services/agents/middleware.py`
- Test: `backend/tests/domain/services/agents/test_middleware_types.py`

- [ ] **Step 1: Write failing tests for MiddlewareSignal enum**

```python
# backend/tests/domain/services/agents/test_middleware_types.py
"""Tests for middleware data types."""
import pytest
from app.domain.services.agents.middleware import (
    MiddlewareSignal,
    MiddlewareContext,
    MiddlewareResult,
    ToolCallInfo,
)


class TestMiddlewareSignal:
    def test_signal_values(self):
        assert MiddlewareSignal.CONTINUE == "continue"
        assert MiddlewareSignal.SKIP_TOOL == "skip_tool"
        assert MiddlewareSignal.INJECT == "inject"
        assert MiddlewareSignal.FORCE == "force"
        assert MiddlewareSignal.ABORT == "abort"

    def test_signal_is_str_enum(self):
        assert isinstance(MiddlewareSignal.CONTINUE, str)


class TestMiddlewareContext:
    def test_default_construction(self):
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        assert ctx.agent_id == "a1"
        assert ctx.iteration_count == 0
        assert ctx.injected_messages == []
        assert ctx.emitted_events == []
        assert ctx.metadata == {}
        assert ctx.step_start_time == 0.0
        assert ctx.stuck_recovery_exhausted is False

    def test_mutable_fields(self):
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        ctx.iteration_count = 5
        ctx.stuck_recovery_exhausted = True
        assert ctx.iteration_count == 5
        assert ctx.stuck_recovery_exhausted is True


class TestToolCallInfo:
    def test_frozen(self):
        info = ToolCallInfo(call_id="c1", function_name="file_read", arguments={"path": "/tmp"})
        assert info.function_name == "file_read"
        with pytest.raises(AttributeError):
            info.function_name = "changed"  # type: ignore[misc]


class TestMiddlewareResult:
    def test_ok_factory(self):
        result = MiddlewareResult.ok()
        assert result.signal == MiddlewareSignal.CONTINUE
        assert result.message is None

    def test_frozen(self):
        result = MiddlewareResult(signal=MiddlewareSignal.FORCE, message="stop")
        with pytest.raises(AttributeError):
            result.signal = MiddlewareSignal.CONTINUE  # type: ignore[misc]

    def test_with_metadata(self):
        result = MiddlewareResult(
            signal=MiddlewareSignal.SKIP_TOOL,
            message="blocked",
            metadata={"reason": "security"},
        )
        assert result.metadata["reason"] == "security"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && conda activate pythinker && pytest tests/domain/services/agents/test_middleware_types.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.services.agents.middleware'`

- [ ] **Step 3: Implement middleware.py**

```python
# backend/app/domain/services/agents/middleware.py
"""Agent Middleware Protocol and data types.

Defines the lifecycle hook contract for composable middleware that intercepts
agent execution at 9 points: before/after execution, step, model, tool_call,
and on_error.

Context7 validated:
- @dataclass(frozen=True, slots=True) for immutable value objects (pydantic.dev)
- @dataclass(slots=True) for mutable shared state (MiddlewareContext)
- Protocol + @runtime_checkable for structural subtyping
- StrEnum for Python 3.11+ string enums
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.domain.models.event import BaseEvent
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
    """Mutable shared context passed through the middleware chain.

    Replaces the 30+ instance variables scattered across BaseAgent.
    Mutable because middleware writes to it during execution.
    """

    agent_id: str
    session_id: str
    iteration_count: int = 0
    step_iteration_count: int = 0
    elapsed_seconds: float = 0.0
    wall_clock_budget: float = 600.0
    token_budget_ratio: float = 0.0
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
    """Protocol for agent execution middleware.

    Implement any subset of hooks. Unimplemented hooks should return
    MiddlewareResult.ok().
    """

    @property
    def name(self) -> str: ...

    async def before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def before_model(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def after_model(self, ctx: MiddlewareContext, response: dict[str, Any]) -> MiddlewareResult: ...
    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult: ...
    async def after_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult) -> MiddlewareResult: ...
    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def after_execution(self, ctx: MiddlewareContext) -> MiddlewareResult: ...
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult: ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/domain/services/agents/test_middleware_types.py -v
```
Expected: ALL PASS

- [ ] **Step 5: Lint check**

```bash
cd backend && ruff check app/domain/services/agents/middleware.py && ruff format --check app/domain/services/agents/middleware.py
```

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/domain/services/agents/middleware.py tests/domain/services/agents/test_middleware_types.py && git commit -m "feat(agents): add middleware protocol and data types

Define AgentMiddleware Protocol with 9 lifecycle hooks, MiddlewareSignal
enum, MiddlewareContext (mutable), ToolCallInfo and MiddlewareResult
(frozen). Foundation for agent middleware pipeline architecture."
```

---

## Task 2: Base Middleware with No-Op Defaults (`base_middleware.py`)

**Files:**
- Create: `backend/app/domain/services/agents/base_middleware.py`
- Test: Add to `backend/tests/domain/services/agents/test_middleware_types.py`

- [ ] **Step 1: Write failing test for BaseMiddleware**

```python
# Append to test_middleware_types.py
from app.domain.services.agents.base_middleware import BaseMiddleware


class TestBaseMiddleware:
    @pytest.mark.asyncio
    async def test_all_hooks_return_continue(self):
        mw = BaseMiddleware()
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        tool = ToolCallInfo(call_id="c1", function_name="file_read", arguments={})
        from app.domain.models.tool_result import ToolResult

        result_obj = ToolResult(success=True, message="ok")

        assert (await mw.before_execution(ctx)).signal == MiddlewareSignal.CONTINUE
        assert (await mw.before_step(ctx)).signal == MiddlewareSignal.CONTINUE
        assert (await mw.before_model(ctx)).signal == MiddlewareSignal.CONTINUE
        assert (await mw.after_model(ctx, {})).signal == MiddlewareSignal.CONTINUE
        assert (await mw.before_tool_call(ctx, tool)).signal == MiddlewareSignal.CONTINUE
        assert (await mw.after_tool_call(ctx, tool, result_obj)).signal == MiddlewareSignal.CONTINUE
        assert (await mw.after_step(ctx)).signal == MiddlewareSignal.CONTINUE
        assert (await mw.after_execution(ctx)).signal == MiddlewareSignal.CONTINUE
        assert (await mw.on_error(ctx, RuntimeError("test"))).signal == MiddlewareSignal.CONTINUE

    def test_name_defaults_to_class_name(self):
        mw = BaseMiddleware()
        assert mw.name == "BaseMiddleware"

    def test_satisfies_protocol(self):
        mw = BaseMiddleware()
        assert isinstance(mw, AgentMiddleware)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/domain/services/agents/test_middleware_types.py::TestBaseMiddleware -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement base_middleware.py**

```python
# backend/app/domain/services/agents/base_middleware.py
"""Base middleware with no-op defaults for all hooks.

Subclass and override only the hooks you need.
"""
from __future__ import annotations

from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    ToolCallInfo,
)


class BaseMiddleware:
    """Concrete base with no-op defaults. Subclass to implement specific hooks."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    async def before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def before_model(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_model(self, ctx: MiddlewareContext, response: dict[str, Any]) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult:
        return MiddlewareResult.ok()
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
cd backend && pytest tests/domain/services/agents/test_middleware_types.py -v && ruff check app/domain/services/agents/base_middleware.py && ruff format --check app/domain/services/agents/base_middleware.py
```

```bash
cd backend && git add app/domain/services/agents/base_middleware.py tests/domain/services/agents/test_middleware_types.py && git commit -m "feat(agents): add BaseMiddleware with no-op defaults for all 9 hooks"
```

---

## Task 3: Middleware Pipeline (`middleware_pipeline.py`)

**Files:**
- Create: `backend/app/domain/services/agents/middleware_pipeline.py`
- Test: `backend/tests/domain/services/agents/test_middleware_pipeline.py`

- [ ] **Step 1: Write failing tests for pipeline**

```python
# backend/tests/domain/services/agents/test_middleware_pipeline.py
"""Tests for MiddlewarePipeline — ordering, signal propagation, error handling."""
import pytest
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


class AlwaysForceMiddleware(BaseMiddleware):
    @property
    def name(self) -> str:
        return "always_force"

    async def before_step(self, ctx):
        return MiddlewareResult(signal=MiddlewareSignal.FORCE, message="forced")

    async def before_tool_call(self, ctx, tool_call):
        return MiddlewareResult(signal=MiddlewareSignal.SKIP_TOOL, message="blocked")


class AlwaysInjectMiddleware(BaseMiddleware):
    @property
    def name(self) -> str:
        return "always_inject"

    async def before_step(self, ctx):
        return MiddlewareResult(signal=MiddlewareSignal.INJECT, message="injected")


class TrackingMiddleware(BaseMiddleware):
    """Records which hooks were called."""

    def __init__(self):
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "tracking"

    async def before_step(self, ctx):
        self.calls.append("before_step")
        return MiddlewareResult.ok()

    async def after_step(self, ctx):
        self.calls.append("after_step")
        return MiddlewareResult.ok()

    async def before_tool_call(self, ctx, tool_call):
        self.calls.append(f"before_tool:{tool_call.function_name}")
        return MiddlewareResult.ok()

    async def after_tool_call(self, ctx, tool_call, result):
        self.calls.append(f"after_tool:{tool_call.function_name}")
        return MiddlewareResult.ok()

    async def on_error(self, ctx, error):
        self.calls.append(f"on_error:{type(error).__name__}")
        return MiddlewareResult.ok()


class TestPipelineOrdering:
    @pytest.mark.asyncio
    async def test_empty_pipeline_returns_continue(self):
        pipeline = MiddlewarePipeline()
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        result = await pipeline.run_before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_first_non_continue_wins_for_before_hooks(self):
        tracker = TrackingMiddleware()
        pipeline = MiddlewarePipeline([tracker, AlwaysForceMiddleware(), AlwaysInjectMiddleware()])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")

        result = await pipeline.run_before_step(ctx)
        # tracker returns CONTINUE, force returns FORCE (wins), inject never runs
        assert result.signal == MiddlewareSignal.FORCE
        assert "before_step" in tracker.calls

    @pytest.mark.asyncio
    async def test_all_run_for_after_hooks_last_wins(self):
        t1 = TrackingMiddleware()
        t2 = TrackingMiddleware()
        pipeline = MiddlewarePipeline([t1, t2])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")

        await pipeline.run_after_step(ctx)
        assert "after_step" in t1.calls
        assert "after_step" in t2.calls


class TestPipelineFluentApi:
    def test_use_returns_self_for_chaining(self):
        pipeline = MiddlewarePipeline()
        result = pipeline.use(TrackingMiddleware()).use(AlwaysForceMiddleware())
        assert result is pipeline
        assert len(pipeline.middleware) == 2


class TestPipelineErrorHandling:
    @pytest.mark.asyncio
    async def test_middleware_exception_is_swallowed(self):
        class BrokenMiddleware(BaseMiddleware):
            @property
            def name(self):
                return "broken"

            async def before_step(self, ctx):
                raise RuntimeError("boom")

        pipeline = MiddlewarePipeline([BrokenMiddleware(), TrackingMiddleware()])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")

        # Should not raise — exception is swallowed, next middleware runs
        result = await pipeline.run_before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_on_error_hook_receives_exception(self):
        tracker = TrackingMiddleware()
        pipeline = MiddlewarePipeline([tracker])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")

        await pipeline.run_on_error(ctx, ValueError("test error"))
        assert "on_error:ValueError" in tracker.calls


class TestPipelineToolCallHooks:
    @pytest.mark.asyncio
    async def test_skip_tool_signal(self):
        pipeline = MiddlewarePipeline([AlwaysForceMiddleware()])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        tool = ToolCallInfo(call_id="c1", function_name="file_read", arguments={})

        result = await pipeline.run_before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.SKIP_TOOL

    @pytest.mark.asyncio
    async def test_after_tool_call_all_run(self):
        t1 = TrackingMiddleware()
        t2 = TrackingMiddleware()
        pipeline = MiddlewarePipeline([t1, t2])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        tool = ToolCallInfo(call_id="c1", function_name="shell_execute", arguments={})
        result_obj = ToolResult(success=True, message="ok")

        await pipeline.run_after_tool_call(ctx, tool, result_obj)
        assert "after_tool:shell_execute" in t1.calls
        assert "after_tool:shell_execute" in t2.calls
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/domain/services/agents/test_middleware_pipeline.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement middleware_pipeline.py**

```python
# backend/app/domain/services/agents/middleware_pipeline.py
"""Pipeline that chains middleware in registration order.

Chain of Responsibility: each middleware can signal to short-circuit,
inject messages, or force-advance the step.

Before hooks: first non-CONTINUE signal wins (short-circuit).
After hooks: all middleware run, last non-CONTINUE signal wins.
"""
from __future__ import annotations

import logging
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import (
    AgentMiddleware,
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)

logger = logging.getLogger(__name__)


class MiddlewarePipeline:
    """Executes middleware hooks in registration order."""

    def __init__(self, middleware: list[AgentMiddleware] | None = None) -> None:
        self._middleware: list[AgentMiddleware] = list(middleware or [])

    def use(self, mw: AgentMiddleware) -> MiddlewarePipeline:
        """Register middleware (fluent API). Returns self for chaining."""
        self._middleware.append(mw)
        return self

    @property
    def middleware(self) -> list[AgentMiddleware]:
        """Read-only copy of registered middleware."""
        return list(self._middleware)

    async def _run_first_wins(self, hook_name: str, *args: Any) -> MiddlewareResult:
        """Run hook on all middleware. First non-CONTINUE signal wins."""
        for mw in self._middleware:
            hook = getattr(mw, hook_name, None)
            if hook is None:
                continue
            try:
                result: MiddlewareResult = await hook(*args)
                if result.signal != MiddlewareSignal.CONTINUE:
                    logger.debug(
                        "Middleware %s.%s returned %s",
                        mw.name,
                        hook_name,
                        result.signal,
                    )
                    return result
            except Exception:
                logger.exception(
                    "Middleware %s.%s raised exception (swallowed)",
                    mw.name,
                    hook_name,
                )
        return MiddlewareResult.ok()

    async def _run_all_last_wins(self, hook_name: str, *args: Any) -> MiddlewareResult:
        """Run hook on all middleware. Last non-CONTINUE signal wins."""
        final = MiddlewareResult.ok()
        for mw in self._middleware:
            hook = getattr(mw, hook_name, None)
            if hook is None:
                continue
            try:
                result: MiddlewareResult = await hook(*args)
                if result.signal != MiddlewareSignal.CONTINUE:
                    final = result
            except Exception:
                logger.exception(
                    "Middleware %s.%s raised exception (swallowed)",
                    mw.name,
                    hook_name,
                )
        return final

    # ── Before hooks (first non-CONTINUE wins) ──

    async def run_before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_first_wins("before_execution", ctx)

    async def run_before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_first_wins("before_step", ctx)

    async def run_before_model(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_first_wins("before_model", ctx)

    async def run_before_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo
    ) -> MiddlewareResult:
        return await self._run_first_wins("before_tool_call", ctx, tool_call)

    # ── After hooks (all run, last non-CONTINUE wins) ──

    async def run_after_model(
        self, ctx: MiddlewareContext, response: dict[str, Any]
    ) -> MiddlewareResult:
        return await self._run_all_last_wins("after_model", ctx, response)

    async def run_after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        return await self._run_all_last_wins("after_tool_call", ctx, tool_call, result)

    async def run_after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_all_last_wins("after_step", ctx)

    async def run_after_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_all_last_wins("after_execution", ctx)

    async def run_on_error(
        self, ctx: MiddlewareContext, error: Exception
    ) -> MiddlewareResult:
        return await self._run_first_wins("on_error", ctx, error)
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
cd backend && pytest tests/domain/services/agents/test_middleware_pipeline.py -v && ruff check app/domain/services/agents/middleware_pipeline.py && ruff format --check app/domain/services/agents/middleware_pipeline.py
```

```bash
cd backend && git add app/domain/services/agents/middleware_pipeline.py tests/domain/services/agents/test_middleware_pipeline.py && git commit -m "feat(agents): add MiddlewarePipeline with chain of responsibility

First non-CONTINUE wins for before_* hooks (short-circuit).
All middleware run for after_* hooks (last non-CONTINUE wins).
Exceptions in middleware are swallowed with logging."
```

---

## Task 4: Agent Service Context & Factory

**Files:**
- Create: `backend/app/domain/services/agents/agent_context.py`
- Create: `backend/app/domain/services/agents/agent_context_factory.py`
- Test: `backend/tests/domain/services/agents/test_agent_context_factory.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/domain/services/agents/test_agent_context_factory.py
"""Tests for AgentServiceContext and AgentContextFactory."""
import pytest
from app.domain.services.agents.agent_context import AgentServiceContext
from app.domain.services.agents.middleware import AgentMiddleware
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline
from app.domain.services.agents.base_middleware import BaseMiddleware


class TestAgentServiceContext:
    def test_construction(self):
        pipeline = MiddlewarePipeline()
        from app.domain.external.observability import get_null_metrics

        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=get_null_metrics(),
            feature_flags={"test": True},
        )
        assert ctx.feature_flags["test"] is True

    def test_get_middleware_by_name(self):
        class Named(BaseMiddleware):
            @property
            def name(self):
                return "my_mw"

        pipeline = MiddlewarePipeline([Named()])
        from app.domain.external.observability import get_null_metrics

        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=get_null_metrics(),
            feature_flags={},
        )
        assert ctx.get_middleware("my_mw") is not None
        assert ctx.get_middleware("nonexistent") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/domain/services/agents/test_agent_context_factory.py -v
```

- [ ] **Step 3: Implement agent_context.py**

```python
# backend/app/domain/services/agents/agent_context.py
"""Session-scoped service container for agent middleware and services.

Replaces static global singletons with explicitly constructed,
session-scoped instances. Thread-safe by construction (one per session).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.external.observability import MetricsPort
from app.domain.services.agents.middleware import AgentMiddleware
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


@dataclass(slots=True)
class AgentServiceContext:
    """All services needed by an agent, scoped to a single session."""

    middleware_pipeline: MiddlewarePipeline
    metrics: MetricsPort
    feature_flags: dict[str, bool]

    def get_middleware(self, name: str) -> AgentMiddleware | None:
        """Retrieve a specific middleware by name for introspection/stats."""
        for mw in self.middleware_pipeline.middleware:
            if mw.name == name:
                return mw
        return None
```

- [ ] **Step 4: Implement agent_context_factory.py (stub — adapters created in later tasks)**

```python
# backend/app/domain/services/agents/agent_context_factory.py
"""Factory that builds session-scoped AgentServiceContext.

Reads feature flags to decide which middleware to register.
Middleware order: cheapest/most critical checks first.
"""
from __future__ import annotations

import logging

from app.domain.external.observability import MetricsPort
from app.domain.services.agents.agent_context import AgentServiceContext
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline

logger = logging.getLogger(__name__)


class AgentContextFactory:
    """Builds session-scoped service contexts with configured middleware.

    Middleware is registered in priority order:
    1. WallClockPressure  — hard budget limits (cheapest check)
    2. TokenBudget        — token limits
    3. SecurityAssessment  — block dangerous actions
    4. HallucinationGuard  — catch hallucinated tools
    5. EfficiencyMonitor   — detect analysis paralysis
    6. UrlFailureGuard     — skip known-failed URLs
    7. StuckDetection      — detect stuck loops
    8. ErrorHandler         — classify/handle errors (last — catches all)
    """

    def create(
        self,
        agent_id: str,
        session_id: str,
        tools: list | None = None,
        research_mode: str | None = None,
        feature_flags: dict[str, bool] | None = None,
    ) -> AgentServiceContext:
        """Create a session-scoped context with all middleware registered."""
        flags = feature_flags or self._load_feature_flags()
        pipeline = MiddlewarePipeline()

        # Middleware adapters will be registered here as they are implemented
        # in Tasks 5-12. For now, pipeline is empty (backward compatible).

        return AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=self._get_metrics(),
            feature_flags=flags,
        )

    @staticmethod
    def _load_feature_flags() -> dict[str, bool]:
        from app.core.config import get_feature_flags

        return get_feature_flags()

    @staticmethod
    def _get_metrics() -> MetricsPort:
        from app.domain.external.observability import get_null_metrics

        return get_null_metrics()
```

- [ ] **Step 5: Run tests, lint, commit**

```bash
cd backend && pytest tests/domain/services/agents/test_agent_context_factory.py -v && ruff check app/domain/services/agents/agent_context.py app/domain/services/agents/agent_context_factory.py
```

```bash
cd backend && git add app/domain/services/agents/agent_context.py app/domain/services/agents/agent_context_factory.py tests/domain/services/agents/test_agent_context_factory.py && git commit -m "feat(agents): add AgentServiceContext and AgentContextFactory

Session-scoped container replaces static globals.
Factory stub ready for middleware adapter registration."
```

---

## Task 5: Middleware Adapters Directory + HallucinationGuardMiddleware

**Files:**
- Create: `backend/app/domain/services/agents/middleware_adapters/__init__.py`
- Create: `backend/app/domain/services/agents/middleware_adapters/hallucination_guard.py`
- Test: `backend/tests/domain/services/agents/test_mw_hallucination_guard.py`

- [ ] **Step 1: Create __init__.py and write failing tests**

```python
# backend/app/domain/services/agents/middleware_adapters/__init__.py
"""Middleware adapters — thin wrappers around existing agent services."""
```

```python
# backend/tests/domain/services/agents/test_mw_hallucination_guard.py
"""Tests for HallucinationGuardMiddleware."""
import pytest
from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.hallucination_guard import (
    HallucinationGuardMiddleware,
)


@pytest.fixture
def detector():
    return ToolHallucinationDetector(["file_read", "file_write", "shell_execute"])


@pytest.fixture
def mw(detector):
    return HallucinationGuardMiddleware(detector=detector)


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestHallucinationGuardName:
    def test_name(self, mw):
        assert mw.name == "hallucination_guard"


class TestBeforeToolCall:
    @pytest.mark.asyncio
    async def test_valid_tool_returns_continue(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={"path": "/tmp"})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_hallucinated_tool_returns_skip(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="nonexistent_tool", arguments={})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.SKIP_TOOL
        assert result.message is not None


class TestBeforeStepHallucinationLoop:
    @pytest.mark.asyncio
    async def test_no_loop_returns_continue(self, mw, ctx):
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_force_after_max_hallucinations(self, mw, ctx, detector):
        # Simulate hallucination loop by forcing detector state
        for _ in range(5):
            detector.detect("fake_tool_xyz")

        # Should inject correction first
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.INJECT

        # Simulate more hallucinations
        for _ in range(5):
            detector.detect("fake_tool_abc")
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.INJECT

        # Third time hits the cap
        for _ in range(5):
            detector.detect("fake_tool_def")
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE


class TestBeforeExecutionReset:
    @pytest.mark.asyncio
    async def test_resets_counter(self, mw, ctx):
        mw._count_this_step = 5
        await mw.before_execution(ctx)
        assert mw._count_this_step == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/domain/services/agents/test_mw_hallucination_guard.py -v
```

- [ ] **Step 3: Implement hallucination_guard.py**

```python
# backend/app/domain/services/agents/middleware_adapters/hallucination_guard.py
"""Middleware adapter for ToolHallucinationDetector.

Intercepts tool calls to detect hallucinated tool names and parameters.
Injects correction prompts when hallucination loops are detected.
"""
from __future__ import annotations

from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.hallucination_detector import (
    ToolHallucinationDetector,
)
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)


class HallucinationGuardMiddleware(BaseMiddleware):
    """Detects hallucinated tool names/params and injects corrections."""

    MAX_HALLUCINATIONS_PER_STEP: int = 3

    def __init__(self, detector: ToolHallucinationDetector) -> None:
        self._detector = detector
        self._count_this_step: int = 0

    @property
    def name(self) -> str:
        return "hallucination_guard"

    async def before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """Reset per-step counter at the start of each execution."""
        self._count_this_step = 0
        return MiddlewareResult.ok()

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """Check if hallucination loop correction is needed."""
        if not self._detector.should_inject_correction_prompt():
            return MiddlewareResult.ok()

        self._count_this_step += 1
        if self._count_this_step >= self.MAX_HALLUCINATIONS_PER_STEP:
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message="Hallucination cap reached — force-advancing.",
            )

        correction = self._detector.get_correction_prompt()
        self._detector.reset()
        return MiddlewareResult(
            signal=MiddlewareSignal.INJECT,
            message=correction,
        )

    async def before_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo
    ) -> MiddlewareResult:
        """Validate tool name exists and parameters are valid."""
        correction = self._detector.detect(tool_call.function_name)
        if correction:
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=correction,
                metadata={"hallucinated_tool": tool_call.function_name},
            )

        validation = self._detector.validate_tool_call(
            tool_call.function_name, tool_call.arguments
        )
        if not validation.is_valid:
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=validation.error_message or "Invalid tool call parameters.",
                metadata={
                    "error_type": validation.error_type,
                    "suggestions": validation.suggestions,
                },
            )

        return MiddlewareResult.ok()
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
cd backend && pytest tests/domain/services/agents/test_mw_hallucination_guard.py -v && ruff check app/domain/services/agents/middleware_adapters/
```

```bash
cd backend && git add app/domain/services/agents/middleware_adapters/ tests/domain/services/agents/test_mw_hallucination_guard.py && git commit -m "feat(agents): add HallucinationGuardMiddleware adapter

Wraps ToolHallucinationDetector with before_step and before_tool_call hooks.
Detects hallucinated tool names, validates parameters, injects corrections."
```

---

## Task 6: StuckDetectionMiddleware

**Files:**
- Create: `backend/app/domain/services/agents/middleware_adapters/stuck_detection.py`
- Test: `backend/tests/domain/services/agents/test_mw_stuck_detection.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/domain/services/agents/test_mw_stuck_detection.py
"""Tests for StuckDetectionMiddleware."""
import pytest
from app.domain.services.agents.middleware import (
    MiddlewareContext, MiddlewareResult, MiddlewareSignal, ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.stuck_detection import (
    StuckDetectionMiddleware,
)
from app.domain.services.agents.stuck_detector import StuckDetector


@pytest.fixture
def mw():
    return StuckDetectionMiddleware(detector=StuckDetector(window_size=3, threshold=2))


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestStuckDetectionName:
    def test_name(self, mw):
        assert mw.name == "stuck_detection"


class TestBeforeToolCall:
    @pytest.mark.asyncio
    async def test_tracks_tool_action(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={"path": "/tmp"})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE
        # Detector should have recorded this action in its tool action history
        assert len(mw._detector._tool_action_history) > 0


class TestAfterStep:
    @pytest.mark.asyncio
    async def test_non_stuck_returns_continue(self, mw, ctx):
        result = await mw.after_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE
```

- [ ] **Step 2: Run tests to verify they fail, then implement**

```python
# backend/app/domain/services/agents/middleware_adapters/stuck_detection.py
"""Middleware adapter for StuckDetector."""
from __future__ import annotations

from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext, MiddlewareResult, MiddlewareSignal, ToolCallInfo,
)
from app.domain.services.agents.stuck_detector import StuckDetector


class StuckDetectionMiddleware(BaseMiddleware):
    """Tracks responses and tool actions for stuck loop detection."""

    def __init__(self, detector: StuckDetector | None = None) -> None:
        self._detector = detector or StuckDetector(window_size=5, threshold=3)

    @property
    def name(self) -> str:
        return "stuck_detection"

    async def before_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo
    ) -> MiddlewareResult:
        # track_tool_action requires: tool_name, tool_args, success
        # At before_tool_call, we don't have success yet — record as True (optimistic).
        # after_tool_call can update if it failed.
        self._detector.track_tool_action(
            tool_call.function_name, tool_call.arguments, success=True
        )
        return MiddlewareResult.ok()

    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        # track_response expects a dict with "content" and optionally "tool_calls" keys
        last_response = ctx.metadata.get("last_response", {})
        if not last_response:
            return MiddlewareResult.ok()

        is_stuck, _confidence = self._detector.track_response(last_response)

        if is_stuck and not self._detector.can_attempt_recovery():
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message="Stuck recovery exhausted — force-advancing to next step.",
            )

        if is_stuck:
            self._detector.record_recovery_attempt()
            recovery = self._detector.get_recovery_prompt()
            return MiddlewareResult(
                signal=MiddlewareSignal.INJECT,
                message=recovery,
            )

        return MiddlewareResult.ok()
```

- [ ] **Step 3: Run tests, lint, commit**

```bash
cd backend && pytest tests/domain/services/agents/test_mw_stuck_detection.py -v && ruff check app/domain/services/agents/middleware_adapters/stuck_detection.py
```

```bash
cd backend && git add app/domain/services/agents/middleware_adapters/stuck_detection.py tests/domain/services/agents/test_mw_stuck_detection.py && git commit -m "feat(agents): add StuckDetectionMiddleware adapter

Wraps StuckDetector with before_tool_call and after_step hooks."
```

---

## Task 7: SecurityAssessmentMiddleware

**Files:**
- Create: `backend/app/domain/services/agents/middleware_adapters/security_assessment.py`
- Test: `backend/tests/domain/services/agents/test_mw_security_assessment.py`

Follow same TDD pattern as Task 5-6. Key behavior:
- `before_tool_call`: calls `self._assessor.assess_action(tool_call.function_name, tool_call.arguments)`
- `SecurityAssessor.assess_action()` returns `SecurityAssessment` dataclass
- If `assessment.blocked is True`, return `SKIP_TOOL` with `assessment.reason`
- Otherwise return `CONTINUE`
- Note: Current assessor always returns `blocked=False` (sandbox provides isolation), but the middleware should respect the `blocked` field for future-proofing

- [ ] **Step 1-4: Write test, implement, lint, commit**

```bash
git commit -m "feat(agents): add SecurityAssessmentMiddleware adapter"
```

---

## Task 8: EfficiencyMonitorMiddleware

Same TDD pattern. Key behavior:
- `after_tool_call`: calls `self._monitor.record(tool_call.function_name)`
- `before_step`: calls `self._monitor.check_efficiency()`, returns `INJECT` with nudge or `FORCE` on hard_stop

- [ ] **Step 1-4: Write test, implement, lint, commit**

```bash
git commit -m "feat(agents): add EfficiencyMonitorMiddleware adapter"
```

---

## Task 9: WallClockPressureMiddleware

Same TDD pattern. Key behavior — extracted from `base.py` `_get_wall_clock_pressure_level()`:
- `before_step`: checks `ctx.elapsed_seconds / ctx.wall_clock_budget`, returns `FORCE` at CRITICAL
- `before_tool_call`: blocks read-only tools at URGENT, blocks all non-write at CRITICAL

- [ ] **Step 1-4: Write test, implement, lint, commit**

```bash
git commit -m "feat(agents): add WallClockPressureMiddleware adapter"
```

---

## Task 10: Remaining Adapters (UrlFailureGuard, ErrorHandler, TokenBudget)

Same TDD pattern for each. Three small commits:

- [ ] **UrlFailureGuardMiddleware** — `before_tool_call` checks URL, `after_tool_call` records results
- [ ] **ErrorHandlerMiddleware** — `on_error` classifies via `ErrorHandler.classify_error()`
- [ ] **TokenBudgetMiddleware** — `before_step`/`before_model` check token budget ratio

```bash
git commit -m "feat(agents): add UrlFailureGuardMiddleware adapter"
git commit -m "feat(agents): add ErrorHandlerMiddleware adapter"
git commit -m "feat(agents): add TokenBudgetMiddleware adapter"
```

---

## Task 11: Wire Adapters into Factory

**Files:**
- Modify: `backend/app/domain/services/agents/agent_context_factory.py`
- Update: `backend/tests/domain/services/agents/test_agent_context_factory.py`

- [ ] **Step 1: Write failing test — factory creates pipeline with all 8 middleware**

```python
class TestFactoryRegistersAllMiddleware:
    def test_creates_all_middleware(self):
        factory = AgentContextFactory()
        ctx = factory.create(
            agent_id="test",
            session_id="test",
            tools=[],
            feature_flags={},
        )
        names = [mw.name for mw in ctx.middleware_pipeline.middleware]
        assert "wall_clock_pressure" in names
        assert "security_assessment" in names
        assert "hallucination_guard" in names
        assert "efficiency_monitor" in names
        assert "stuck_detection" in names
        assert "error_handler" in names
        assert len(names) >= 6  # At minimum these 6
```

- [ ] **Step 2: Update factory to register all adapters**
- [ ] **Step 3: Run tests, lint, commit**

```bash
git commit -m "feat(agents): wire all middleware adapters into AgentContextFactory"
```

---

## Task 12: Integrate Pipeline into BaseAgent (Backward Compatible)

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`

This is the highest-risk task. Changes must be backward compatible.

**IMPORTANT: Init ordering** — `_build_default_pipeline()` must be called AFTER the embedded services (`_stuck_detector`, `_hallucination_detector`, `_security_assessor`, `_efficiency_monitor`) are initialized in `__init__`. Place the pipeline construction at the END of `__init__`.

- [ ] **Step 1: Add `service_context` param to BaseAgent.__init__**

Add after `tool_result_store` param:
```python
service_context: "AgentServiceContext | None" = None,
```

Add to body:
```python
if service_context:
    self._pipeline = service_context.middleware_pipeline
else:
    self._pipeline = self._build_default_pipeline()
```

- [ ] **Step 2: Implement `_build_default_pipeline()`**

```python
def _build_default_pipeline(self) -> MiddlewarePipeline:
    """Build default middleware pipeline from existing embedded services.

    Backward compatible: reproduces identical behavior to current inline code.
    """
    from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline
    from app.domain.services.agents.middleware_adapters.hallucination_guard import HallucinationGuardMiddleware
    from app.domain.services.agents.middleware_adapters.stuck_detection import StuckDetectionMiddleware
    from app.domain.services.agents.middleware_adapters.security_assessment import SecurityAssessmentMiddleware
    from app.domain.services.agents.middleware_adapters.efficiency_monitor import EfficiencyMonitorMiddleware

    pipeline = MiddlewarePipeline()
    pipeline.use(SecurityAssessmentMiddleware(assessor=self._security_assessor))
    pipeline.use(HallucinationGuardMiddleware(detector=self._hallucination_detector))
    pipeline.use(EfficiencyMonitorMiddleware(monitor=self._efficiency_monitor))
    pipeline.use(StuckDetectionMiddleware(detector=self._stuck_detector))
    return pipeline
```

- [ ] **Step 3: Run ALL existing tests to verify nothing breaks**

```bash
cd backend && pytest tests/ -x --tb=short -q
```
Expected: ALL PASS (no behavioral change — pipeline wraps same services)

- [ ] **Step 4: Lint and commit**

```bash
cd backend && ruff check app/domain/services/agents/base.py && ruff format --check app/domain/services/agents/base.py
```

```bash
cd backend && git add app/domain/services/agents/base.py && git commit -m "feat(agents): integrate middleware pipeline into BaseAgent

Add service_context param (backward compatible).
Add _build_default_pipeline() from existing embedded services.
No behavioral change — pipeline wraps same services."
```

---

## Task 13: Integration Tests + Final Validation

- [ ] **Step 0: Add integration test for _build_default_pipeline and multi-hook sequence**

```python
# backend/tests/domain/services/agents/test_middleware_integration.py
"""Integration tests for middleware pipeline end-to-end."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.domain.services.agents.middleware import (
    MiddlewareContext, MiddlewareSignal, ToolCallInfo,
)
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.models.tool_result import ToolResult


class OrderTracker(BaseMiddleware):
    """Tracks hook call order across the full lifecycle."""
    def __init__(self, name_str: str):
        self._name = name_str
        self.calls: list[str] = []

    @property
    def name(self):
        return self._name

    async def before_step(self, ctx):
        self.calls.append(f"{self._name}:before_step")
        return super().before_step.__wrapped__(self, ctx) if hasattr(super().before_step, '__wrapped__') else await super().before_step(ctx)

    async def before_tool_call(self, ctx, tool_call):
        self.calls.append(f"{self._name}:before_tool:{tool_call.function_name}")
        return await super().before_tool_call(ctx, tool_call)

    async def after_tool_call(self, ctx, tool_call, result):
        self.calls.append(f"{self._name}:after_tool:{tool_call.function_name}")
        return await super().after_tool_call(ctx, tool_call, result)

    async def after_step(self, ctx):
        self.calls.append(f"{self._name}:after_step")
        return await super().after_step(ctx)


class TestFullLifecycleSequence:
    @pytest.mark.asyncio
    async def test_multi_hook_sequence(self):
        """Verify correct hook ordering through a realistic agent iteration."""
        t1 = OrderTracker("security")
        t2 = OrderTracker("hallucination")
        pipeline = MiddlewarePipeline([t1, t2])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        tool = ToolCallInfo(call_id="c1", function_name="file_read", arguments={})
        result = ToolResult(success=True, message="ok")

        # Simulate one iteration
        await pipeline.run_before_step(ctx)
        await pipeline.run_before_tool_call(ctx, tool)
        await pipeline.run_after_tool_call(ctx, tool, result)
        await pipeline.run_after_step(ctx)

        # Verify ordering
        all_calls = t1.calls + t2.calls
        assert "security:before_step" in t1.calls
        assert "hallucination:before_step" in t2.calls
        assert "security:before_tool:file_read" in t1.calls
        assert "security:after_tool:file_read" in t1.calls
        assert "security:after_step" in t1.calls
```

```bash
cd backend && pytest tests/domain/services/agents/test_middleware_integration.py -v
```

```bash
cd backend && git add tests/domain/services/agents/test_middleware_integration.py && git commit -m "test(agents): add middleware pipeline integration tests"
```

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && conda activate pythinker && pytest tests/ --tb=short -q
```

- [ ] **Step 2: Run lint and format check**

```bash
cd backend && ruff check . && ruff format --check .
```

- [ ] **Step 3: Verify no regressions in agent tests specifically**

```bash
cd backend && pytest tests/domain/services/agents/ tests/unit/agents/ -v --tb=short
```

- [ ] **Step 4: Count LOC reduction (informational)**

```bash
wc -l backend/app/domain/services/agents/middleware.py backend/app/domain/services/agents/base_middleware.py backend/app/domain/services/agents/middleware_pipeline.py backend/app/domain/services/agents/agent_context.py backend/app/domain/services/agents/agent_context_factory.py backend/app/domain/services/agents/middleware_adapters/*.py
```

---

## Summary

| Task | Description | Est. Minutes |
|------|-------------|-------------|
| 1 | Core data types (middleware.py) | 10 |
| 2 | BaseMiddleware no-op defaults | 5 |
| 3 | MiddlewarePipeline | 15 |
| 4 | AgentServiceContext + Factory | 10 |
| 5 | HallucinationGuardMiddleware | 15 |
| 6 | StuckDetectionMiddleware | 10 |
| 7 | SecurityAssessmentMiddleware | 10 |
| 8 | EfficiencyMonitorMiddleware | 10 |
| 9 | WallClockPressureMiddleware | 10 |
| 10 | Remaining adapters (3x) | 20 |
| 11 | Wire into factory | 10 |
| 12 | Integrate into BaseAgent | 15 |
| 13 | Final validation | 10 |
