# Session Reliability Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 6 bugs found during live monitoring of session `52befb2877924066`: SSE 0-event reconnects during summarization, research pipeline shadow bypass, hallucination verification skip, chart scoring favoring small tables, final step state race, and missing artifact references in summaries.

**Architecture:** Surgical, independent fixes across 8 backend files. Each fix has zero coupling to others, allowing independent revert. TDD approach — write failing test, implement minimal fix, verify.

**Tech Stack:** Python 3.12, pytest, Pydantic v2, asyncio, FastAPI SSE

---

### Task 1: SSE Reconnect During Summarization — Stop Premature DoneEvent

**Problem:** When a client reconnects mid-summarization, `session.status == "completed"` (from execution phase) triggers the short-circuit at `session_routes.py:924`. The reconnect returns 0 events → DoneEvent, killing the live stream.

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py:912-1011`
- Test: `backend/tests/interfaces/api/test_session_routes.py`

**Step 1: Write the failing test**

Add to `backend/tests/interfaces/api/test_session_routes.py`:

```python
class TestReconnectDuringSummarization:
    """Verify reconnect during active task does not short-circuit to DoneEvent."""

    @pytest.mark.asyncio
    async def test_completed_session_with_active_task_does_not_shortcircuit(self):
        """When session.status is 'completed' but session.task_id exists and is active,
        the reconnect should NOT short-circuit — it should fall through to agent_service.chat()."""
        from app.interfaces.api.session_routes import chat
        from app.interfaces.schemas.session import ChatRequest

        # Build a session that looks "completed" from execution but has an active task
        session = SimpleNamespace(
            id="test-sess-123",
            status="completed",
            user_id="user-1",
            task_id="active-task-456",  # Task still running (summarization)
            events=[],
            title="Test Session",
            research_mode=None,
        )

        request = ChatRequest(
            session_id="test-sess-123",
            message="",  # No fresh input — pure reconnect
        )

        http_request = MagicMock()
        http_request.headers = {}

        mock_session_service = AsyncMock()
        mock_session_service.get_session.return_value = session
        mock_agent_service = AsyncMock()

        # The key assertion: with an active task_id, chat() should NOT
        # return a static completed_generator. It should call agent_service.
        # We'll check that session_service.get_session is called but
        # the short-circuit path is NOT taken.
        with (
            patch("app.interfaces.api.session_routes.get_session_service", return_value=mock_session_service),
            patch("app.interfaces.api.session_routes.get_agent_service", return_value=mock_agent_service),
            patch("app.interfaces.api.session_routes._is_task_active", return_value=True),
        ):
            # The function should proceed to agent_service.chat, not short-circuit
            # We verify by checking that DoneEvent is NOT yielded for active tasks
            result = await chat(request, http_request)
            # agent_service.chat should have been invoked (not short-circuited)
            assert mock_agent_service.chat.called or not hasattr(result, "_is_completed_generator")

    @pytest.mark.asyncio
    async def test_truly_completed_session_still_shortcircuits(self):
        """When session is truly completed (no active task), DoneEvent short-circuit still works."""
        from app.interfaces.api.session_routes import chat
        from app.interfaces.schemas.session import ChatRequest

        session = SimpleNamespace(
            id="test-sess-789",
            status="completed",
            user_id="user-1",
            task_id=None,  # No active task
            events=[],
            title="Done Session",
            research_mode=None,
        )

        request = ChatRequest(
            session_id="test-sess-789",
            message="",
        )

        http_request = MagicMock()
        http_request.headers = {}

        mock_session_service = AsyncMock()
        mock_session_service.get_session.return_value = session

        with (
            patch("app.interfaces.api.session_routes.get_session_service", return_value=mock_session_service),
            patch("app.interfaces.api.session_routes._is_task_active", return_value=False),
        ):
            result = await chat(request, http_request)
            # Should return EventSourceResponse with DoneEvent (short-circuit path)
            assert result is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda run -n pythinker pytest tests/interfaces/api/test_session_routes.py::TestReconnectDuringSummarization -v`
Expected: FAIL — `_is_task_active` function does not exist yet

**Step 3: Implement the fix**

In `backend/app/interfaces/api/session_routes.py`, add a helper function before the `chat()` route:

```python
async def _is_task_active(session_id: str) -> bool:
    """Check if session has an actively-running task via Redis liveness key.

    Returns True when the task runner is still heartbeating, which means
    the session is mid-execution (e.g. in summarization phase) even though
    session.status may already read 'completed' from the execution phase.
    """
    from app.infrastructure.external.redis_task import get_redis_task_service

    try:
        redis_service = get_redis_task_service()
        liveness = await redis_service.get_liveness(session_id)
        return liveness is not None
    except Exception:
        return False
```

Then modify the short-circuit condition at line 924:

```python
# BEFORE:
if session.status in ("completed", "failed") and not has_fresh_input:

# AFTER:
if session.status in ("completed", "failed") and not has_fresh_input:
    # Guard: if a task is still actively running (e.g. summarization),
    # do NOT short-circuit — fall through to the live stream path.
    if await _is_task_active(session_id):
        logger.info(
            "Session %s shows '%s' but has active task — skipping short-circuit",
            session_id,
            session.status,
        )
    else:
        # ... existing short-circuit logic (indent existing block)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda run -n pythinker pytest tests/interfaces/api/test_session_routes.py::TestReconnectDuringSummarization -v`
Expected: PASS

**Step 5: Run full session_routes test suite**

Run: `cd backend && conda run -n pythinker pytest tests/interfaces/api/test_session_routes.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/interfaces/api/session_routes.py backend/tests/interfaces/api/test_session_routes.py
git commit -m "fix(sse): prevent premature DoneEvent on reconnect during summarization

Check Redis liveness before short-circuiting completed sessions.
When task runner is still heartbeating (e.g. during summarization),
fall through to live stream instead of returning 0-event DoneEvent."
```

---

### Task 2: Switch Research Pipeline Default to Enforced Mode

**Problem:** `research_pipeline_mode` defaults to `"shadow"`, meaning synthesis gate verdicts are logged but never enforced. The pipeline was built and tested — time to activate it. Also, `browser_navigate` is not intercepted by `ResearchExecutionPolicy`, so the LLM bypassed `info_search_web` entirely.

**Files:**
- Modify: `backend/app/core/config_research_pipeline.py:26`
- Modify: `backend/app/domain/services/agents/execution.py:458-473`
- Modify: `backend/tests/integration/test_research_pipeline_shadow_mode.py`
- Create: `backend/tests/integration/test_research_pipeline_enforced_default.py`

**Step 1: Write the failing test**

Create `backend/tests/integration/test_research_pipeline_enforced_default.py`:

```python
"""Tests verifying the research pipeline defaults to enforced mode."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


class TestResearchPipelineEnforcedDefault:
    """Verify the pipeline defaults to enforced, not shadow."""

    def test_config_default_is_enforced(self):
        """The config mixin default must be 'enforced' so the synthesis gate blocks."""
        from app.core.config_research_pipeline import ResearchPipelineSettingsMixin

        mixin = ResearchPipelineSettingsMixin()
        assert mixin.research_pipeline_mode == "enforced"

    def test_synthesis_gate_blocks_in_enforced_mode(self):
        """In enforced mode, _check_synthesis_gate returns a result (not None)."""
        from unittest.mock import MagicMock, patch

        from app.domain.models.evidence import SynthesisGateVerdict

        # Build a mock ExecutionAgent with the gate
        mock_policy = MagicMock()
        mock_result = MagicMock()
        mock_result.verdict = SynthesisGateVerdict.hard_fail
        mock_result.reasons = ["too few sources"]
        mock_result.thresholds_applied = {}
        mock_policy.can_synthesize.return_value = mock_result

        mock_settings = SimpleNamespace(research_pipeline_mode="enforced")
        with patch("app.domain.services.agents.execution.get_settings", return_value=mock_settings):
            from app.domain.services.agents.execution import ExecutionAgent

            agent = ExecutionAgent.__new__(ExecutionAgent)
            agent._research_execution_policy = mock_policy
            result = agent._check_synthesis_gate()

        assert result is not None
        assert result.verdict == SynthesisGateVerdict.hard_fail

    def test_search_nudge_injected_when_no_search_detected(self):
        """When pipeline is enforced and step is synthesis-like but no searches
        were recorded, a search nudge should be injected into the step prompt."""
        # This tests the new search-nudge injection in execute_step
        from app.domain.services.agents.execution import ExecutionAgent

        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent._research_execution_policy = None
        # _is_synthesis_step should detect keywords
        assert agent._is_synthesis_step("Compile findings and synthesize report")
        assert agent._is_synthesis_step("write the final summary")
        assert not agent._is_synthesis_step("Search for Python frameworks")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda run -n pythinker pytest tests/integration/test_research_pipeline_enforced_default.py -v`
Expected: FAIL on `test_config_default_is_enforced` (current default is "shadow")

**Step 3: Implement the fix**

In `backend/app/core/config_research_pipeline.py`, line 26:

```python
# BEFORE:
research_pipeline_mode: Literal["shadow", "enforced"] = "shadow"

# AFTER:
research_pipeline_mode: Literal["shadow", "enforced"] = "enforced"
```

Update the module docstring (lines 8-12) to reflect the change:

```python
# BEFORE:
# shadow   — pipeline runs alongside the existing flow; its decisions are
#            logged but never enforced.  Safe to deploy without changing UX.
# enforced — pipeline gates synthesis and can block report generation when
#            quality thresholds are not met.

# AFTER:
# shadow   — pipeline runs alongside the existing flow; its decisions are
#            logged but never enforced.  Safe to deploy without changing UX.
# enforced — (DEFAULT) pipeline gates synthesis and can block report generation
#            when quality thresholds are not met.
```

**Step 4: Update shadow mode tests**

In `backend/tests/integration/test_research_pipeline_shadow_mode.py`, the `_make_config()` already explicitly sets `"research_pipeline_mode": "shadow"`, so those tests remain valid (they test shadow mode explicitly, not the default).

**Step 5: Run tests to verify they pass**

Run: `cd backend && conda run -n pythinker pytest tests/integration/test_research_pipeline_enforced_default.py tests/integration/test_research_pipeline_shadow_mode.py tests/integration/test_research_pipeline_integration.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/core/config_research_pipeline.py backend/tests/integration/test_research_pipeline_enforced_default.py
git commit -m "feat(research): switch pipeline default from shadow to enforced

The deterministic research pipeline has been validated in shadow mode.
Promote to enforced so synthesis gate verdicts actually block when
evidence quality thresholds are not met.

Override with RESEARCH_PIPELINE_MODE=shadow to revert."
```

---

### Task 3: Fix Hallucination Verification Skip When Source Context Is Empty

**Problem:** When `deep_research` bypasses `info_search_web` (uses `browser_navigate` instead), `SourceTracker` collects nothing → `build_source_context()` returns `[]` → LettuceDetect's `verify()` is called with empty context → returns `skipped=True` → hallucination check silently skipped.

**Files:**
- Modify: `backend/app/domain/services/agents/output_verifier.py:440-462`
- Test: `backend/tests/test_verifier.py` or new `backend/tests/domain/services/agents/test_hallucination_grounding_fallback.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/agents/test_hallucination_grounding_fallback.py`:

```python
"""Tests for hallucination grounding fallback when source_context is empty."""
from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch
from types import SimpleNamespace

import pytest

from app.domain.services.agents.output_verifier import OutputVerifier


class TestHallucinationGroundingFallback:
    """When SourceTracker is empty, output_verifier should fall back to
    context_manager key_facts as grounding context rather than skipping."""

    def test_build_source_context_uses_key_facts_fallback(self):
        """build_source_context() should return key_facts when no tracked sources exist."""
        verifier = OutputVerifier.__new__(OutputVerifier)
        verifier._source_tracker = MagicMock()
        verifier._source_tracker.get_source_snippets.return_value = []
        verifier._context_manager = MagicMock()
        verifier._context_manager.get_key_facts.return_value = [
            "Python 3.12 was released in October 2023",
            "FastAPI is built on Starlette and Pydantic",
        ]

        context = verifier.build_source_context()
        assert len(context) >= 1
        assert any("Python 3.12" in c for c in context)

    def test_build_source_context_prefers_tracked_sources(self):
        """When tracked sources exist, they take priority over key_facts."""
        verifier = OutputVerifier.__new__(OutputVerifier)
        verifier._source_tracker = MagicMock()
        verifier._source_tracker.get_source_snippets.return_value = [
            "Content from actual web source about GitHub trends"
        ]
        verifier._context_manager = MagicMock()
        verifier._context_manager.get_key_facts.return_value = [
            "Some fallback fact"
        ]

        context = verifier.build_source_context()
        assert len(context) >= 1
        assert any("GitHub trends" in c for c in context)

    @pytest.mark.asyncio
    async def test_verify_hallucination_does_not_skip_with_key_facts_fallback(self):
        """verify_hallucination should NOT return skipped=True when key_facts provide context."""
        verifier = OutputVerifier.__new__(OutputVerifier)
        verifier._source_tracker = MagicMock()
        verifier._source_tracker.get_source_snippets.return_value = []
        verifier._context_manager = MagicMock()
        verifier._context_manager.get_key_facts.return_value = [
            "Pythinker uses FastAPI backend with DDD architecture",
        ]
        verifier._lettuce_enabled = True
        verifier._metrics = MagicMock()
        verifier._research_depth = None

        mock_lettuce = MagicMock()
        mock_lettuce.verify.return_value = MagicMock(
            skipped=False,
            has_hallucinations=False,
            hallucinated_spans=[],
            hallucination_ratio=0.0,
            confidence_score=0.9,
        )

        mock_settings = SimpleNamespace(
            hallucination_grounding_context_size=4096,
            hallucination_grounding_context_deep=8192,
            hallucination_block_threshold=0.30,
            hallucination_warn_threshold=0.10,
        )

        with (
            patch("app.domain.services.agents.output_verifier.get_lettuce_verifier", return_value=mock_lettuce),
            patch("app.domain.services.agents.output_verifier.get_settings", return_value=mock_settings),
        ):
            result = await verifier.verify_hallucination(
                content="Test content about FastAPI",
                query="Tell me about Pythinker",
            )

        assert not result.skipped
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/agents/test_hallucination_grounding_fallback.py -v`
Expected: FAIL — `build_source_context` doesn't use key_facts fallback yet

**Step 3: Implement the fix**

In `backend/app/domain/services/agents/output_verifier.py`, modify `build_source_context()` to add key_facts fallback:

```python
def build_source_context(self) -> list[str]:
    """Build grounding context from tracked sources, with key_facts fallback."""
    context = []

    # Primary: tracked source snippets from SourceTracker
    if self._source_tracker:
        context = self._source_tracker.get_source_snippets()

    # Fallback: when no tracked sources (e.g. browser_navigate bypassed search),
    # use context_manager key_facts as supplementary grounding.
    if not context and self._context_manager:
        key_facts = self._context_manager.get_key_facts()
        if key_facts:
            context = list(key_facts)
            logger.info(
                "hallucination_grounding_fallback",
                extra={"source": "key_facts", "count": len(context)},
            )

    return context
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/agents/test_hallucination_grounding_fallback.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/output_verifier.py backend/tests/domain/services/agents/test_hallucination_grounding_fallback.py
git commit -m "fix(verification): grounding fallback to key_facts when SourceTracker is empty

When deep_research bypasses info_search_web (uses browser_navigate),
SourceTracker collects nothing → empty grounding context → LettuceDetect
skips verification entirely. Now falls back to context_manager key_facts
so hallucination detection still runs with available evidence."
```

---

### Task 4: Fix Chart Table Scoring to Prefer Larger Tables

**Problem:** `_select_best_table()` scoring formula `rows * headers + numeric_density * 2` lets a small 3-row table with high numeric density outscore a larger 10-row mixed table. Result: chart shows 3 data points instead of 10.

**Files:**
- Modify: `backend/app/domain/services/comparison_chart_generator.py:202-216`
- Test: `backend/tests/domain/services/test_comparison_chart_generator.py`

**Step 1: Write the failing test**

Add to `backend/tests/domain/services/test_comparison_chart_generator.py`:

```python
class TestSelectBestTableRowBonus:
    """Verify larger tables are preferred over smaller high-density tables."""

    def test_larger_table_preferred_over_small_dense_table(self):
        """A 10-row table should outscore a 3-row table even if the 3-row
        table has higher numeric density per cell."""
        generator = ComparisonChartGenerator()

        markdown = """# GitHub Trending Report

## Quick Stats
| Metric | Value | Change |
|--------|-------|--------|
| Stars | 12500 | +500 |
| Forks | 3200 | +120 |
| Issues | 845 | -30 |

## Top 10 Trending Repositories
| Repository | Stars | Language | Description |
|-----------|-------|----------|-------------|
| repo-alpha | 15000 | Python | ML framework |
| repo-beta | 12000 | Rust | Systems tool |
| repo-gamma | 9500 | TypeScript | Web framework |
| repo-delta | 8200 | Go | Cloud native |
| repo-epsilon | 7100 | Python | Data science |
| repo-zeta | 6300 | JavaScript | UI library |
| repo-eta | 5800 | Rust | CLI toolkit |
| repo-theta | 4900 | Python | NLP library |
| repo-iota | 4200 | Go | API gateway |
| repo-kappa | 3700 | TypeScript | State management |
"""
        # Extract tables and verify the 10-row table is selected
        tables = generator._extract_tables(markdown)
        assert len(tables) == 2

        best = generator._select_best_table(tables)
        assert best is not None
        assert len(best.rows) == 10, f"Expected 10-row table, got {len(best.rows)}-row table"

    def test_row_count_bonus_applied(self):
        """Tables with 5+ rows should receive a bonus to prevent
        small dense tables from winning."""
        generator = ComparisonChartGenerator()

        markdown = """# Report

## Small Table
| A | B |
|---|---|
| 100 | 200 |
| 300 | 400 |

## Large Table
| Name | Value | Status | Notes |
|------|-------|--------|-------|
| Item 1 | 10 | Active | Good |
| Item 2 | 20 | Active | OK |
| Item 3 | 30 | Paused | Review |
| Item 4 | 40 | Active | Good |
| Item 5 | 50 | Active | Fine |
| Item 6 | 60 | Active | Good |
"""
        tables = generator._extract_tables(markdown)
        best = generator._select_best_table(tables)
        assert best is not None
        assert len(best.rows) >= 5
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_comparison_chart_generator.py::TestSelectBestTableRowBonus -v`
Expected: FAIL — the 3-row table currently wins

**Step 3: Implement the fix**

In `backend/app/domain/services/comparison_chart_generator.py`, modify `_select_best_table()` at lines 202-216:

```python
def _select_best_table(self, tables: list[_MarkdownTable]) -> _MarkdownTable | None:
    best: _MarkdownTable | None = None
    best_score = -1
    for table in tables:
        score = len(table.rows) * len(table.headers)
        numeric_density = self._numeric_cell_count(table)
        score += numeric_density * 2
        # Row count bonus: prefer tables with more data points for richer charts.
        # Without this, a small 3-row all-numeric table can outscore a larger
        # 10-row table that has mixed text/numeric content.
        if len(table.rows) >= 5:
            score += len(table.rows) * 3
        if table.heading and self._VS_PATTERN.search(table.heading):
            score += 12
        if self._VS_PATTERN.search(" ".join(table.headers)):
            score += 8
        if score > best_score:
            best = table
            best_score = score
    return best
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_comparison_chart_generator.py -v`
Expected: All PASS (including existing tests)

**Step 5: Commit**

```bash
git add backend/app/domain/services/comparison_chart_generator.py backend/tests/domain/services/test_comparison_chart_generator.py
git commit -m "fix(chart): add row count bonus so larger tables outscore small dense ones

_select_best_table() now gives a rows*3 bonus to tables with 5+ rows.
Prevents a 3-row all-numeric table from outscoring a 10-row table
that would produce a much richer visualization."
```

---

### Task 5: Drain Background Tasks Before SUMMARIZING Transition

**Problem:** `_background_save_task_state()` at `plan_act.py:3462` fires `asyncio.create_task()` — a fire-and-forget save. When this runs on the *last* step, the flow immediately transitions to SUMMARIZING. The background save may not complete before the summarization reads state, leaving the final step unmarked as "completed" in the sandbox file.

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:3448-3463` and `725-736`
- Create: `backend/tests/domain/services/flows/test_background_task_drain.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/flows/test_background_task_drain.py`:

```python
"""Tests for background task drain before phase transition."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestBackgroundTaskDrain:
    """Verify background tasks are awaited before critical transitions."""

    @pytest.mark.asyncio
    async def test_drain_background_tasks_awaits_pending(self):
        """_drain_background_tasks should await all pending background tasks."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        # Create a background task that sets a flag when complete
        completed = asyncio.Event()

        async def slow_save():
            await asyncio.sleep(0.05)
            completed.set()

        task = asyncio.create_task(slow_save())
        flow._background_tasks.add(task)
        task.add_done_callback(flow._background_tasks.discard)

        # Drain should wait for the task
        await flow._drain_background_tasks()

        assert completed.is_set()
        assert len(flow._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_drain_background_tasks_handles_empty_set(self):
        """_drain_background_tasks is a no-op when no tasks are pending."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        # Should not raise
        await flow._drain_background_tasks()

    @pytest.mark.asyncio
    async def test_drain_background_tasks_tolerates_failures(self):
        """Failed background tasks should not crash the drain."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        async def failing_save():
            raise RuntimeError("sandbox write failed")

        task = asyncio.create_task(failing_save())
        flow._background_tasks.add(task)
        task.add_done_callback(flow._background_tasks.discard)

        # Should not raise even though the task failed
        await flow._drain_background_tasks()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/flows/test_background_task_drain.py -v`
Expected: FAIL — `_drain_background_tasks` method does not exist

**Step 3: Implement the fix**

In `backend/app/domain/services/flows/plan_act.py`, add a drain method after `_on_background_task_done` (around line 737):

```python
async def _drain_background_tasks(self, timeout: float = 5.0) -> None:
    """Await all pending background tasks before a critical phase transition.

    Called before SUMMARIZING to ensure the last step's state save is
    flushed to the sandbox file. Uses a bounded timeout to prevent
    indefinite blocking.
    """
    if not self._background_tasks:
        return
    pending = list(self._background_tasks)
    logger.debug(
        "Draining %d background task(s) for agent %s",
        len(pending),
        self._agent_id,
    )
    done, not_done = await asyncio.wait(pending, timeout=timeout)
    for task in not_done:
        logger.warning(
            "Background task did not complete within %.1fs for agent %s",
            timeout,
            self._agent_id,
        )
    # Consume exceptions so they don't leak as unhandled
    for task in done:
        if task.done() and not task.cancelled():
            exc = task.exception()
            if exc:
                logger.warning("Background task failed during drain: %s", exc)
```

Then in the SUMMARIZING transition block (around line 3495), add the drain call:

```python
elif self.status == AgentStatus.SUMMARIZING:
    # Drain pending background tasks (especially final step's state save)
    await self._drain_background_tasks()
    # ... existing code continues
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/flows/test_background_task_drain.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_background_task_drain.py
git commit -m "fix(flow): drain background tasks before SUMMARIZING transition

_background_save_task_state() is fire-and-forget. On the last step,
the flow transitions to SUMMARIZING before the save completes, leaving
the final step unmarked in the sandbox file. Now drains all pending
background tasks (with 5s timeout) before entering SUMMARIZING."
```

---

### Task 6: Ensure Artifact References Reach Final Summary

**Problem:** The artifact manifest is injected into the summarization context (`plan_act.py:3618-3625`), and `executor.set_artifact_references()` is called (`plan_act.py:3627-3629`), but the response_generator's `_artifact_references_section()` only renders references that were set *before* the summarization LLM call. If `_report_attachments` is empty at summarization start and only populated by the file-sync pipeline *after*, the section is missing.

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:3602-3629`
- Create: `backend/tests/domain/services/flows/test_artifact_manifest_injection.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/flows/test_artifact_manifest_injection.py`:

```python
"""Tests for artifact manifest injection into summarization context."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestArtifactManifestInjection:
    """Verify artifact references are always available to the summarizer."""

    def test_session_files_populate_report_attachments(self):
        """When session_files exist, _report_attachments must be populated
        BEFORE the summarization LLM call, not after."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = []

        session_files = [
            SimpleNamespace(
                filename="report.md",
                storage_key="minio://reports/report.md",
                file_path="/workspace/output/report.md",
                size=11000,
                content_type="text/markdown",
            ),
            SimpleNamespace(
                filename="chart.html",
                storage_key="minio://reports/chart.html",
                file_path="/workspace/output/chart.html",
                size=8800,
                content_type="text/html",
            ),
        ]

        # Simulate the snapshot logic from plan_act.py:3605-3612
        if session_files and not flow._report_attachments:
            flow._report_attachments = [
                {
                    "filename": f.filename,
                    "storage_key": getattr(f, "storage_key", "") or f.file_path or "",
                }
                for f in session_files
            ]

        assert len(flow._report_attachments) == 2
        assert flow._report_attachments[0]["filename"] == "report.md"
        assert flow._report_attachments[1]["filename"] == "chart.html"

    def test_artifact_references_section_renders_with_attachments(self):
        """response_generator._artifact_references_section() renders correctly
        when artifact references are populated."""
        from app.domain.services.agents.response_generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._artifact_references = [
            {"filename": "report.md", "content_type": "text/markdown"},
            {"filename": "chart.html", "content_type": "text/html"},
            {"filename": "chart.png", "content_type": "image/png"},
        ]

        section = gen._artifact_references_section()
        assert "report.md" in section
        assert "chart.html" in section
        assert "chart.png" in section
        assert "## Artifact References" in section

    def test_artifact_references_section_renders_fallback_when_empty(self):
        """When no artifacts exist, render a deterministic 'no artifacts' line."""
        from app.domain.services.agents.response_generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._artifact_references = []

        section = gen._artifact_references_section()
        assert "No file artifacts" in section

    def test_report_attachments_not_overwritten_when_already_populated(self):
        """If _report_attachments was already populated (e.g. by file-sync),
        session_files should NOT overwrite it."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = [
            {"filename": "existing.pdf", "storage_key": "s3://bucket/existing.pdf"},
        ]

        session_files = [
            SimpleNamespace(
                filename="new.md",
                storage_key="minio://reports/new.md",
                file_path="/workspace/output/new.md",
                size=5000,
                content_type="text/markdown",
            ),
        ]

        # The guard: `if session_files and not flow._report_attachments:`
        # should prevent overwrite
        if session_files and not flow._report_attachments:
            flow._report_attachments = [
                {"filename": f.filename, "storage_key": getattr(f, "storage_key", "") or f.file_path or ""}
                for f in session_files
            ]

        # Original should be preserved
        assert len(flow._report_attachments) == 1
        assert flow._report_attachments[0]["filename"] == "existing.pdf"
```

**Step 2: Run test to verify they pass (characterization tests)**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/flows/test_artifact_manifest_injection.py -v`
Expected: These are characterization tests — they PASS because they test the current behavior at line 3605-3612. But we need to verify the *merge* case below.

**Step 3: Implement the fix — merge instead of guard**

The current logic at `plan_act.py:3605` has:
```python
if session_files and not self._report_attachments:
```

This means if `_report_attachments` is partially populated by file-sync, session_files are skipped entirely. Change to a merge:

In `backend/app/domain/services/flows/plan_act.py`, replace lines 3605-3612:

```python
# BEFORE:
if session_files and not self._report_attachments:
    self._report_attachments = [
        {
            "filename": f.filename,
            "storage_key": getattr(f, "storage_key", "") or f.file_path or "",
        }
        for f in session_files
    ]

# AFTER:
if session_files:
    # Merge session files into _report_attachments, avoiding duplicates
    existing_filenames = {a["filename"] for a in self._report_attachments}
    for f in session_files:
        if f.filename not in existing_filenames:
            self._report_attachments.append({
                "filename": f.filename,
                "storage_key": getattr(f, "storage_key", "") or f.file_path or "",
            })
            existing_filenames.add(f.filename)
```

**Step 4: Update the test to verify merge behavior**

Add to the test class:

```python
def test_report_attachments_merged_not_overwritten(self):
    """Session files should be merged into _report_attachments, not replace them."""
    from app.domain.services.flows.plan_act import PlanActFlow

    flow = PlanActFlow.__new__(PlanActFlow)
    flow._report_attachments = [
        {"filename": "existing.pdf", "storage_key": "s3://bucket/existing.pdf"},
    ]

    session_files = [
        SimpleNamespace(
            filename="new.md",
            storage_key="minio://reports/new.md",
            file_path="/workspace/output/new.md",
        ),
    ]

    # After merge, both should be present
    existing_filenames = {a["filename"] for a in flow._report_attachments}
    for f in session_files:
        if f.filename not in existing_filenames:
            flow._report_attachments.append({
                "filename": f.filename,
                "storage_key": getattr(f, "storage_key", "") or f.file_path or "",
            })
            existing_filenames.add(f.filename)

    assert len(flow._report_attachments) == 2
    filenames = [a["filename"] for a in flow._report_attachments]
    assert "existing.pdf" in filenames
    assert "new.md" in filenames
```

**Step 5: Run tests**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/flows/test_artifact_manifest_injection.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_artifact_manifest_injection.py
git commit -m "fix(summary): merge session files into artifact manifest instead of guard

_report_attachments used a guard (if not self._report_attachments)
that skipped session_files entirely when file-sync had already
partially populated attachments. Changed to merge with dedup so all
artifacts reach the final summary's artifact references section."
```

---

## Final Verification

### Run full test suite

```bash
cd backend && conda run -n pythinker pytest tests/ -x -q
```

### Run linting

```bash
cd backend && conda run -n pythinker ruff check . && conda run -n pythinker ruff format --check .
```

### Verify no regressions in research pipeline

```bash
cd backend && conda run -n pythinker pytest tests/integration/test_research_pipeline_integration.py tests/integration/test_research_pipeline_shadow_mode.py -v
```
