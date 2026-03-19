# Agent Middleware Pipeline Phase 3-4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route BaseAgent's `_execute_inner()` loop through the middleware pipeline, replacing 100+ LOC of inline service calls with clean pipeline hook calls; wire PlanActFlow to create and pass `AgentServiceContext`.

**Architecture:** Surgically replace the top-level loop concerns (wall clock pressure, hallucination loop detection, iteration budget, stuck detection on responses) with `self._pipeline.run_*()` calls. Keep tool-level interception (in `_execute_single_tool`, `_execute_parallel_tool`) as-is for now — those are tightly coupled with tool event emission and will be migrated incrementally in a future plan. Wire `PlanActFlow` to create `AgentServiceContext` and pass it to agents.

**Tech Stack:** Python 3.12+, existing middleware infrastructure from Phase 1-2

**Spec:** `docs/superpowers/specs/2026-03-19-agent-middleware-pipeline-design.md` (Sections 5.2, 6.3, 6.4)
**Depends on:** Phase 1-2 plan (`docs/superpowers/plans/2026-03-19-agent-middleware-pipeline.md`) — completed

---

## Scope

### In Scope (Phase 3)
- Replace wall clock pressure logic in `_execute_inner()` (~90 LOC) with `WallClockPressureMiddleware` via pipeline
- Replace hallucination loop detection at top of main loop (~20 LOC) with pipeline `before_step`
- Replace stuck detection on responses in `_execute_step_safely()` (~50 LOC) with pipeline `after_step`
- Add `try/except` with `pipeline.run_on_error()` to execute loop
- Store `last_response` in `MiddlewareContext.metadata` for `StuckDetectionMiddleware`
- Remove ~15 tracking variables from `_execute_inner` that move to `MiddlewareContext`

### In Scope (Phase 4)
- Wire `PlanActFlow` to create `AgentServiceContext` and pass to agents
- Pass research_mode through context factory for correct efficiency thresholds

### Deferred (Future Plan)
- Tool-level interception in `_execute_single_tool` / `_execute_parallel_tool` (security assessment, URL guard, efficiency recording per-tool) — these are deeply coupled with tool event emission and parallel execution
- Elimination of all static global singletons (incremental)

---

## File Structure

### Modified Files
| File | Change |
|------|--------|
| `backend/app/domain/services/agents/base.py` | Replace inline wall-clock/hallucination/stuck/budget logic with pipeline calls in `_execute_inner()` and `_execute_step_safely()` |
| `backend/app/domain/services/flows/plan_act.py` | Create `AgentServiceContext` via factory, pass to planner + executor |
| `backend/app/domain/services/agents/middleware_adapters/wall_clock_pressure.py` | Add `_add_to_memory` callback support for advisory/urgent messages |

### New Test Files
| File | Tests |
|------|-------|
| `backend/tests/domain/services/agents/test_base_middleware_routing.py` | Verify pipeline is called at each lifecycle point in execute loop |

---

## Task 1: Add MiddlewareContext Population to Execute Loop

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`
- Test: `backend/tests/domain/services/agents/test_base_middleware_routing.py`

The first step is non-destructive: create the `MiddlewareContext` at the start of `_execute_inner()` and populate it each iteration, without removing any existing code yet. This proves the pipeline fires correctly alongside the existing logic.

- [ ] **Step 1: Write test that verifies MiddlewareContext is created and populated**

```python
# backend/tests/domain/services/agents/test_base_middleware_routing.py
"""Tests for middleware pipeline routing in BaseAgent execute loop."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.domain.services.agents.middleware import (
    MiddlewareContext, MiddlewareResult, MiddlewareSignal,
)
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline
from app.domain.services.agents.base_middleware import BaseMiddleware


class SpyMiddleware(BaseMiddleware):
    """Records all hook calls with their context state."""

    def __init__(self):
        self.before_execution_calls: list[MiddlewareContext] = []
        self.before_step_calls: list[MiddlewareContext] = []
        self.after_step_calls: list[MiddlewareContext] = []

    @property
    def name(self):
        return "spy"

    async def before_execution(self, ctx):
        self.before_execution_calls.append(ctx)
        return MiddlewareResult.ok()

    async def before_step(self, ctx):
        self.before_step_calls.append(ctx)
        return MiddlewareResult.ok()

    async def after_step(self, ctx):
        self.after_step_calls.append(ctx)
        return MiddlewareResult.ok()


class TestMiddlewareContextPopulation:
    """Verify _execute_inner creates and populates MiddlewareContext."""

    def test_base_agent_has_pipeline(self):
        """BaseAgent should have a _pipeline attribute after construction."""
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent(
            agent_id="test",
            agent_repository=MagicMock(),
            llm=MagicMock(),
            json_parser=MagicMock(),
            tools=[],
        )
        assert hasattr(agent, "_pipeline")
        assert isinstance(agent._pipeline, MiddlewarePipeline)
        # Default pipeline should have 4 middleware (from _build_default_pipeline)
        assert len(agent._pipeline.middleware) == 4
```

- [ ] **Step 2: Run test to verify it passes (this tests existing Phase 1-2 code)**

```bash
cd backend && conda activate pythinker && pytest tests/domain/services/agents/test_base_middleware_routing.py -v -p no:cov -o addopts=
```

- [ ] **Step 3: Commit test file**

```bash
cd backend && git add tests/domain/services/agents/test_base_middleware_routing.py && git commit -m "test(agents): add middleware routing tests for BaseAgent"
```

---

## Task 2: Replace Wall Clock Pressure in _execute_inner

This is the biggest LOC savings (~90 lines). The wall clock pressure logic (lines 1663-1754 of base.py) checks elapsed time, sends advisory/urgent/critical messages, and blocks tools. This maps directly to `WallClockPressureMiddleware.before_step()` + `before_tool_call()`.

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:1593-1755`
- Modify: `backend/app/domain/services/agents/middleware_adapters/wall_clock_pressure.py`

- [ ] **Step 1: Enhance WallClockPressureMiddleware to emit advisory/urgent messages via ctx**

The current middleware only returns signals. It needs to also store advisory messages in `ctx.injected_messages` for the execute loop to inject them as memory messages. Update `wall_clock_pressure.py`:

```python
# Add to before_step, after the CRITICAL check:
async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
    level = self._get_pressure_level(ctx)
    if level == "CRITICAL":
        return MiddlewareResult(
            signal=MiddlewareSignal.FORCE,
            message="Wall-clock CRITICAL (90%+). Conclude now.",
            metadata={"pressure_level": level},
        )
    if level == "URGENT":
        return MiddlewareResult(
            signal=MiddlewareSignal.INJECT,
            message=(
                f"STEP TIME URGENT: 75% of budget used ({ctx.elapsed_seconds:.0f}s of "
                f"{ctx.wall_clock_budget:.0f}s). Read-only tools are now BLOCKED. "
                f"You MUST finalize your output immediately."
            ),
            metadata={"pressure_level": level},
        )
    if level == "ADVISORY":
        # Advisory is informational — inject as memory but don't interrupt
        ctx.injected_messages.append({
            "role": "user",
            "content": (
                f"STEP TIME ADVISORY: You have used 50% of the step time budget "
                f"({ctx.elapsed_seconds:.0f}s of {ctx.wall_clock_budget:.0f}s). "
                f"Begin wrapping up research and focus on writing output."
            ),
        })
        return MiddlewareResult.ok()
    return MiddlewareResult.ok()
```

- [ ] **Step 2: In base.py `_execute_inner`, add MiddlewareContext creation and wall_clock_budget**

At the top of `_execute_inner` (after line 1598), add:

```python
from app.domain.services.agents.middleware import MiddlewareContext, MiddlewareSignal
import time as _time

# Create middleware context for this execution
_mw_ctx = MiddlewareContext(
    agent_id=self._agent_id,
    session_id=getattr(self, "_session_id", ""),
    active_phase=self._active_phase,
    research_depth=getattr(self, "_research_depth", None),
)
_mw_ctx.step_start_time = _time.monotonic()

# Compute wall clock budget
from app.core.config import get_settings as _get_settings
_mw_settings = _get_settings()
_depth = getattr(self, "_research_depth", None)
if _depth == "QUICK":
    _mw_ctx.wall_clock_budget = getattr(_mw_settings, "step_budget_quick_seconds", 300.0)
elif _depth == "DEEP":
    _mw_ctx.wall_clock_budget = getattr(_mw_settings, "step_budget_deep_seconds", 900.0)
elif _depth == "STANDARD":
    _mw_ctx.wall_clock_budget = getattr(_mw_settings, "step_budget_standard_seconds", 600.0)
else:
    _mw_ctx.wall_clock_budget = getattr(_mw_settings, "max_step_wall_clock_seconds", 600.0)

# Run before_execution
await self._pipeline.run_before_execution(_mw_ctx)
```

- [ ] **Step 3: Inside the main loop, update `_mw_ctx.elapsed_seconds` and call `before_step`**

Replace the wall clock pressure block (lines 1663-1754) with:

```python
# Update middleware context timing
_mw_ctx.elapsed_seconds = _time.monotonic() - _mw_ctx.step_start_time
_mw_ctx.iteration_count = int(iteration_spent)
_mw_ctx.step_iteration_count = step_iteration_count

# ── Wall clock + budget checks via middleware pipeline ──
_step_result = await self._pipeline.run_before_step(_mw_ctx)
if _step_result.signal == MiddlewareSignal.FORCE:
    logger.warning("Middleware before_step returned FORCE: %s", _step_result.message)
    self._stuck_recovery_exhausted = True
    break
if _step_result.signal == MiddlewareSignal.INJECT:
    logger.info("Middleware before_step injecting message")
    await self._add_to_memory([{"role": "user", "content": _step_result.message}])
    graceful_completion_requested = True
    wall_clock_pressure_active = _step_result.metadata.get("pressure_level")

# Inject any advisory messages from middleware context
for _inj_msg in _mw_ctx.injected_messages:
    await self._add_to_memory([_inj_msg])
_mw_ctx.injected_messages.clear()
```

- [ ] **Step 4: Remove the old wall clock pressure logic** (lines 1663-1754 — the `if self._step_start_time is not None:` block and all its nested ADVISORY/URGENT/CRITICAL handling)

Keep only the wall_limit exceeded check at the very top (hard stop when `elapsed > wall_limit`).

- [ ] **Step 5: Run all existing tests to verify no regressions**

```bash
cd backend && conda activate pythinker && pytest tests/domain/services/agents/ tests/unit/agents/ -x --tb=short -q -p no:cov -o addopts=
```

- [ ] **Step 6: Lint and commit**

```bash
cd backend && ruff check app/domain/services/agents/base.py app/domain/services/agents/middleware_adapters/wall_clock_pressure.py && ruff format --check app/domain/services/agents/base.py app/domain/services/agents/middleware_adapters/wall_clock_pressure.py
```

```bash
git commit -m "refactor(agents): route wall clock pressure through middleware pipeline

Replace ~90 LOC of inline wall clock advisory/urgent/critical handling
in _execute_inner with WallClockPressureMiddleware via pipeline.
before_step returns FORCE at critical, INJECT at urgent, advisory via ctx."
```

---

## Task 3: Replace Hallucination Loop Detection in _execute_inner

Replace lines 1628-1647 (the `if self._hallucination_detector.should_inject_correction_prompt():` block) with `HallucinationGuardMiddleware` via the pipeline's `before_step` hook.

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:1628-1647`

- [ ] **Step 1: The pipeline's `before_step` already runs `HallucinationGuardMiddleware.before_step()` which does this exact check. Remove the inline block:**

Replace lines 1628-1647:
```python
# OLD: direct hallucination detector calls
if self._hallucination_detector.should_inject_correction_prompt():
    self._hallucination_count_this_step += 1
    # ... 20 lines of handling
```

With nothing — the `before_step` pipeline call from Task 2 already handles this (the pipeline runs ALL middleware including HallucinationGuardMiddleware which checks `should_inject_correction_prompt` and returns INJECT or FORCE).

- [ ] **Step 2: Remove the `_hallucination_count_this_step` counter reset** from the top of `_execute_inner` (line 1613) since it's now managed by the middleware.

- [ ] **Step 3: Run tests, lint, commit**

```bash
cd backend && pytest tests/domain/services/agents/ tests/unit/agents/ -x --tb=short -q -p no:cov -o addopts=
```

```bash
git commit -m "refactor(agents): route hallucination loop detection through middleware

Remove 20 LOC of inline hallucination loop escalation from _execute_inner.
HallucinationGuardMiddleware.before_step handles detection, correction
injection, and force-advance via the pipeline."
```

---

## Task 4: Route Stuck Detection Through Pipeline

Replace the stuck detection in `_execute_step_safely()` (lines 2563-2613) with `StuckDetectionMiddleware.after_step()`.

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:2563-2613`

- [ ] **Step 1: Store `last_response` in middleware context metadata**

After line 2561 (where `filtered_message` is constructed), add:
```python
# Store for middleware stuck detection
if hasattr(self, '_mw_ctx') and self._mw_ctx:
    self._mw_ctx.metadata["last_response"] = filtered_message
```

Note: `_mw_ctx` needs to be stored as instance attribute in `_execute_inner` so `_execute_step_safely` can access it. Add `self._mw_ctx = _mw_ctx` after creating the context in Task 2.

- [ ] **Step 2: After storing `last_response`, call pipeline `after_step`**

After the existing stuck detection block, add a pipeline call (don't remove old code yet — run both in parallel to verify):

```python
# Pipeline after_step (runs StuckDetectionMiddleware)
if hasattr(self, '_mw_ctx') and self._mw_ctx:
    _after_result = await self._pipeline.run_after_step(self._mw_ctx)
    # Note: existing inline stuck detection still runs for now
```

- [ ] **Step 3: Verify both old and new paths produce same results, then remove old stuck detection**

Remove lines 2563-2613 (the `is_response_stuck, confidence = self._stuck_detector.track_response(...)` block through the recovery prompt injection).

Replace with:
```python
# ── Stuck detection via middleware pipeline ──
if hasattr(self, '_mw_ctx') and self._mw_ctx:
    self._mw_ctx.metadata["last_response"] = filtered_message
    _after_result = await self._pipeline.run_after_step(self._mw_ctx)
    if _after_result.signal == MiddlewareSignal.FORCE:
        self._stuck_recovery_exhausted = True
        # Fall through to return — caller checks _stuck_recovery_exhausted
    elif _after_result.signal == MiddlewareSignal.INJECT:
        await self._add_to_memory([filtered_message, {"role": "user", "content": _after_result.message}])
        continue
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
cd backend && pytest tests/domain/services/agents/ tests/unit/agents/ -x --tb=short -q -p no:cov -o addopts=
```

```bash
git commit -m "refactor(agents): route stuck detection through middleware pipeline

Replace ~50 LOC of inline stuck detection in _execute_step_safely
with StuckDetectionMiddleware.after_step via pipeline."
```

---

## Task 5: Add try/except with on_error to Execute Loop

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`

- [ ] **Step 1: Wrap the main while loop in `_execute_inner` with try/except/finally**

```python
try:
    while iteration_spent < iteration_budget:
        # ... existing loop body
        pass
except Exception as _exc:
    _err_result = await self._pipeline.run_on_error(self._mw_ctx, _exc)
    if _err_result.signal == MiddlewareSignal.ABORT:
        raise
    logger.exception("Agent execution error handled by middleware")
finally:
    await self._pipeline.run_after_execution(self._mw_ctx)
```

- [ ] **Step 2: Run tests, lint, commit**

```bash
git commit -m "refactor(agents): add on_error and after_execution pipeline hooks to execute loop"
```

---

## Task 6: Wire PlanActFlow to Create and Pass AgentServiceContext

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:460-500`

- [ ] **Step 1: In PlanActFlow.__init__, create AgentServiceContext via factory**

After the tools list is built (around line 462), add:

```python
from app.domain.services.agents.agent_context_factory import AgentContextFactory

_context_factory = AgentContextFactory()
_service_context = _context_factory.create(
    agent_id=self._agent_id,
    session_id=session_id,
    tools=tools,
    research_mode=self._research_mode,
    feature_flags=feature_flags,
)
```

- [ ] **Step 2: Pass `service_context` to PlannerAgent and ExecutionAgent**

```python
self.planner = PlannerAgent(
    agent_id=self._agent_id,
    ...
    tool_result_store=tool_result_store,
    service_context=_service_context,  # NEW
)

self.executor = ExecutionAgent(
    agent_id=self._agent_id,
    ...
    tool_result_store=tool_result_store,
    service_context=_service_context,  # NEW
)
```

- [ ] **Step 3: Verify PlannerAgent and ExecutionAgent accept `service_context`**

Both inherit from BaseAgent which already accepts it (Task 12 from Phase 1-2). Check that their `__init__` passes `**kwargs` or explicitly accepts the param.

Read `planner.py` and `execution.py` `__init__` signatures — if they don't forward `service_context`, add it.

- [ ] **Step 4: Remove the manual efficiency monitor threshold override** (lines 497-499 in plan_act.py):

```python
# REMOVE — now handled by AgentContextFactory with research_mode param
if self._research_mode in ("deep_research", "wide_research"):
    from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor
    self.executor._efficiency_monitor = ToolEfficiencyMonitor(...)
```

- [ ] **Step 5: Run full test suite**

```bash
cd backend && conda activate pythinker && pytest tests/ -x --tb=short -q -p no:cov -o addopts= --ignore=tests/infrastructure/external/scraper
```

- [ ] **Step 6: Lint and commit**

```bash
git commit -m "feat(agents): wire PlanActFlow to create and pass AgentServiceContext

PlanActFlow now creates AgentServiceContext via factory with
research_mode for correct efficiency thresholds. Passed to
PlannerAgent and ExecutionAgent."
```

---

## Task 7: Final Validation

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && conda activate pythinker && pytest tests/ --tb=short -q -p no:cov -o addopts= --ignore=tests/infrastructure/external/scraper
```

- [ ] **Step 2: Run lint**

```bash
cd backend && ruff check . && ruff format --check .
```

- [ ] **Step 3: Count LOC saved in base.py**

```bash
wc -l backend/app/domain/services/agents/base.py
```
Expected: ~2,850 (down from 3,027 — ~170 LOC removed)

- [ ] **Step 4: Verify all middleware tests still pass**

```bash
cd backend && pytest tests/domain/services/agents/test_middleware_*.py tests/domain/services/agents/test_mw_*.py tests/domain/services/agents/test_agent_context_factory.py -v -p no:cov -o addopts=
```

---

## Summary

| Task | Description | LOC Impact |
|------|-------------|------------|
| 1 | Test harness for middleware routing | +30 test LOC |
| 2 | Replace wall clock pressure with pipeline | -90, +20 |
| 3 | Replace hallucination loop with pipeline | -20 |
| 4 | Replace stuck detection with pipeline | -50, +10 |
| 5 | Add on_error + after_execution hooks | +10 |
| 6 | Wire PlanActFlow with AgentServiceContext | +15, -5 |
| 7 | Final validation | 0 |

**Net impact:** ~130 LOC removed from BaseAgent, BaseAgent drops from 3,027 to ~2,860 LOC.
