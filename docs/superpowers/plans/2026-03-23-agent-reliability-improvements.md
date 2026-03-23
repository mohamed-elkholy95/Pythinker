# Agent Reliability Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three interrelated agent reliability issues — action audit false positives, grounding evidence gaps, and middleware lifecycle management — using industry best practices (LangChain middleware patterns, NLI-style claim verification, intent-based tool mapping).

**Architecture:** Leverage existing infrastructure (`tool_hint` on Step, `build_source_context()` on OutputVerifier, `BaseMiddleware` hooks) rather than building new systems. The action audit switches from keyword→tool regex matching to planner-declared `tool_hint` matching. The grounding verifier gains per-step source tracking. The middleware pipeline gains an `on_step_boundary()` lifecycle hook with automatic state reset.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, asyncio

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/domain/models/plan.py` | Modify | Add `expected_tools` field to Step model |
| `app/domain/services/agents/planner.py` | Modify | Populate `expected_tools` from `tool_hint` mapping |
| `app/domain/services/flows/plan_act.py` | Modify | Use `expected_tools` in action audit; call lifecycle hooks |
| `app/domain/services/agents/base_middleware.py` | Modify | Add `on_step_boundary()` hook |
| `app/domain/services/agents/middleware_pipeline.py` | Modify | Implement `run_step_boundary()` with lifecycle hook |
| `app/domain/services/agents/middleware_adapters/efficiency_monitor.py` | Modify | Implement `on_step_boundary()` |
| `app/domain/services/agents/output_verifier.py` | Modify | Add per-step source accumulation for better evidence |
| `app/domain/services/agents/execution.py` | Modify | Feed step tool results into verifier source context |
| `tests/domain/services/flows/test_step_action_audit.py` | Modify | Test tool_hint-based audit |
| `tests/domain/services/agents/test_mw_lifecycle.py` | Create | Test lifecycle hooks |
| `tests/domain/services/agents/test_verifier_evidence.py` | Create | Test evidence-grounded verification |

---

## Task 1: Intent-Based Action Audit via `expected_tools`

**Files:**
- Modify: `app/domain/models/plan.py:132-156`
- Modify: `app/domain/services/agents/planner.py:540-600`
- Modify: `app/domain/services/flows/plan_act.py:1564-1670`
- Test: `tests/domain/services/flows/test_step_action_audit.py`

### Rationale

The current action audit uses `\b{verb}\b` regex on step descriptions to guess which tools should have been used. This causes false positives (e.g., "benchmark" in a cross-validation step maps to `shell_exec`). The planner already sets `tool_hint` per step — we use it as the authoritative source of expected tool categories.

- [ ] **Step 1: Add `expected_tools` field to Step model**

```python
# app/domain/models/plan.py — add after line 155 (retry_policy)
expected_tools: list[str] = Field(default_factory=list)  # Declared tool categories for action audit
```

- [ ] **Step 2: Write failing test for tool_hint-based audit**

```python
# tests/domain/services/flows/test_step_action_audit.py

def test_tool_hint_research_step_not_failed_for_missing_benchmark():
    """Step with tool_hint='web_search' should pass audit even if description says 'benchmark'."""
    step = Step(
        id="3",
        description="Cross-validate key claims and resolve conflicting benchmark data",
        success=True,
        expected_tools=["search", "browser", "file_read", "file_write"],
    )
    tools_used = {"search", "browser", "file_read", "file_write", "info_search_web"}
    result = PlanActFlow._apply_step_action_audit(step, tools_used)
    assert result is False  # Should NOT fail audit
    assert step.success is True


def test_expected_tools_override_keyword_inference():
    """When expected_tools is set, keyword inference is skipped."""
    step = Step(
        id="1",
        description="Execute benchmark script and run tests",
        success=True,
        expected_tools=["shell_exec"],
    )
    tools_used = {"shell_exec"}
    result = PlanActFlow._apply_step_action_audit(step, tools_used)
    assert result is False  # Passes — shell_exec was used


def test_expected_tools_missing_tool_fails_audit():
    """When expected_tools declares a tool that wasn't used, audit fails."""
    step = Step(
        id="1",
        description="Execute benchmark script",
        success=True,
        expected_tools=["shell_exec"],
    )
    tools_used = {"file_write"}  # Wrote but didn't execute
    result = PlanActFlow._apply_step_action_audit(step, tools_used)
    assert result is True  # Should fail audit
    assert step.success is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `conda run -n pythinker python -m pytest tests/domain/services/flows/test_step_action_audit.py -x -v -p no:cov -o addopts=`

- [ ] **Step 4: Populate `expected_tools` from `tool_hint` in planner**

In `app/domain/services/agents/planner.py`, in the `_step_from_description` function (around line 588), after setting `tool_hint`:

```python
# Map tool_hint to expected_tools for action audit
_TOOL_HINT_TO_EXPECTED: dict[str, list[str]] = {
    "web_search": ["search", "info_search_web", "wide_research"],
    "browser": ["browser", "browser_navigate", "browser_get_content", "search"],
    "file": ["file_read", "file_write", "file"],
    "shell": ["shell_exec", "code_execute_python"],
    "code": ["shell_exec", "code_execute_python", "code_executor"],
    "deal_search": ["search", "info_search_web"],
    "deal_find_coupons": ["search", "browser"],
    "deal_compare_prices": ["search", "browser"],
}

if tool_hint and tool_hint in _TOOL_HINT_TO_EXPECTED:
    step.expected_tools = _TOOL_HINT_TO_EXPECTED[tool_hint]
```

- [ ] **Step 5: Update `_apply_step_action_audit` to prefer `expected_tools`**

In `app/domain/services/flows/plan_act.py`, modify `_apply_step_action_audit` (line 1637):

```python
@classmethod
def _apply_step_action_audit(cls, step: Step, tools_used: set[str]) -> bool:
    """Fail steps that claim actions they did not actually perform."""
    if not step.success or not step.description:
        return False

    # Tier C: If planner declared expected_tools, validate against those
    # (skips keyword-based inference entirely — no false positives)
    if step.expected_tools:
        expected_set = set(step.expected_tools)
        # Check if at least ONE expected tool was used
        if tools_used & expected_set:
            return False  # Audit passes — used at least one expected tool
        # None of the expected tools were used
        step.success = False
        step.status = ExecutionStatus.FAILED
        step.error = f"Step did not use any declared tools: {', '.join(sorted(expected_set))}"
        step.notes = (
            (step.notes or "") + f"\n[Audit failure: expected tools {sorted(expected_set)}, used {sorted(tools_used)}]"
        ).strip()
        return True

    # Fallback: keyword-based inference (legacy path for steps without expected_tools)
    desc_lower = step.description.lower()
    # ... (existing keyword logic, unchanged)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `conda run -n pythinker python -m pytest tests/domain/services/flows/test_step_action_audit.py -x -v -p no:cov -o addopts=`

- [ ] **Step 7: Run full agent test suite**

Run: `conda run -n pythinker python -m pytest tests/domain/services/agents/ tests/domain/services/flows/ -x -p no:cov -o addopts=`

- [ ] **Step 8: Commit**

```bash
git add app/domain/models/plan.py app/domain/services/agents/planner.py app/domain/services/flows/plan_act.py tests/domain/services/flows/test_step_action_audit.py
git commit -m "feat(audit): intent-based action audit using planner-declared expected_tools

Replace keyword regex matching with tool_hint-based expected_tools.
Steps now declare their tool requirements via the planner, eliminating
false positives like 'benchmark' in research steps mapping to shell_exec."
```

---

## Task 2: Middleware Lifecycle Hooks

**Files:**
- Modify: `app/domain/services/agents/base_middleware.py`
- Modify: `app/domain/services/agents/middleware_pipeline.py`
- Modify: `app/domain/services/agents/middleware_adapters/efficiency_monitor.py`
- Modify: `app/domain/services/flows/plan_act.py:3444-3452`
- Create: `tests/domain/services/agents/test_mw_lifecycle.py`

### Rationale

The `_middlewares` typo bug showed that manual iteration over private attributes is fragile. LangChain's middleware pattern uses declarative lifecycle hooks (`before_agent`, `before_model`, etc.). We add `on_step_boundary()` to BaseMiddleware and call it from `run_step_boundary()` in the pipeline — a single call point that all middleware can hook into.

- [ ] **Step 1: Write failing test for lifecycle hooks**

```python
# tests/domain/services/agents/test_mw_lifecycle.py
import pytest
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline
from app.domain.services.agents.middleware import MiddlewareContext


class TrackingMiddleware(BaseMiddleware):
    def __init__(self):
        self.step_boundary_called = False
        self.boundary_count = 0

    def on_step_boundary(self) -> None:
        self.step_boundary_called = True
        self.boundary_count += 1


class TestMiddlewareLifecycle:
    def test_run_step_boundary_calls_all_middleware(self):
        mw1 = TrackingMiddleware()
        mw2 = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw1).use(mw2)

        pipeline.run_step_boundary()

        assert mw1.step_boundary_called
        assert mw2.step_boundary_called

    def test_run_step_boundary_increments_count(self):
        mw = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw)

        pipeline.run_step_boundary()
        pipeline.run_step_boundary()

        assert mw.boundary_count == 2

    def test_reset_for_new_step_also_calls_on_step_boundary(self):
        """reset_for_new_step delegates to on_step_boundary for middleware that implement it."""
        mw = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw)

        pipeline.reset_for_new_step()

        assert mw.step_boundary_called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n pythinker python -m pytest tests/domain/services/agents/test_mw_lifecycle.py -x -v -p no:cov -o addopts=`

- [ ] **Step 3: Add `on_step_boundary()` to BaseMiddleware**

```python
# app/domain/services/agents/base_middleware.py — add after on_error()

    def on_step_boundary(self) -> None:
        """Called when the pipeline transitions between plan steps.

        Override to reset per-step state (URL dedup sets, navigation budgets,
        efficiency counters). This is a synchronous hook — no I/O needed.
        """
```

- [ ] **Step 4: Update MiddlewarePipeline to use lifecycle hook**

```python
# app/domain/services/agents/middleware_pipeline.py — update reset_for_new_step()

    def reset_for_new_step(self) -> None:
        """Reset per-step state on all middleware via lifecycle hook."""
        self.run_step_boundary()

    def run_step_boundary(self) -> None:
        """Notify all middleware of a step boundary.

        Calls on_step_boundary() on each middleware, then reset_browser_budget()
        for backward compatibility with middleware that hasn't migrated yet.
        """
        for mw in self._middleware:
            if hasattr(mw, "on_step_boundary"):
                try:
                    mw.on_step_boundary()
                except Exception:
                    logger.exception("Middleware %s.on_step_boundary raised (swallowed)", getattr(mw, "name", "?"))
            # Backward compat: call reset_browser_budget if on_step_boundary doesn't exist
            elif hasattr(mw, "reset_browser_budget"):
                mw.reset_browser_budget()
```

- [ ] **Step 5: Migrate EfficiencyMonitorMiddleware to lifecycle hook**

```python
# app/domain/services/agents/middleware_adapters/efficiency_monitor.py
# Add on_step_boundary() that delegates to reset_browser_budget()

    def on_step_boundary(self) -> None:
        """Lifecycle hook: reset all per-step state at step boundaries."""
        self.reset_browser_budget()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `conda run -n pythinker python -m pytest tests/domain/services/agents/test_mw_lifecycle.py tests/domain/services/agents/test_mw_efficiency_monitor.py -x -v -p no:cov -o addopts=`

- [ ] **Step 7: Commit**

```bash
git add app/domain/services/agents/base_middleware.py app/domain/services/agents/middleware_pipeline.py app/domain/services/agents/middleware_adapters/efficiency_monitor.py tests/domain/services/agents/test_mw_lifecycle.py
git commit -m "feat(middleware): add on_step_boundary lifecycle hook

Middleware can now implement on_step_boundary() for automatic state reset
at step transitions. MiddlewarePipeline.run_step_boundary() calls all
middleware in order. Eliminates need for callers to reach into private
attributes. Follows LangChain middleware lifecycle pattern."
```

---

## Task 3: Evidence-Grounded Verification Improvements

**Files:**
- Modify: `app/domain/services/agents/output_verifier.py:121-145`
- Modify: `app/domain/services/agents/execution.py`
- Create: `tests/domain/services/agents/test_verifier_evidence.py`

### Rationale

The OutputVerifier's `build_source_context()` collects sources from SourceTracker, but by the time verification runs, context compaction may have truncated tool results. Research (EY hallucination report, Portkey guide) recommends passing actual search snippets directly. We add per-step source accumulation to ensure the verifier always has fresh evidence.

- [ ] **Step 1: Write failing test for step-level source accumulation**

```python
# tests/domain/services/agents/test_verifier_evidence.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from app.domain.services.agents.output_verifier import OutputVerifier


class TestStepSourceAccumulation:
    def test_add_step_source_adds_to_tracker(self):
        verifier = OutputVerifier.__new__(OutputVerifier)
        verifier._source_tracker = MagicMock()
        verifier._source_tracker._collected_sources = []
        verifier._step_sources = []

        verifier.add_step_source(
            title="MacBook Pro M5 Review",
            url="https://notebookcheck.net/review",
            snippet="M5 Pro scored 15,200 in Geekbench multi-core",
        )

        assert len(verifier._step_sources) == 1
        assert "notebookcheck.net" in verifier._step_sources[0]

    def test_build_source_context_includes_step_sources(self):
        verifier = OutputVerifier.__new__(OutputVerifier)
        verifier._source_tracker = MagicMock()
        verifier._source_tracker._collected_sources = []
        verifier._context_manager = None
        verifier._step_sources = [
            "Source: MacBook M5 Review (https://example.com)\nM5 Pro has 12-core CPU"
        ]

        context = verifier.build_source_context()

        assert len(context) >= 1
        assert "M5 Pro has 12-core CPU" in context[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n pythinker python -m pytest tests/domain/services/agents/test_verifier_evidence.py -x -v -p no:cov -o addopts=`

- [ ] **Step 3: Add step-level source accumulation to OutputVerifier**

In `app/domain/services/agents/output_verifier.py`, add:

```python
# In __init__ or setup:
self._step_sources: list[str] = []

def add_step_source(self, title: str, url: str, snippet: str) -> None:
    """Add a source discovered during step execution for grounding context."""
    entry = f"Source: {title} ({url})\n{snippet[:500]}"
    self._step_sources.append(entry)

def clear_step_sources(self) -> None:
    """Clear per-step sources after verification."""
    self._step_sources.clear()
```

Update `build_source_context()` to include `_step_sources`:

```python
def build_source_context(self) -> list[str]:
    context: list[str] = []

    # Include per-step sources (highest priority — freshest evidence)
    context.extend(self._step_sources)

    # Existing: SourceTracker collected sources
    collected = self._source_tracker._collected_sources
    for src in collected:
        # ... existing logic

    # Existing: ContextManager key_facts and insights
    # ... existing logic

    return context
```

- [ ] **Step 4: Feed search results into verifier from execution agent**

In `app/domain/services/agents/execution.py`, after search tool results are received, extract top snippets and feed them to the verifier:

```python
# After tool_completed for search/info_search_web tools:
if tool_name in ("info_search_web", "wide_research", "search") and self._output_verifier:
    # Extract snippets from search results for grounding evidence
    if hasattr(result, "data") and isinstance(result.data, dict):
        for item in result.data.get("results", [])[:5]:
            self._output_verifier.add_step_source(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", item.get("content", ""))[:500],
            )
```

- [ ] **Step 5: Clear step sources at step boundary**

In `plan_act.py`, after step verification completes, clear sources:

```python
# After _apply_hallucination_verification for the step:
if hasattr(step_executor, "_output_verifier"):
    step_executor._output_verifier.clear_step_sources()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `conda run -n pythinker python -m pytest tests/domain/services/agents/test_verifier_evidence.py -x -v -p no:cov -o addopts=`

- [ ] **Step 7: Run full test suite**

Run: `conda run -n pythinker python -m pytest tests/domain/services/agents/ tests/domain/services/flows/ -x -p no:cov -o addopts=`

- [ ] **Step 8: Commit**

```bash
git add app/domain/services/agents/output_verifier.py app/domain/services/agents/execution.py tests/domain/services/agents/test_verifier_evidence.py
git commit -m "feat(verifier): per-step source accumulation for evidence-grounded verification

Search results are now fed directly to the grounding verifier as evidence,
so claim verification checks against actual data rather than LLM knowledge.
Reduces false positives on source attribution claims."
```

---

## Task 4: Integration Verification

**Files:**
- No new files — cross-cutting validation

- [ ] **Step 1: Run complete backend test suite**

Run: `conda run -n pythinker python -m pytest tests/ -x -p no:cov -o addopts= --timeout=120`

Expected: All existing tests pass plus new tests.

- [ ] **Step 2: Lint and format check**

Run: `conda run -n pythinker ruff check . && ruff format --check .`

- [ ] **Step 3: Rebuild backend container with all changes**

Run: `docker compose up --build -d --no-deps backend`

- [ ] **Step 4: Smoke test — submit a research task and verify**

Submit "Compare MacBook M4 Max vs M5 Pro for AI workloads" from frontend.
Verify in logs:
- No `FORCE` triggers on steps
- No false-positive action audit failures
- Steps complete with `expected_tools` in audit log
- Grounding verifier receives source evidence

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes from smoke test"
```
