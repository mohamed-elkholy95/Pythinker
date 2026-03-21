# E2E Reliability Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor 3 core systems (streaming loop, conversation context, intent classifier) to fix all 6 issues found in E2E testing — session cancellation, follow-up hallucination, status contradiction, cursor format, startup race, and accessibility.

**Architecture:** Extract the streaming/cancellation/heartbeat logic from the 4,250-line `plan_act.py` into dedicated modules (`StreamExecutor`, `ToolExecutorWithHeartbeat`). Expand conversation context capture from 5 to 12 event types with priority-weighted retrieval. Make the intent classifier session-aware via `SessionContextExtractor` to prevent mode downgrade during planned sessions.

**Tech Stack:** Python 3.12, FastAPI, asyncio, Pydantic v2, Qdrant, Vue 3 Composition API, TypeScript

**Spec:** `docs/superpowers/specs/2026-03-21-e2e-reliability-fixes-design.md`

---

## File Structure

### New Files (4)

| File | Responsibility |
|------|---------------|
| `backend/app/domain/services/flows/stream_executor.py` | Streaming loop with idle timeout, cancellation grace, heartbeat interleaving |
| `backend/app/domain/services/flows/tool_executor.py` | Shielded tool dispatch with progress heartbeats |
| `backend/app/domain/services/agents/session_context_extractor.py` | Extract plan/topic summary from session event history |
| `frontend/src/components/report/TaskInterruptedFooter.vue` | Amber "interrupted" footer with retry button |

### Modified Files (Key)

| File | Change |
|------|--------|
| `backend/app/domain/services/flows/plan_act.py:2042-2108` | Replace inline streaming loop with `StreamExecutor` delegation |
| `backend/app/domain/models/event.py:577` | Add `TOOL_EXECUTING` to `PlanningPhase` enum |
| `backend/app/domain/utils/cancellation.py:18` | Add `clear()` method to `CancellationToken` |
| `backend/app/core/config_features.py:137` | Add `cancellation_grace_period_seconds` |
| `backend/app/domain/models/conversation_context.py:15-30` | Expand `TurnRole` (2 new) and `TurnEventType` (7 new) |
| `backend/app/domain/services/conversation_context_service.py:567` | Rewrite `extract_turn_from_event()` for 12 event types |
| `backend/app/domain/services/agents/intent_classifier.py:24,318` | Add session fields to `ClassificationContext`, add guards |
| `backend/app/domain/services/agents/agent_task_factory.py:366` | Wire `SessionContextExtractor` into classification |
| `backend/app/domain/services/prompts/discuss.py:73` | Add `plan_summary` parameter |
| `frontend/src/pages/ChatPage.vue` | Add `isSessionInterrupted` computed, render interrupted footer |
| `frontend/src/components/Suggestions.vue:6-10` | Add ARIA attributes |
| `frontend/src/api/client.ts:947-960` | Fix `lastReceivedEventId` to use SSE `id:` field (not payload UUID) |
| `frontend/src/components/report/index.ts` | Export `TaskInterruptedFooter` from barrel |
| `backend/app/domain/services/prompts/sandbox_context.py:32` | Exponential backoff, 6 retries |
| `backend/app/interfaces/api/session_routes.py` | Clear `disconnect_event` on session reattach |

---

## Phase 1: Stream Executor Extraction

### Task 1: Add `TOOL_EXECUTING` to `PlanningPhase` Enum

**Files:**
- Modify: `backend/app/domain/models/event.py:577-587`
- Test: `backend/tests/domain/models/test_event_enums.py` (create if not exists)

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/models/test_event_enums.py
from app.domain.models.event import PlanningPhase


def test_tool_executing_phase_exists():
    """TOOL_EXECUTING phase must exist for tool heartbeat events."""
    assert hasattr(PlanningPhase, "TOOL_EXECUTING")
    assert PlanningPhase.TOOL_EXECUTING.value == "tool_executing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest tests/domain/models/test_event_enums.py -v -p no:cov -o addopts=`
Expected: FAIL — `AttributeError: TOOL_EXECUTING`

- [ ] **Step 3: Add the enum value**

In `backend/app/domain/models/event.py`, inside `PlanningPhase` enum (after line 587):

```python
    TOOL_EXECUTING = "tool_executing"  # Active tool execution heartbeat
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/models/test_event_enums.py -v -p no:cov -o addopts=`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/models/event.py backend/tests/domain/models/test_event_enums.py
git commit -m "feat(event): add TOOL_EXECUTING to PlanningPhase enum"
```

---

### Task 2: Add `clear()` to `CancellationToken` + Grace Period Config

**Files:**
- Modify: `backend/app/domain/utils/cancellation.py:18`
- Modify: `backend/app/core/config_features.py:137`
- Test: `backend/tests/domain/utils/test_cancellation.py` (create or extend)

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/utils/test_cancellation.py
import asyncio
import pytest
from app.domain.utils.cancellation import CancellationToken


@pytest.mark.asyncio
async def test_clear_resets_cancellation():
    """clear() should reset the token so is_cancelled() returns False."""
    event = asyncio.Event()
    token = CancellationToken(event=event, session_id="test-123")

    event.set()
    assert token.is_cancelled() is True

    token.clear()
    assert token.is_cancelled() is False


@pytest.mark.asyncio
async def test_clear_allows_reuse_after_cancel():
    """After clear(), check_cancelled() should not raise."""
    event = asyncio.Event()
    token = CancellationToken(event=event, session_id="test-456")

    event.set()
    with pytest.raises(asyncio.CancelledError):
        await token.check_cancelled()

    token.clear()
    # Should not raise
    await token.check_cancelled()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/domain/utils/test_cancellation.py -v -p no:cov -o addopts=`
Expected: FAIL — `AttributeError: 'CancellationToken' object has no attribute 'clear'`

- [ ] **Step 3: Implement `clear()` method**

In `backend/app/domain/utils/cancellation.py`, add to `CancellationToken` class:

```python
    def clear(self) -> None:
        """Clear cancellation state (e.g., when client reconnects).

        Resets the internal event so that ``is_cancelled()`` returns False
        and ``check_cancelled()`` no longer raises.
        """
        if self._event is not None:
            self._event.clear()
            self._checked_count = 0
```

- [ ] **Step 4: Add config setting**

In `backend/app/core/config_features.py`, after `workflow_idle_timeout_seconds` (line 137):

```python
    cancellation_grace_period_seconds: int = 5  # Grace before cancelling during tool execution
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/domain/utils/test_cancellation.py -v -p no:cov -o addopts=`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/utils/cancellation.py backend/app/core/config_features.py backend/tests/domain/utils/test_cancellation.py
git commit -m "feat(cancellation): add clear() method and grace period config"
```

---

### Task 3: Create `StreamExecutor`

**Files:**
- Create: `backend/app/domain/services/flows/stream_executor.py`
- Test: `backend/tests/domain/services/flows/test_stream_executor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/services/flows/test_stream_executor.py
import asyncio
import pytest
from unittest.mock import AsyncMock

from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.utils.cancellation import CancellationToken
from app.domain.services.flows.stream_executor import StreamExecutor


async def _events_gen(*events: BaseEvent):
    """Helper: async generator yielding given events."""
    for e in events:
        yield e


@pytest.mark.asyncio
async def test_streams_events_from_inner():
    """StreamExecutor should yield all events from the inner generator."""
    token = CancellationToken(session_id="s1")
    executor = StreamExecutor(
        cancel_token=token, session_id="s1", agent_id="a1",
        wall_clock_timeout=60, idle_timeout=10,
    )
    done = DoneEvent()
    collected = []
    async for event in executor.execute(_events_gen(done)):
        collected.append(event)
    assert len(collected) == 1
    assert isinstance(collected[0], DoneEvent)


@pytest.mark.asyncio
async def test_idle_timeout_emits_error_and_done():
    """When inner stalls beyond idle_timeout, emit ErrorEvent + DoneEvent."""
    token = CancellationToken(session_id="s2")
    executor = StreamExecutor(
        cancel_token=token, session_id="s2", agent_id="a2",
        wall_clock_timeout=60, idle_timeout=1,  # 1 second idle timeout
    )

    async def _stalling_gen():
        yield ProgressEvent(phase="received", message="start")
        await asyncio.sleep(5)  # Stall longer than idle_timeout
        yield DoneEvent()

    collected = []
    async for event in executor.execute(_stalling_gen()):
        collected.append(event)

    # Should get: ProgressEvent, ErrorEvent (timeout), DoneEvent
    assert len(collected) == 3
    assert isinstance(collected[1], ErrorEvent)
    assert "stuck" in collected[1].error.lower() or "timeout" in collected[1].error.lower()
    assert isinstance(collected[2], DoneEvent)


@pytest.mark.asyncio
async def test_cancellation_during_tool_uses_grace_period():
    """During tool execution, cancellation should be delayed by grace period."""
    event = asyncio.Event()
    token = CancellationToken(event=event, session_id="s3")
    executor = StreamExecutor(
        cancel_token=token, session_id="s3", agent_id="a3",
        wall_clock_timeout=60, idle_timeout=30, grace_period=2,
    )

    tool_calling = ToolEvent(
        tool_name="browser_navigate",
        function_name="browser_navigate",
        status=ToolStatus.CALLING,
    )
    tool_called = ToolEvent(
        tool_name="browser_navigate",
        function_name="browser_navigate",
        status=ToolStatus.CALLED,
    )

    async def _tool_gen():
        yield tool_calling
        await asyncio.sleep(0.5)
        # Simulate: disconnect happens here, but we're in tool execution
        event.set()
        await asyncio.sleep(0.5)
        # Clear before grace expires (simulating reconnect)
        event.clear()
        yield tool_called
        yield DoneEvent()

    collected = []
    async for ev in executor.execute(_tool_gen()):
        collected.append(ev)

    # Should complete: tool_calling, tool_called, DoneEvent
    types = [type(e).__name__ for e in collected]
    assert "DoneEvent" in types, f"Expected completion but got: {types}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/domain/services/flows/test_stream_executor.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.services.flows.stream_executor'`

- [ ] **Step 3: Implement `StreamExecutor`**

Create `backend/app/domain/services/flows/stream_executor.py`:

```python
"""Streaming executor with cancellation grace and idle timeout management.

Extracted from plan_act.py:2042-2108 to provide a reusable, testable
streaming loop. Wraps an inner async generator (the actual workflow)
and adds:
- Wall-clock timeout (prevents runaway agents)
- Idle timeout that resets on every yielded event
- Cancellation grace period during tool execution
- Tool-active state tracking via ToolEvent start/complete
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator

from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.utils.cancellation import CancellationToken

logger = logging.getLogger(__name__)


class StreamExecutor:
    """Execute an async event generator with timeout and cancellation."""

    def __init__(
        self,
        cancel_token: CancellationToken,
        session_id: str,
        agent_id: str,
        wall_clock_timeout: int,
        idle_timeout: int,
        grace_period: int = 5,
    ) -> None:
        self._cancel_token = cancel_token
        self._session_id = session_id
        self._agent_id = agent_id
        self._wall_clock_timeout = wall_clock_timeout
        self._idle_timeout = idle_timeout
        self._grace_period = grace_period

    async def execute(
        self,
        inner: AsyncGenerator[BaseEvent, None],
    ) -> AsyncIterator[BaseEvent]:
        """Stream events with timeout, cancellation, and tool-aware grace."""
        try:
            # Initial cancellation check before starting (matches current run() behavior)
            await self._check_cancelled(tool_active=False)

            async with asyncio.timeout(self._wall_clock_timeout):
                inner_iter = inner.__aiter__()
                tool_active = False

                while True:
                    await self._check_cancelled(tool_active=tool_active)

                    try:
                        async with asyncio.timeout(self._idle_timeout):
                            event = await inner_iter.__anext__()
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        idle_mins = self._idle_timeout // 60
                        logger.warning(
                            "Agent %s idle timeout after %ds for session %s",
                            self._agent_id,
                            self._idle_timeout,
                            self._session_id,
                        )
                        yield ErrorEvent(
                            error=f"The agent hasn't produced output for "
                            f"{idle_mins} minutes and may be stuck.",
                            error_type="timeout",
                            recoverable=True,
                            can_resume=True,
                            error_code="workflow_idle_timeout",
                        )
                        yield DoneEvent()
                        return

                    # Track tool execution state for grace period
                    if isinstance(event, ToolEvent):
                        if event.status == ToolStatus.CALLING:
                            tool_active = True
                        elif event.status == ToolStatus.CALLED:
                            tool_active = False

                    yield event

        except asyncio.CancelledError:
            logger.info(
                "StreamExecutor: workflow cancelled for session %s",
                self._session_id,
            )
            raise
        except TimeoutError:
            wall_mins = self._wall_clock_timeout // 60
            logger.error(
                "Agent %s wall-clock timeout after %ds for session %s",
                self._agent_id,
                self._wall_clock_timeout,
                self._session_id,
            )
            yield ErrorEvent(
                error=f"The task reached the {wall_mins}-minute time limit.",
                error_type="timeout",
                recoverable=True,
                can_resume=True,
                error_code="workflow_wall_clock_timeout",
            )
            yield DoneEvent()

    async def _check_cancelled(self, tool_active: bool = False) -> None:
        """Check cancellation with grace period during tool execution."""
        if not self._cancel_token.is_cancelled():
            return
        if tool_active and self._grace_period > 0:
            logger.info(
                "StreamExecutor: disconnect detected during tool execution, "
                "waiting %ds grace period for session %s",
                self._grace_period,
                self._session_id,
            )
            await asyncio.sleep(self._grace_period)
            if not self._cancel_token.is_cancelled():
                logger.info(
                    "StreamExecutor: client reconnected during grace for %s",
                    self._session_id,
                )
                return
        raise asyncio.CancelledError(f"Session {self._session_id} cancelled")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/domain/services/flows/test_stream_executor.py -v -p no:cov -o addopts=`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/services/flows/stream_executor.py backend/tests/domain/services/flows/test_stream_executor.py
git commit -m "feat(streaming): add StreamExecutor with cancellation grace and idle timeout"
```

---

### Task 4: Create `ToolExecutorWithHeartbeat`

**Files:**
- Create: `backend/app/domain/services/flows/tool_executor.py`
- Test: `backend/tests/domain/services/flows/test_tool_executor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/services/flows/test_tool_executor.py
import asyncio
import pytest

from app.domain.models.event import PlanningPhase, ProgressEvent
from app.domain.services.flows.tool_executor import ToolExecutorWithHeartbeat


@pytest.mark.asyncio
async def test_heartbeat_emitted_during_slow_tool():
    """Heartbeat events should be emitted during tool execution > interval."""
    executor = ToolExecutorWithHeartbeat(interval_seconds=0.3)

    async def slow_tool(_call):
        await asyncio.sleep(1.0)  # Simulate slow tool
        return {"result": "done"}

    mock_call = type("ToolCall", (), {"name": "browser_navigate"})()
    events = []
    async for event in executor.execute(mock_call, slow_tool):
        events.append(event)

    heartbeats = [e for e in events if isinstance(e, ProgressEvent)]
    assert len(heartbeats) >= 2, f"Expected >=2 heartbeats, got {len(heartbeats)}"
    assert all(e.phase == PlanningPhase.TOOL_EXECUTING for e in heartbeats)


@pytest.mark.asyncio
async def test_tool_result_yielded_after_heartbeats():
    """The actual tool result should be yielded after heartbeats."""
    executor = ToolExecutorWithHeartbeat(interval_seconds=0.2)

    async def fast_tool(_call):
        await asyncio.sleep(0.5)
        return {"result": "ok"}

    mock_call = type("ToolCall", (), {"name": "search"})()
    events = []
    async for event in executor.execute(mock_call, fast_tool):
        events.append(event)

    # Last non-heartbeat event should be the tool result
    non_heartbeats = [e for e in events if not isinstance(e, ProgressEvent)]
    assert len(non_heartbeats) == 1
    assert non_heartbeats[0] == {"result": "ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/domain/services/flows/test_tool_executor.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `ToolExecutorWithHeartbeat`**

Create `backend/app/domain/services/flows/tool_executor.py`:

```python
"""Shielded tool execution with progress heartbeats.

Wraps tool calls with LLMHeartbeat + interleave_heartbeat so that
long-running tools (browser, search) emit ProgressEvent every N seconds,
keeping the idle timeout alive in StreamExecutor.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Awaitable, Callable

from app.domain.models.event import BaseEvent, PlanningPhase, ProgressEvent
from app.domain.services.flows.llm_heartbeat import LLMHeartbeat, interleave_heartbeat

logger = logging.getLogger(__name__)


class ToolExecutorWithHeartbeat:
    """Execute tool calls with heartbeat emission for long-running operations."""

    def __init__(self, interval_seconds: float = 5.0) -> None:
        self._interval = interval_seconds

    async def execute(
        self,
        tool_call: Any,
        execute_fn: Callable[..., Awaitable[Any]],
    ) -> AsyncIterator[BaseEvent]:
        """Execute a tool call, yielding heartbeats during execution.

        Args:
            tool_call: The tool call object (must have .name attribute)
            execute_fn: Async callable that executes the tool call
        """
        tool_name = getattr(tool_call, "name", "unknown")
        heartbeat = LLMHeartbeat(
            phase=PlanningPhase.TOOL_EXECUTING,
            message=f"Running {tool_name}...",
            interval_seconds=self._interval,
        )

        async def _tool_gen() -> AsyncGenerator[Any, None]:
            result = await execute_fn(tool_call)
            yield result

        async with heartbeat:
            async for event in interleave_heartbeat(_tool_gen(), heartbeat):
                yield event
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/domain/services/flows/test_tool_executor.py -v -p no:cov -o addopts=`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/services/flows/tool_executor.py backend/tests/domain/services/flows/test_tool_executor.py
git commit -m "feat(streaming): add ToolExecutorWithHeartbeat for tool-level heartbeats"
```

---

### Task 5: Integrate `StreamExecutor` into `plan_act.py`

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:2042-2108`

- [ ] **Step 1: Read the current `run()` method**

Read `backend/app/domain/services/flows/plan_act.py` lines 2042-2110 to understand the current inline streaming loop.

- [ ] **Step 2: Replace with `StreamExecutor` delegation**

Replace the `run()` method body (lines 2042-2108) with:

```python
    async def run(self, message: Message) -> AsyncIterator[BaseEvent]:
        from app.domain.services.flows.stream_executor import StreamExecutor

        settings = get_settings()
        tracer = get_tracer()

        with tracer.trace(
            "agent-run",
            agent_id=self._agent_id,
            session_id=self._session_id,
            attributes={"message.preview": message.message[:100]},
        ) as trace_ctx:
            executor = StreamExecutor(
                cancel_token=self._cancel_token,
                session_id=self._session_id,
                agent_id=self._agent_id,
                wall_clock_timeout=settings.max_execution_time_seconds,
                idle_timeout=settings.effective_workflow_idle_timeout,
                grace_period=settings.cancellation_grace_period_seconds,
            )
            async for event in executor.execute(
                self._run_with_trace(message, trace_ctx)
            ):
                yield event
```

Keep the existing `_run_with_trace()` method (line 2110+) untouched.

- [ ] **Step 3: Clear disconnect event on session reattach**

In `backend/app/interfaces/api/session_routes.py`, find where a new SSE connection opens for an already-running session. Add `disconnect_event.clear()` to signal reconnection.

- [ ] **Step 4: Run existing backend tests**

Run: `cd backend && conda activate pythinker && pytest tests/ -x -p no:cov -o addopts= --timeout=30`
Expected: PASS (no regressions)

- [ ] **Step 5: Run linting**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/app/interfaces/api/session_routes.py
git commit -m "refactor(plan_act): extract streaming loop into StreamExecutor"
```

---

### Task 6: Frontend — Interrupted State + Footer

**Files:**
- Create: `frontend/src/components/report/TaskInterruptedFooter.vue`
- Modify: `frontend/src/pages/ChatPage.vue`

- [ ] **Step 1: Create `TaskInterruptedFooter.vue`**

```vue
<template>
  <div class="interrupted-footer">
    <div class="interrupted-status">
      <AlertTriangle class="interrupted-icon" />
      <span class="status-text">{{ $t('Task was interrupted') }}</span>
    </div>
    <button class="retry-button" @click="$emit('retry')">
      <RefreshCw class="retry-icon" />
      {{ $t('Retry') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'

defineEmits<{
  (e: 'retry'): void
}>()
</script>

<style scoped>
.interrupted-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-warning-bg, #fffbeb);
  border: 1px solid var(--color-warning-border, #fcd34d);
  border-radius: 8px;
  margin-top: 12px;
}

.interrupted-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.interrupted-icon {
  width: 18px;
  height: 18px;
  color: var(--color-warning, #d97706);
}

.status-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-warning-text, #92400e);
}

.retry-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-warning-text, #92400e);
  background: transparent;
  border: 1px solid var(--color-warning-border, #fcd34d);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.retry-button:hover {
  background: var(--color-warning-hover, #fef3c7);
}

.retry-icon {
  width: 14px;
  height: 14px;
}
</style>
```

- [ ] **Step 2: Export from `report/index.ts`**

Add to `frontend/src/components/report/index.ts`:

```typescript
export { default as TaskInterruptedFooter } from './TaskInterruptedFooter.vue'
```

- [ ] **Step 3: Add interrupted state to `ChatPage.vue`**

Add computed property and render the footer. Find the section where `TaskCompletedFooter` is rendered and add the interrupted variant alongside it.

```typescript
// Add computed:
const isSessionInterrupted = computed(() =>
  sessionStatus.value === SessionStatus.CANCELLED &&
  events.value.length > 0
)

// Add handler:
const handleRetryInterrupted = () => {
  // Resubmit the original user message
  const originalMessage = events.value.find(
    (e: any) => e.type === 'message' && e.role === 'user'
  )
  if (originalMessage) {
    inputMessage.value = originalMessage.message
    handleSubmit()
  }
}
```

Add template (near existing `TaskCompletedFooter`):

```vue
<TaskInterruptedFooter
  v-if="isSessionInterrupted && !isSessionRunning"
  @retry="handleRetryInterrupted"
/>
```

- [ ] **Step 4: Run frontend lint and type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/TaskInterruptedFooter.vue frontend/src/components/report/index.ts frontend/src/pages/ChatPage.vue
git commit -m "feat(frontend): add TaskInterruptedFooter for cancelled sessions"
```

---

## Phase 2: Conversation Context Service Redesign

### Task 7: Expand Enums in `conversation_context.py`

**Files:**
- Modify: `backend/app/domain/models/conversation_context.py:15-30`
- Test: `backend/tests/domain/models/test_conversation_context.py` (create if not exists)

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/models/test_conversation_context.py
from app.domain.models.conversation_context import TurnRole, TurnEventType


def test_turn_role_has_plan_and_thought():
    assert hasattr(TurnRole, "PLAN_SUMMARY")
    assert hasattr(TurnRole, "THOUGHT")


def test_turn_event_type_has_all_new_types():
    new_types = [
        "PLAN", "THOUGHT", "REFLECTION", "VERIFICATION",
        "COMPREHENSION", "MODE_CHANGE", "TASK_RECREATION",
    ]
    for t in new_types:
        assert hasattr(TurnEventType, t), f"Missing TurnEventType.{t}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/models/test_conversation_context.py -v -p no:cov -o addopts=`
Expected: FAIL

- [ ] **Step 3: Add the new enum values**

In `backend/app/domain/models/conversation_context.py`:

Add to `TurnRole` (after line 21):
```python
    PLAN_SUMMARY = "plan_summary"
    THOUGHT = "thought"
```

Add to `TurnEventType` (after line 31):
```python
    PLAN = "plan"
    THOUGHT = "thought"
    REFLECTION = "reflection"
    VERIFICATION = "verification"
    COMPREHENSION = "comprehension"
    MODE_CHANGE = "mode_change"
    TASK_RECREATION = "task_recreation"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/models/test_conversation_context.py -v -p no:cov -o addopts=`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/models/conversation_context.py backend/tests/domain/models/test_conversation_context.py
git commit -m "feat(context): expand TurnRole and TurnEventType enums for 12 event types"
```

---

### Task 8: Rewrite `extract_turn_from_event()` for 12 Event Types

**Files:**
- Modify: `backend/app/domain/services/conversation_context_service.py:567-652`
- Test: `backend/tests/domain/services/test_conversation_context_extraction.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/services/test_conversation_context_extraction.py
import pytest
from unittest.mock import MagicMock
from app.domain.services.conversation_context_service import ConversationContextService
from app.domain.models.event import (
    PlanEvent, PlanStatus, ThoughtEvent, ThoughtStatus,
    ReflectionEvent, ReflectionStatus, VerificationEvent, VerificationStatus,
    ComprehensionEvent, ModeChangeEvent, TaskRecreationEvent,
)
from app.domain.models.conversation_context import TurnEventType, TurnRole


@pytest.fixture
def service():
    """Minimal ConversationContextService for extraction tests."""
    svc = ConversationContextService.__new__(ConversationContextService)
    svc._min_content_length = 10
    svc._seen_hashes = set()
    return svc


def _make_plan_event():
    plan = MagicMock()
    plan.title = "Top 3 AI Frameworks"
    step1 = MagicMock()
    step1.description = "Research frameworks"
    step2 = MagicMock()
    step2.description = "Compare features"
    plan.steps = [step1, step2]
    return PlanEvent(plan=plan, status=PlanStatus.CREATED)


def test_extract_plan_event(service):
    event = _make_plan_event()
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.role == TurnRole.PLAN_SUMMARY
    assert turn.event_type == TurnEventType.PLAN
    assert "Top 3 AI Frameworks" in turn.content
    assert "Research frameworks" in turn.content


def test_extract_plan_event_skips_updated(service):
    plan = MagicMock()
    plan.title = "Test"
    plan.steps = []
    event = PlanEvent(plan=plan, status=PlanStatus.UPDATED)
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is None


def test_extract_thought_event_final(service):
    event = ThoughtEvent(
        status=ThoughtStatus.CHAIN_COMPLETE,
        thought_type="analysis",
        content="The data shows clear trends in framework adoption",
        confidence=0.85,
        is_final=True,
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.role == TurnRole.THOUGHT
    assert turn.event_type == TurnEventType.THOUGHT


def test_extract_thought_event_skips_non_final(service):
    event = ThoughtEvent(
        status=ThoughtStatus.THINKING,
        thought_type="analysis",
        content="Still thinking...",
        is_final=False,
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is None


def test_extract_mode_change_event(service):
    event = ModeChangeEvent(mode="discuss", reason="follow-up question")
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.event_type == TurnEventType.MODE_CHANGE
    assert "discuss" in turn.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/domain/services/test_conversation_context_extraction.py -v -p no:cov -o addopts=`
Expected: FAIL — new event types not handled

- [ ] **Step 3: Rewrite `extract_turn_from_event()` method**

Replace the method body at line 567 in `conversation_context_service.py` with the expanded extraction using `match/case` as specified in the design spec. Handle all 12 event types with appropriate content extraction, roles, and event types.

Reference: spec section "Phase 2: Conversation Context Service Redesign", subsection 2.1.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/domain/services/test_conversation_context_extraction.py -v -p no:cov -o addopts=`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Run full backend tests for regressions**

Run: `cd backend && pytest tests/ -x -p no:cov -o addopts= --timeout=30`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/services/conversation_context_service.py backend/tests/domain/services/test_conversation_context_extraction.py
git commit -m "refactor(context): expand extract_turn_from_event to 12 event types"
```

---

## Phase 3: Session-Aware Intent Classifier

### Task 9: Create `SessionContextExtractor`

**Files:**
- Create: `backend/app/domain/services/agents/session_context_extractor.py`
- Test: `backend/tests/domain/services/agents/test_session_context_extractor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/services/agents/test_session_context_extractor.py
from unittest.mock import MagicMock
from app.domain.services.agents.session_context_extractor import (
    SessionContextExtractor,
    SessionExecutionContext,
)
from app.domain.models.event import PlanEvent, PlanStatus, StepEvent, StepStatus


def _make_session(events=None):
    session = MagicMock()
    session.events = events or []
    session.title = "Test Session"
    return session


def _make_plan_event(title="AI Frameworks Research"):
    plan = MagicMock()
    plan.title = title
    step = MagicMock()
    step.description = "Search web"
    plan.steps = [step]
    return PlanEvent(plan=plan, status=PlanStatus.CREATED)


def _make_step_completed():
    step = MagicMock()
    step.description = "Search web"
    return StepEvent(step=step, status=StepStatus.COMPLETED)


def test_extract_session_with_plan():
    plan_event = _make_plan_event("AI Frameworks Research")
    session = _make_session([plan_event, _make_step_completed()])
    ctx = SessionContextExtractor.extract(session)
    assert ctx.had_plan is True
    assert ctx.plan_title == "AI Frameworks Research"
    assert ctx.completed_steps == 1
    assert len(ctx.plan_steps) == 1


def test_extract_session_without_plan():
    session = _make_session([])
    ctx = SessionContextExtractor.extract(session)
    assert ctx.had_plan is False
    assert ctx.plan_title is None
    assert ctx.completed_steps == 0


def test_to_plan_summary_formatted():
    plan_event = _make_plan_event("Compare Frameworks")
    session = _make_session([plan_event])
    ctx = SessionContextExtractor.extract(session)
    summary = ctx.to_plan_summary()
    assert "Compare Frameworks" in summary
    assert "Search web" in summary
    assert "0/1" in summary


def test_to_plan_summary_empty_when_no_plan():
    session = _make_session([])
    ctx = SessionContextExtractor.extract(session)
    assert ctx.to_plan_summary() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/domain/services/agents/test_session_context_extractor.py -v -p no:cov -o addopts=`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `SessionContextExtractor`**

Create `backend/app/domain/services/agents/session_context_extractor.py` with the implementation from the spec (Phase 3, section 3.3).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/domain/services/agents/test_session_context_extractor.py -v -p no:cov -o addopts=`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/services/agents/session_context_extractor.py backend/tests/domain/services/agents/test_session_context_extractor.py
git commit -m "feat(classifier): add SessionContextExtractor for session-aware classification"
```

---

### Task 10: Add Session Guards to Intent Classifier

**Files:**
- Modify: `backend/app/domain/services/agents/intent_classifier.py:24,318`
- Test: `backend/tests/domain/services/agents/test_intent_classifier_guards.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/services/agents/test_intent_classifier_guards.py
from app.domain.services.agents.intent_classifier import (
    ClassificationContext,
    get_intent_classifier,
)
from app.domain.models.session import AgentMode, SessionStatus


def test_blocks_agent_to_discuss_when_session_has_plan():
    """Follow-up in a planned session should NOT downgrade to DISCUSS."""
    classifier = get_intent_classifier()
    ctx = ClassificationContext(
        attachments=[],
        available_skills=[],
        conversation_length=10,
        is_follow_up=True,
        urls=[],
        mcp_tools=[],
        session_mode=AgentMode.AGENT,
        session_had_plan=True,
        session_plan_title="AI Agent Frameworks Research",
    )
    result = classifier.classify_with_context(
        "Can you expand on the comparison?", ctx
    )
    assert result.mode == AgentMode.AGENT, (
        f"Expected AGENT but got {result.mode} — guard failed"
    )


def test_allows_discuss_when_no_plan():
    """Fresh session with no plan should allow DISCUSS mode."""
    classifier = get_intent_classifier()
    ctx = ClassificationContext(
        attachments=[],
        available_skills=[],
        conversation_length=0,
        is_follow_up=False,
        urls=[],
        mcp_tools=[],
        session_mode=AgentMode.AGENT,
        session_had_plan=False,
    )
    result = classifier.classify_with_context("hello", ctx)
    assert result.mode == AgentMode.DISCUSS
```

- [ ] **Step 2: Run tests to verify first one fails**

Run: `cd backend && pytest tests/domain/services/agents/test_intent_classifier_guards.py -v -p no:cov -o addopts=`
Expected: First test FAILS (no session guard), second test PASSES

- [ ] **Step 3: Add session fields to `ClassificationContext`**

At line 24 in `intent_classifier.py`, add to the `ClassificationContext` dataclass:

```python
    # Session execution awareness
    session_mode: AgentMode | None = None
    session_had_plan: bool = False
    session_plan_title: str | None = None
    session_status: SessionStatus | None = None
    session_completed_steps: int = 0
```

Import `AgentMode` and `SessionStatus` at the top.

- [ ] **Step 4: Add session guards to `classify_with_context()`**

At line 318, inside `classify_with_context()`, add the guard logic BEFORE the existing context-aware enhancements:

```python
        # Session-aware guard: prevent AGENT→DISCUSS downgrade for planned sessions
        if (
            context is not None
            and context.session_mode == AgentMode.AGENT
            and mode == AgentMode.DISCUSS
            and context.session_had_plan
        ):
            reasons.append(
                f"BLOCKED: AGENT→DISCUSS downgrade prevented — "
                f"session has plan '{context.session_plan_title}'"
            )
            return ClassificationResult(
                intent="follow_up_to_planned_task",
                mode=AgentMode.AGENT,
                confidence=0.90,
                reasons=reasons,
                context_signals={"plan_guard_active": True},
            )
```

- [ ] **Step 5: Add Guard 2 — continuation phrase detection**

After Guard 1, add Guard 2 for continuation phrases in planned sessions.
The `_is_continuation_phrase()` method checks if the message uses continuation
language ("do it", "go ahead", "continue", "proceed", "yes please"):

```python
        # Guard 2: Continuation phrases in planned session → stay AGENT
        if (
            context is not None
            and context.is_follow_up
            and context.session_had_plan
            and self._is_continuation_phrase(message)
        ):
            reasons.append("Continuation phrase in planned session → AGENT")
            return ClassificationResult(
                intent="continuation",
                mode=AgentMode.AGENT,
                confidence=0.95,
                reasons=reasons,
                context_signals={"continuation_in_plan": True},
            )
```

Add the helper method to `IntentClassifier`:

```python
    _CONTINUATION_PATTERNS: ClassVar[list[str]] = [
        r"^(do it|go ahead|continue|proceed|yes|yes please|ok do it|sure)[\s!.]*$",
        r"^(keep going|carry on|finish it|complete it)[\s!.]*$",
    ]

    def _is_continuation_phrase(self, message: str) -> bool:
        """Check if message is a continuation/approval phrase."""
        normalized = message.lower().strip()
        return any(
            re.match(p, normalized, re.IGNORECASE)
            for p in self._CONTINUATION_PATTERNS
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/domain/services/agents/test_intent_classifier_guards.py -v -p no:cov -o addopts=`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/domain/services/agents/intent_classifier.py backend/tests/domain/services/agents/test_intent_classifier_guards.py
git commit -m "feat(classifier): add session-aware guards to prevent mode downgrade"
```

---

### Task 11: Wire `SessionContextExtractor` into `agent_task_factory.py` + Discuss Prompt

**Files:**
- Modify: `backend/app/domain/services/agents/agent_task_factory.py:366`
- Modify: `backend/app/domain/services/prompts/discuss.py:73`

- [ ] **Step 1: Wire extractor into `classify_intent_with_context()`**

In `agent_task_factory.py` at line ~399, add before the `ClassificationContext` creation:

```python
        from app.domain.services.agents.session_context_extractor import (
            SessionContextExtractor,
        )
        exec_ctx = SessionContextExtractor.extract(session)
```

Add to the `ClassificationContext` constructor:

```python
            session_mode=session.mode,
            session_had_plan=exec_ctx.had_plan,
            session_plan_title=exec_ctx.plan_title,
            session_status=session.status,
            session_completed_steps=exec_ctx.completed_steps,
```

- [ ] **Step 2: Add `plan_summary` to discuss prompt**

In `backend/app/domain/services/prompts/discuss.py` at line 73, add the `plan_summary` parameter and inject it as a `<prior_task_context>` block, as specified in the design spec (Phase 3, section 3.5).

- [ ] **Step 3: Wire plan summary at the call site**

Find where `build_discuss_prompt()` is called and pass `plan_summary=exec_ctx.to_plan_summary()` from the session context.

- [ ] **Step 4: Run linting**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: No errors

- [ ] **Step 5: Run full backend tests**

Run: `cd backend && pytest tests/ -x -p no:cov -o addopts= --timeout=30`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/services/agents/agent_task_factory.py backend/app/domain/services/prompts/discuss.py
git commit -m "feat(context): wire SessionContextExtractor into classifier and discuss prompt"
```

---

## Phase 4: Event Resume, Startup, & Frontend Polish

### Task 12: Fix Resume Cursor Format (Frontend)

**Files:**
- Modify: `frontend/src/api/client.ts:947-960`

- [ ] **Step 1: Find and fix the `lastReceivedEventId` assignment**

In `client.ts` around lines 947-960, find where `lastReceivedEventId` is set from the JSON
payload's `event_id` (UUID format like `"e70a6c37-..."`). The SSE transport-level `id:` field
(accessed as `event.id` in fetch-event-source or `nativeEventId` in native EventSource) contains
the correct Redis stream format (`"1234567890-0"`).

Fix: prefer the SSE `id:` field over the payload UUID:

```typescript
// Fix: Use SSE id: field (Redis stream format) over payload event_id (UUID)
const sseId = event.id;  // SSE transport-level id: field
if (sseId) {
    lastReceivedEventId = sseId;
} else if (eventId) {
    lastReceivedEventId = eventId;  // Fallback to payload UUID
}
```

Also check line ~819 where `resumeBody.event_id = lastReceivedEventId` is set — this
now sends the correct Redis format to the backend.

- [ ] **Step 2: Run frontend lint and type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "fix(sse): use Redis stream ID format for resume cursor"
```

---

### Task 13: Fix Sandbox Context Startup Race

**Files:**
- Modify: `backend/app/domain/services/prompts/sandbox_context.py:32`
- Modify: `backend/app/core/lifespan.py`

- [ ] **Step 1: Update retry parameters AND formula (both changes required)**

In `sandbox_context.py`, make THREE changes together:

**Change 1** — at line 32, update constants:
```python
_RETRY_ATTEMPTS = 6        # was 3
_RETRY_BASE_DELAY = 1.0    # was 2.0
```

**Change 2** — in `load_context_with_retry()` at line ~65, change the delay formula
from linear to exponential:
```python
# OLD (linear): delay = cls._RETRY_BASE_DELAY * (attempt + 1)
# NEW (exponential):
delay = cls._RETRY_BASE_DELAY * (2 ** attempt)
# Produces: 1s, 2s, 4s, 8s, 16s = ~31s total coverage
```

**Important**: Use `cls._RETRY_BASE_DELAY` (classmethod), NOT `self._RETRY_BASE_DELAY`.

- [ ] **Step 2: Add tracked background reload task in lifespan**

In `lifespan.py`, after the initial sandbox context load attempt, add:

```python
async def _reload_sandbox_context_on_ready():
    """Background task: reload sandbox context once sandbox is healthy."""
    from app.domain.services.prompts.sandbox_context import SandboxContextManager
    for _ in range(10):
        await asyncio.sleep(6)
        result = await SandboxContextManager.load_context_with_retry()
        if result is not None:
            logger.info("Sandbox context loaded after delayed retry")
            return
    logger.warning("Sandbox context never became available")

sandbox_reload_task = asyncio.create_task(_reload_sandbox_context_on_ready())
```

Ensure `sandbox_reload_task.cancel()` is called in the shutdown block.

- [ ] **Step 3: Run linting**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add backend/app/domain/services/prompts/sandbox_context.py backend/app/core/lifespan.py
git commit -m "fix(startup): exponential backoff for sandbox context with background reload"
```

---

### Task 14: Suggestions Accessibility

**Files:**
- Modify: `frontend/src/components/Suggestions.vue:6-10`

- [ ] **Step 1: Add ARIA attributes**

Replace lines 6-10 in `Suggestions.vue`:

```html
    <div
      v-for="(suggestion, index) in suggestions"
      :key="index"
      class="suggestion-item"
      role="button"
      tabindex="0"
      :aria-label="suggestion"
      @click="$emit('select', suggestion)"
      @keydown.enter="$emit('select', suggestion)"
      @keydown.space.prevent="$emit('select', suggestion)"
    >
```

- [ ] **Step 2: Run frontend lint**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Suggestions.vue
git commit -m "fix(a11y): add ARIA button role and keyboard handlers to Suggestions"
```

---

### Task 15: Dependency Pinning + Stale Session Cleanup

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/application/services/maintenance_service.py`

- [ ] **Step 1: Pin dependency versions**

Add to `backend/requirements.txt` (if not already present):

```
urllib3>=2.0,<2.6
charset-normalizer>=3.0,<3.4
```

- [ ] **Step 2: Add stale session cleanup**

In `maintenance_service.py`, in the periodic cleanup method, add logic to delete sessions where:
- `title is None`
- `status == SessionStatus.CANCELLED`
- `latest_message is None`
- `created_at < now - 24 hours`

- [ ] **Step 3: Run linting**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/app/application/services/maintenance_service.py
git commit -m "chore: pin urllib3/charset-normalizer versions, add stale session cleanup"
```

---

## Verification: Full E2E Retest

### Task 16: End-to-End Verification

- [ ] **Step 1: Rebuild and restart stack**

```bash
./dev.sh down -v && ./dev.sh watch
```

- [ ] **Step 2: Verify no startup warnings**

```bash
docker logs pythinker-backend-1 --tail 50 2>&1 | grep -E '(ERROR|WARNING|warn)'
```
Expected: No sandbox context warnings after ~15s. No urllib3/chardet warnings.

- [ ] **Step 3: Run a research task via browser**

Navigate to `http://localhost:5174`, submit a research task, verify:
- Task completes without cancellation
- Sandbox screencast visible
- No console 404 errors (or fewer)

- [ ] **Step 4: Test follow-up question**

After research completes, submit a follow-up about the same topic. Verify:
- Response is about the SAME topic (no hallucination)
- Mode stays AGENT (check backend logs for "BLOCKED" guard message)

- [ ] **Step 5: Test interruption UI**

During a running task, refresh the page. Verify:
- SSE reconnects with correct cursor format
- No "cursor not a Redis stream ID" warning in logs
- If task was interrupted, amber footer shows (not green "Task completed")

- [ ] **Step 6: Test suggestions accessibility**

After task completion, verify follow-up suggestions:
- Tab key navigates between suggestions
- Enter key triggers suggestion
- Screen reader announces "button" role

- [ ] **Step 7: Run full test suite**

```bash
cd backend && conda activate pythinker && ruff check . && ruff format --check . && pytest tests/ -p no:cov -o addopts=
cd frontend && bun run lint && bun run type-check
```
Expected: All pass
