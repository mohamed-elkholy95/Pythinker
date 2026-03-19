# Agent Middleware Pipeline Architecture — Design Spec

**Date:** 2026-03-19
**Status:** Approved
**Scope:** Backend agent system (`backend/app/domain/services/agents/`)

---

## 1. Problem Statement

Pythinker's `BaseAgent` class (2,990 LOC) is a **god class** that handles 7+ orthogonal concerns:
tool execution, token management, error recovery, hallucination detection, stuck detection,
efficiency monitoring, security assessment, and URL failure guarding.

**Consequences:**
- 30+ instance variables managing unrelated state
- 7+ embedded service objects hardcoded in `__init__`
- Multiple static global singletons across the agents package (e.g., `get_compliance_gates()`, `get_tool_profiler()`, `get_tool_tracer()`, `get_toolset_manager()`) risk cross-session contamination
- Testing requires 7+ mocks per test case
- Adding new behavior requires modifying the god class
- No extension points for custom agent behaviors

## 2. Design Goals

1. **Decompose cross-cutting concerns** into composable, independently testable middleware
2. **Define clear service contracts** via Python `Protocol` interfaces
3. **Eliminate static global singletons** across the agents package with session-scoped service containers
4. **Preserve backward compatibility** — existing tests must pass without modification
5. **Align with 2026 industry patterns** (Microsoft Agent Framework, LangChain, Claude Agent SDK)

## 3. Industry Validation

### 3.1 Microsoft Agent Framework Pipeline (2026)
- Agent builds pipeline through class composition: `AgentMiddlewareLayer` + `AgentTelemetryLayer` + `RawAgent`
- Middleware intercepts every call to `run()`, allowing inspection/modification of inputs and outputs
- **Applied:** Our `MiddlewarePipeline` follows this exact layered composition pattern

### 3.2 LangChain Callback/Middleware System (2026)
- LangChain uses `BaseCallbackHandler` with hooks like `on_llm_start`, `on_tool_start`, `on_tool_end`
- Additionally, `RunnableConfig` supports middleware-style `before_model`/`after_model` interception
- Multiple middleware compose automatically (first defined = outermost layer)
- Middleware can call handler multiple times for retry logic, skip to short-circuit, or modify request/response
- **Applied:** We adopt the `before_model`/`after_model` lifecycle points (not just `before_step`/`after_step`)

### 3.3 Claude Agent SDK Hooks (2026)
- Lifecycle hooks via `hooks` parameter with `Tool.before_invoke` and `Tool.after_invoke` callbacks
- In-process tool servers (no separate processes)
- **Applied:** Our hook naming is inspired by Claude Agent SDK's lifecycle approach

### 3.4 AG-UI Protocol Middleware (2026)
- Middleware forms a chain: first receives input, can modify before passing to next
- Five core capabilities: inspection, transformation, filtering, metadata injection, monitoring
- **Applied:** Our `MiddlewareSignal` enum provides these capabilities

### 3.5 Python Best Practices (Context7 Validated)
- **Pydantic v2:** Use `@dataclass(frozen=True, slots=True)` for immutable value objects (results, info); use `@dataclass(slots=True)` (mutable) for shared state containers like `MiddlewareContext`; reserve Pydantic `BaseModel` for API boundary validation (Context7: pydantic.dev)
- **FastAPI DI:** Yield-based lifecycle management; `Annotated[T, Depends(factory)]` pattern (Context7: fastapi.tiangolo.com)
- **Frozen dataclasses:** Prevent accidental mutation; hashable for use in sets/dicts (Context7: pydantic.dev/dataclasses)
- **`@field_validator` must be `@classmethod`** for any Pydantic models (project convention)

## 4. Architecture

### 4.1 Lifecycle Hook Points

```
User Request
    |
    v
[before_execution]  ← Pipeline-level (once per execute() call)
    |
    v
┌── Iteration Loop ──────────────────────────────────────┐
│                                                         │
│   [before_step]      ← Before each iteration           │
│       |                                                 │
│       v                                                 │
│   [before_model]     ← Before LLM call                 │
│       |                                                 │
│       v                                                 │
│   LLM.call_with_tools()                                │
│       |                                                 │
│       v                                                 │
│   [after_model]      ← After LLM response              │
│       |                                                 │
│       v                                                 │
│   For each tool_call:                                   │
│       [before_tool_call]  ← Before tool execution       │
│           |                                             │
│           v                                             │
│       tool.invoke_function()                            │
│           |                                             │
│           v                                             │
│       [after_tool_call]   ← After tool execution        │
│                                                         │
│   [after_step]       ← After processing all tool calls  │
│                                                         │
└── End Iteration ───────────────────────────────────────┘
    |
    v
[after_execution]  ← Pipeline-level (once per execute() call)
    |
    v
[on_error]         ← On any exception during execution
```

### 4.2 Core Protocol

**File:** `backend/app/domain/services/agents/middleware.py`

```python
"""Agent Middleware Protocol and data types.

Context7 validated:
- @dataclass(frozen=True, slots=True) for immutable containers (pydantic.dev)
- Protocol + @runtime_checkable for structural subtyping (typing docs)
- StrEnum for Python 3.11+ string enums (python docs)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.domain.models.event import BaseEvent
from app.domain.models.tool_result import ToolResult


class MiddlewareSignal(StrEnum):
    """Control signals returned by middleware to influence execution flow.

    CONTINUE  — Proceed normally (default)
    SKIP_TOOL — Skip this tool call (blocked by security/guard)
    INJECT    — Inject a correction/nudge message into conversation
    FORCE     — Force-advance to next step (stuck/hallucination cap)
    ABORT     — Abort the current execution entirely
    """
    CONTINUE = "continue"
    SKIP_TOOL = "skip_tool"
    INJECT = "inject"
    FORCE = "force"
    ABORT = "abort"


@dataclass(slots=True)
class MiddlewareContext:
    """Mutable shared context passed through the middleware chain.

    Replaces the 30+ instance variables scattered across BaseAgent.
    Mutable (not frozen) because middleware writes to it.
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

    # Flow-control state (previously on BaseAgent)
    step_start_time: float = 0.0
    stuck_recovery_exhausted: bool = False

    # Accumulator for middleware-injected messages
    injected_messages: list[dict[str, Any]] = field(default_factory=list)

    # Accumulator for middleware-emitted SSE events
    emitted_events: list[BaseEvent] = field(default_factory=list)

    # Metadata bag for inter-middleware communication
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
    def ok() -> "MiddlewareResult":
        """Convenience factory for CONTINUE result."""
        return MiddlewareResult()


@runtime_checkable
class AgentMiddleware(Protocol):
    """Protocol for agent execution middleware.

    Implement any subset of hooks. Unimplemented hooks should return
    MiddlewareResult.ok() (CONTINUE signal).

    Industry alignment:
    - Microsoft Agent Framework: AgentMiddlewareLayer
    - LangChain: AgentMiddleware (before_model, after_model, wrap_tool_call)
    - Claude Agent SDK: before_tool_call, after_tool_call, on_error
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

### 4.3 Base Middleware (No-Op Defaults)

**File:** `backend/app/domain/services/agents/base_middleware.py`

```python
"""Base middleware with no-op defaults for all hooks.

Subclass and override only the hooks you need. Matches LangChain pattern
where middleware only implements what it cares about.
"""

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

    async def after_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult:
        return MiddlewareResult.ok()
```

### 4.4 Middleware Pipeline

**File:** `backend/app/domain/services/agents/middleware_pipeline.py`

```python
"""Pipeline that chains middleware in registration order.

Chain of Responsibility: each middleware can signal to short-circuit,
inject messages, or force-advance the step. First non-CONTINUE signal wins
for before_* hooks. All middleware run for after_* hooks (last signal wins).

Industry alignment: Microsoft Agent Framework pipeline composition,
LangChain "first in list = outermost layer" semantics.
"""
import logging
import time

logger = logging.getLogger(__name__)


class MiddlewarePipeline:
    """Executes middleware hooks in registration order."""

    def __init__(self, middleware: list[AgentMiddleware] | None = None):
        self._middleware: list[AgentMiddleware] = list(middleware or [])

    def use(self, mw: AgentMiddleware) -> "MiddlewarePipeline":
        """Register middleware (fluent API). Returns self for chaining."""
        self._middleware.append(mw)
        return self

    @property
    def middleware(self) -> list[AgentMiddleware]:
        """Read-only access to registered middleware."""
        return list(self._middleware)

    async def _run_first_wins(
        self, hook_name: str, *args, **kwargs
    ) -> MiddlewareResult:
        """Run hook on all middleware. First non-CONTINUE signal wins."""
        for mw in self._middleware:
            hook = getattr(mw, hook_name, None)
            if hook is None:
                continue
            try:
                result = await hook(*args, **kwargs)
                if result.signal != MiddlewareSignal.CONTINUE:
                    logger.debug(
                        "Middleware %s.%s returned %s",
                        mw.name, hook_name, result.signal,
                    )
                    return result
            except Exception:
                logger.exception(
                    "Middleware %s.%s raised exception (swallowed)",
                    mw.name, hook_name,
                )
        return MiddlewareResult.ok()

    async def _run_all_last_wins(
        self, hook_name: str, *args, **kwargs
    ) -> MiddlewareResult:
        """Run hook on all middleware. Last non-CONTINUE signal wins."""
        final = MiddlewareResult.ok()
        for mw in self._middleware:
            hook = getattr(mw, hook_name, None)
            if hook is None:
                continue
            try:
                result = await hook(*args, **kwargs)
                if result.signal != MiddlewareSignal.CONTINUE:
                    final = result
            except Exception:
                logger.exception(
                    "Middleware %s.%s raised exception (swallowed)",
                    mw.name, hook_name,
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
        self, ctx: MiddlewareContext, response: dict
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

### 4.5 Middleware Adapters (8 implementations)

Each adapter wraps an **existing service** — no logic rewrite.

**Directory:** `backend/app/domain/services/agents/middleware_adapters/`

| File | Wraps | Primary Hooks | Estimated LOC |
|------|-------|---------------|---------------|
| `stuck_detection.py` | `StuckDetector` | `before_tool_call`, `after_step` | ~80 |
| `hallucination_guard.py` | `ToolHallucinationDetector` | `before_step`, `before_tool_call` | ~100 |
| `security_assessment.py` | `SecurityAssessor` | `before_tool_call` | ~60 |
| `efficiency_monitor.py` | `ToolEfficiencyMonitor` | `before_step`, `after_tool_call` | ~80 |
| `url_failure_guard.py` | `UrlFailureGuard` | `before_tool_call`, `after_tool_call` | ~70 |
| `error_handler.py` | `ErrorHandler` | `on_error` | ~60 |
| `wall_clock_pressure.py` | (extracted logic) | `before_step`, `before_tool_call` | ~80 |
| `token_budget.py` | `TokenBudgetManager` | `before_step`, `before_model` | ~70 |

**Example — HallucinationGuardMiddleware:**

```python
"""Middleware adapter for ToolHallucinationDetector.

Intercepts tool calls to detect hallucinated tool names and parameters.
Injects correction prompts when hallucination loops are detected.
"""
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
from app.domain.services.agents.middleware import (
    MiddlewareContext, MiddlewareResult, MiddlewareSignal, ToolCallInfo,
)


class HallucinationGuardMiddleware(BaseMiddleware):
    """Detects hallucinated tool names/params and injects corrections."""

    MAX_HALLUCINATIONS_PER_STEP: int = 3

    def __init__(self, detector: ToolHallucinationDetector):
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
                metadata={"error_type": validation.error_type, "suggestions": validation.suggestions},
            )

        return MiddlewareResult.ok()
```

### 4.6 Agent Service Context (replaces static globals)

**File:** `backend/app/domain/services/agents/agent_context.py`

```python
"""Session-scoped service container.

Replaces 8+ static global singletons with explicitly constructed,
session-scoped instances. Thread-safe by construction (one per session).

Context7 validated: dataclass for simple data containers (pydantic.dev).
"""
from dataclasses import dataclass

from app.domain.external.observability import MetricsPort
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


@dataclass(slots=True)
class AgentServiceContext:
    """All services needed by an agent, scoped to a single session.

    Holds both the pipeline and individual middleware references
    for observability (e.g., diagnostics endpoint needs stuck_detector.get_stats()).
    """
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

### 4.7 Agent Context Factory

**File:** `backend/app/domain/services/agents/agent_context_factory.py`

```python
"""Factory that builds session-scoped AgentServiceContext.

Reads feature flags to decide which middleware to register.
Middleware order matters: earlier middleware runs first (outermost layer).

Order rationale:
1. WallClockPressure — hard budget limits checked first (cheapest check)
2. TokenBudget — token limits checked early
3. SecurityAssessment — block dangerous actions before execution
4. HallucinationGuard — catch hallucinated tools before execution
5. EfficiencyMonitor — detect analysis paralysis patterns
6. UrlFailureGuard — skip known-failed URLs
7. StuckDetection — detect stuck loops on responses
8. ErrorHandler — classify and handle errors last (catches everything)
"""


class AgentContextFactory:
    """Builds session-scoped service contexts with configured middleware."""

    def create(
        self,
        agent_id: str,
        session_id: str,
        tools: list,
        research_mode: str | None = None,
        feature_flags: dict[str, bool] | None = None,
    ) -> AgentServiceContext:
        flags = feature_flags or self._load_feature_flags()
        pipeline = MiddlewarePipeline()

        # Always-on middleware (ordered by priority — cheapest/most critical first)
        pipeline.use(WallClockPressureMiddleware())
        pipeline.use(TokenBudgetMiddleware())
        pipeline.use(SecurityAssessmentMiddleware())
        pipeline.use(HallucinationGuardMiddleware(
            detector=ToolHallucinationDetector(self._extract_tool_names(tools))
        ))
        pipeline.use(EfficiencyMonitorMiddleware(
            research_mode=research_mode,
        ))
        pipeline.use(UrlFailureGuardMiddleware())
        pipeline.use(StuckDetectionMiddleware())
        pipeline.use(ErrorHandlerMiddleware())

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

    @staticmethod
    def _extract_tool_names(tools: list) -> list[str]:
        names = []
        for tool in tools:
            for schema in (tool.get_tools() if hasattr(tool, "get_tools") else []):
                name = schema.get("function", {}).get("name", "")
                if name:
                    names.append(name)
        return names
```

## 5. BaseAgent Integration

### 5.1 Constructor Changes

```python
# BEFORE (current):
class BaseAgent:
    def __init__(self, agent_id, agent_repository, llm, json_parser,
                 tools=None, state_manifest=None, circuit_breaker=None,
                 feature_flags=None, cancel_token=None, tool_result_store=None):
        # ... 30+ instance variables including 7 hardcoded services

# AFTER (new optional param, backward compatible):
class BaseAgent:
    def __init__(self, agent_id, agent_repository, llm, json_parser,
                 tools=None, state_manifest=None, circuit_breaker=None,
                 feature_flags=None, cancel_token=None, tool_result_store=None,
                 service_context: AgentServiceContext | None = None):  # NEW
        # Core properties (unchanged)
        ...
        # Middleware pipeline (new)
        if service_context:
            self._pipeline = service_context.middleware_pipeline
            self._metrics = service_context.metrics
        else:
            # Backward-compatible default pipeline
            self._pipeline = self._build_default_pipeline()

        # KEEP existing services during migration (Phase 2-3)
        # REMOVE after full migration (Phase 4)
```

### 5.2 Execute Loop Refactored

The `_execute_inner` method goes from ~400 LOC with scattered conditionals to ~80 LOC with clean pipeline calls:

```python
async def _execute_inner(self, request, format=None):
    ctx = MiddlewareContext(
        agent_id=self._agent_id,
        session_id=getattr(self, "_session_id", ""),
        wall_clock_budget=self._get_wall_clock_budget(),
        active_phase=self._active_phase,
        research_depth=getattr(self, "_research_depth", None),
    )

    # Pipeline-level init
    await self._pipeline.run_before_execution(ctx)
    ctx.step_start_time = time.monotonic()

    message = await self.ask(request, format)

    try:
        while ctx.iteration_count < self.max_iterations:
            if not message.get("tool_calls"):
                break

            ctx.elapsed_seconds = time.monotonic() - ctx.step_start_time

            # ── Before Step ──
            step_result = await self._pipeline.run_before_step(ctx)
            if step_result.signal == MiddlewareSignal.FORCE:
                ctx.stuck_recovery_exhausted = True
                break
            if step_result.signal == MiddlewareSignal.INJECT:
                message = await self.ask_with_messages(
                    [{"role": "user", "content": step_result.message}]
                )
                continue

            # ── Before Model (token budget, complexity checks) ──
            model_pre = await self._pipeline.run_before_model(ctx)
            if model_pre.signal == MiddlewareSignal.FORCE:
                break

            # ── Process Tool Calls ──
            tool_responses = []
            for tc in message["tool_calls"]:
                tool_info = ToolCallInfo(
                    call_id=tc.get("id", ""),
                    function_name=tc["function"]["name"],
                    arguments=tc["function"].get("arguments", {}),
                )

                # Before tool call (security, hallucination, URL guard)
                pre = await self._pipeline.run_before_tool_call(ctx, tool_info)
                if pre.signal == MiddlewareSignal.SKIP_TOOL:
                    tool_responses.append(self._build_skip_response(tool_info, pre.message))
                    continue

                # Execute tool (existing logic, unchanged)
                result = await self._execute_tool_safely(tc)

                # After tool call (tracking, metrics, URL logging)
                await self._pipeline.run_after_tool_call(ctx, tool_info, result)

                tool_responses.append(self._build_tool_response(tc, result))
                # Yield tool events (existing logic)
                ...

            # Continue conversation with tool results
            message = await self.ask_with_messages(tool_responses)

            # ── After Model ──
            await self._pipeline.run_after_model(ctx, message)

            # ── After Step (stuck detection on response) ──
            after = await self._pipeline.run_after_step(ctx)
            if after.signal == MiddlewareSignal.FORCE:
                ctx.stuck_recovery_exhausted = True
                break
            if after.signal == MiddlewareSignal.INJECT:
                message = await self.ask_with_messages(
                    [{"role": "user", "content": after.message}]
                )

            ctx.iteration_count += 1
            ctx.step_iteration_count += 1

            # Emit any middleware-generated events
            for event in ctx.emitted_events:
                yield event
            ctx.emitted_events.clear()

    except Exception as exc:
        # ── On Error (error classification, circuit breaking) ──
        error_result = await self._pipeline.run_on_error(ctx, exc)
        if error_result.signal == MiddlewareSignal.ABORT:
            raise
        # If middleware handled it, log and continue to cleanup
        logger.exception("Agent execution error handled by middleware")
    finally:
        # Pipeline-level cleanup (always runs)
        await self._pipeline.run_after_execution(ctx)

    # Sync flow-control state back to agent for callers
    self._stuck_recovery_exhausted = ctx.stuck_recovery_exhausted
```

## 6. Migration Strategy (Backward Compatible)

### Phase 1: Foundation (No behavior change)
- Add new files: `middleware.py`, `base_middleware.py`, `middleware_pipeline.py`, `agent_context.py`, `agent_context_factory.py`
- Add `middleware_adapters/` directory with `__init__.py`
- Add `_build_default_pipeline()` to BaseAgent (builds pipeline from existing embedded services)
- Add `service_context` optional param to BaseAgent.__init__
- **All existing tests pass unchanged** — default pipeline reproduces identical behavior

### Phase 2: Adapter Implementation
- Create 8 middleware adapter classes (thin wrappers around existing services)
- Wire into `_build_default_pipeline()`
- Add comprehensive unit tests for each middleware (independently testable)
- **All existing tests pass unchanged** — adapters delegate to same services

### Phase 3: Execute Loop Refactoring
- Replace inline service calls in `_execute_inner()` with `self._pipeline.run_*()` calls
- Remove 15+ tracking instance variables from `__init__` (moved to MiddlewareContext)
- Keep `_build_default_pipeline()` for callers not yet using AgentContextFactory
- **All existing tests pass unchanged** — behavior identical, just routed through pipeline

### Phase 4: Global Singleton Elimination
- Replace 8 static `get_*()` singletons with session-scoped instances via AgentContextFactory
- Update PlanActFlow to create AgentServiceContext and pass to agents
- Deprecate global `get_*()` functions (log warning, delegate to factory)
- **Integration tests updated** — direct singleton users migrate to context injection

## 7. Testing Strategy

### Unit Tests (per middleware, ~50 tests each)
```python
# Example: test_hallucination_guard_middleware.py
async def test_hallucinated_tool_returns_skip_signal():
    detector = ToolHallucinationDetector(["file_read", "file_write"])
    mw = HallucinationGuardMiddleware(detector=detector)
    ctx = MiddlewareContext(agent_id="test", session_id="test")
    tool = ToolCallInfo(call_id="1", function_name="nonexistent_tool", arguments={})

    result = await mw.before_tool_call(ctx, tool)

    assert result.signal == MiddlewareSignal.SKIP_TOOL
    assert "nonexistent_tool" in (result.metadata.get("hallucinated_tool", ""))
```

### Pipeline Integration Tests
```python
# Verify middleware ordering
async def test_first_non_continue_signal_wins():
    pipeline = MiddlewarePipeline()
    pipeline.use(AlwaysContinueMiddleware())
    pipeline.use(AlwaysSkipMiddleware())  # This should win
    pipeline.use(AlwaysForceMiddleware())  # Never reached

    result = await pipeline.run_before_tool_call(ctx, tool)
    assert result.signal == MiddlewareSignal.SKIP_TOOL
```

### Backward Compatibility Tests
- All existing `test_execution.py`, `test_base_agent.py` tests pass without modification
- `_build_default_pipeline()` produces identical behavior to current inline code

## 8. File Inventory

| Action | File | Est. LOC |
|--------|------|----------|
| NEW | `domain/services/agents/middleware.py` | ~130 |
| NEW | `domain/services/agents/base_middleware.py` | ~50 |
| NEW | `domain/services/agents/middleware_pipeline.py` | ~120 |
| NEW | `domain/services/agents/agent_context.py` | ~30 |
| NEW | `domain/services/agents/agent_context_factory.py` | ~80 |
| NEW | `domain/services/agents/middleware_adapters/__init__.py` | ~20 |
| NEW | `domain/services/agents/middleware_adapters/stuck_detection.py` | ~80 |
| NEW | `domain/services/agents/middleware_adapters/hallucination_guard.py` | ~100 |
| NEW | `domain/services/agents/middleware_adapters/security_assessment.py` | ~60 |
| NEW | `domain/services/agents/middleware_adapters/efficiency_monitor.py` | ~80 |
| NEW | `domain/services/agents/middleware_adapters/url_failure_guard.py` | ~70 |
| NEW | `domain/services/agents/middleware_adapters/error_handler.py` | ~60 |
| NEW | `domain/services/agents/middleware_adapters/wall_clock_pressure.py` | ~80 |
| NEW | `domain/services/agents/middleware_adapters/token_budget.py` | ~70 |
| MODIFY | `domain/services/agents/base.py` | -400, +100 |
| MODIFY | `domain/services/agents/execution.py` | -100, +30 |
| MODIFY | `domain/services/flows/plan_act.py` | +40 |
| NEW | `tests/domain/services/agents/test_middleware.py` | ~200 |
| NEW | `tests/domain/services/agents/test_middleware_pipeline.py` | ~150 |
| NEW | `tests/domain/services/agents/test_middleware_adapters.py` | ~400 |
| NEW | `tests/domain/services/agents/test_agent_context_factory.py` | ~100 |

**Total: ~2,500 LOC new, ~500 LOC removed from BaseAgent**

## 9. Success Metrics

| Metric | Before | After |
|--------|--------|-------|
| BaseAgent LOC | 2,990 | ~2,100 |
| Instance vars in __init__ | 30+ | ~15 |
| Mocks needed per test | 7+ | 1-2 |
| Time to add new behavior | Modify god class | Add middleware file |
| Static global singletons | 8+ | 0 |
| Middleware independently testable | N/A | 8/8 |

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Behavioral regression in execute loop | Medium | High | Phase 2-3 run both paths in parallel; assert identical results |
| Middleware ordering bugs | Low | Medium | Explicit ordering in factory; integration tests verify priority |
| Performance regression from pipeline overhead | Low | Low | ~0.1ms per hook call (Python function dispatch); negligible vs. LLM latency |
| Existing tests break | Low | High | Each phase preserves backward compat; `_build_default_pipeline()` fallback |

## 11. Non-Goals

- **Not** rewriting existing service logic (StuckDetector, SecurityAssessor, etc.)
- **Not** changing the LLM interface or tool execution mechanics
- **Not** modifying the event streaming (SSE) architecture
- **Not** changing the frontend or API layer
- **Not** adding new agent capabilities — this is a structural refactoring only
