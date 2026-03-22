# Agent Responsiveness & UI Pipeline Optimization

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce perceived time-to-first-useful-output from ~62s to <15s for research tasks by filling UI dark periods, fast-tracking planning, emitting partial results, and adding cancellation support.

**Architecture:** Six phases, ordered by impact-per-effort. Phase 1-2 are backend-only (fill event gaps, fast draft plan). Phase 3-4 are frontend+backend (phase timeline UI, partial outputs). Phase 5-6 are backend refinements (latency budgets, cancel/retry). Each phase is independently shippable and feature-flagged.

**Tech Stack:** Python 3.12, FastAPI, asyncio, Pydantic v2, Vue 3 Composition API, TypeScript, SSE

**Practical Targets:**

| Metric | Before | After Phase 2 | After Phase 4 |
|--------|--------|---------------|---------------|
| Time-to-acknowledgment | ~100ms | ~100ms | ~100ms |
| Time-to-first-phase-update | ~5.1s | <1s | <1s |
| Time-to-first-search | ~62s | ~8-12s | ~8-12s |
| Time-to-first-partial-answer | ~62s+ | ~20s | ~15s |

---

## Phase 1: Fill the Dark Periods (Backend)

**Problem:** The backend goes silent for 12-25s during verification and execution reasoning. The frontend has no events to render, making it look frozen.

**Solution:** Emit `ProgressEvent` at verification start/end, execution reasoning start, and periodic 2-3s heartbeats during LLM calls.

---

### Task 1.1: Add Verification Phase Events

**Files:**
- Modify: `backend/app/domain/models/event.py:559-568` (PlanningPhase enum)
- Modify: `backend/app/domain/services/flows/plan_act.py` (verification section)
- Test: `backend/tests/domain/services/flows/test_plan_act_progress_events.py`

**Step 1: Extend PlanningPhase enum**

In `backend/app/domain/models/event.py`, add two new phases to the `PlanningPhase` enum:

```python
class PlanningPhase(str, Enum):
    RECEIVED = "received"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    VERIFYING = "verifying"        # NEW
    EXECUTING_SETUP = "executing_setup"  # NEW
    FINALIZING = "finalizing"
    HEARTBEAT = "heartbeat"
    WAITING = "waiting"
```

**Step 2: Write the failing test**

Create `backend/tests/domain/services/flows/test_plan_act_progress_events.py`:

```python
"""Tests that PlanActFlow emits progress events during dark periods."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.domain.models.event import PlanningPhase, ProgressEvent


@pytest.mark.asyncio
async def test_verification_emits_verifying_progress_event():
    """Verification phase must emit a ProgressEvent with phase=VERIFYING before calling the verifier."""
    # We'll collect events from the flow and assert VERIFYING appears
    # Exact setup depends on how plan_act.py is instantiated in tests —
    # follow the pattern in existing tests/domain/services/flows/ test files.
    # Key assertion:
    events = []  # collect from async generator
    verifying_events = [e for e in events if isinstance(e, ProgressEvent) and e.phase == PlanningPhase.VERIFYING]
    assert len(verifying_events) >= 1, "Expected at least one VERIFYING progress event"


@pytest.mark.asyncio
async def test_execution_setup_emits_progress_event():
    """Transition from plan-created to first tool call must emit EXECUTING_SETUP event."""
    events = []
    setup_events = [e for e in events if isinstance(e, ProgressEvent) and e.phase == PlanningPhase.EXECUTING_SETUP]
    assert len(setup_events) >= 1, "Expected EXECUTING_SETUP progress event before first tool call"
```

**Step 3: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest tests/domain/services/flows/test_plan_act_progress_events.py -v`
Expected: FAIL (no VERIFYING events emitted yet)

**Step 4: Emit ProgressEvent at verification boundaries in plan_act.py**

In `plan_act.py`, locate the verification section (around the `AgentStatus.VERIFYING` transition). Add yields:

```python
# Before calling verifier
yield ProgressEvent(
    phase=PlanningPhase.VERIFYING,
    message="Checking plan quality...",
    progress_percent=None,  # indeterminate — we don't know how long verification takes
)

# ... existing verification call ...

# After verification completes (before transitioning to EXECUTING)
yield ProgressEvent(
    phase=PlanningPhase.EXECUTING_SETUP,
    message="Preparing to execute plan...",
    progress_percent=0,
)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/services/flows/test_plan_act_progress_events.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/domain/models/event.py backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_plan_act_progress_events.py
git commit -m "feat(agent): emit progress events during verification and execution setup"
```

---

### Task 1.2: Add Periodic LLM-Call Heartbeats

**Problem:** During planning (~18s) and verification (~12s), zero events are emitted. The SSE connection heartbeat is 30s — too slow to feel alive.

**Files:**
- Create: `backend/app/domain/services/flows/llm_heartbeat.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Test: `backend/tests/domain/services/flows/test_llm_heartbeat.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/flows/test_llm_heartbeat.py`:

```python
"""Tests for LLM heartbeat emitter during long-running calls."""
import asyncio
import pytest
from app.domain.services.flows.llm_heartbeat import LLMHeartbeat
from app.domain.models.event import PlanningPhase, ProgressEvent


@pytest.mark.asyncio
async def test_heartbeat_emits_events_while_waiting():
    """Heartbeat should emit events every interval_seconds while active."""
    heartbeat = LLMHeartbeat(
        phase=PlanningPhase.PLANNING,
        message="Generating plan...",
        interval_seconds=0.1,  # fast for testing
    )
    heartbeat.start()
    await asyncio.sleep(0.35)
    events = heartbeat.drain()
    heartbeat.stop()
    # Should have ~3 events (0.35 / 0.1)
    assert len(events) >= 2
    assert all(isinstance(e, ProgressEvent) for e in events)
    assert all(e.phase == PlanningPhase.PLANNING for e in events)


@pytest.mark.asyncio
async def test_heartbeat_stops_cleanly():
    """After stop(), no more events should be produced."""
    heartbeat = LLMHeartbeat(
        phase=PlanningPhase.PLANNING,
        message="Generating plan...",
        interval_seconds=0.1,
    )
    heartbeat.start()
    await asyncio.sleep(0.15)
    heartbeat.stop()
    count_at_stop = len(heartbeat.drain())
    await asyncio.sleep(0.2)
    assert len(heartbeat.drain()) == 0, "No events should be produced after stop"


@pytest.mark.asyncio
async def test_heartbeat_as_context_manager():
    """Heartbeat should work as async context manager."""
    async with LLMHeartbeat(
        phase=PlanningPhase.VERIFYING,
        message="Verifying plan...",
        interval_seconds=0.1,
    ) as heartbeat:
        await asyncio.sleep(0.25)
    events = heartbeat.drain()
    assert len(events) >= 2
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/flows/test_llm_heartbeat.py -v`
Expected: FAIL (module does not exist)

**Step 3: Implement LLMHeartbeat**

Create `backend/app/domain/services/flows/llm_heartbeat.py`:

```python
"""Periodic heartbeat emitter for long-running LLM calls.

Emits ProgressEvent at a configurable interval so the SSE stream
stays alive and the frontend shows continuous activity.
"""
from __future__ import annotations

import asyncio
from collections import deque

from app.domain.models.event import PlanningPhase, ProgressEvent


class LLMHeartbeat:
    """Produces ProgressEvent heartbeats on a background task."""

    def __init__(
        self,
        phase: PlanningPhase,
        message: str,
        interval_seconds: float = 2.5,
    ) -> None:
        self._phase = phase
        self._message = message
        self._interval = interval_seconds
        self._events: deque[ProgressEvent] = deque()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    # -- public API --

    def start(self) -> None:
        self._stopped = False
        self._task = asyncio.create_task(self._emit_loop())

    def stop(self) -> None:
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()

    def drain(self) -> list[ProgressEvent]:
        """Return and clear all buffered events."""
        events = list(self._events)
        self._events.clear()
        return events

    # -- context manager --

    async def __aenter__(self) -> LLMHeartbeat:
        self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.stop()
        # Allow cancellation to propagate
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # -- internals --

    async def _emit_loop(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._interval)
                if not self._stopped:
                    self._events.append(
                        ProgressEvent(
                            phase=self._phase,
                            message=self._message,
                        )
                    )
        except asyncio.CancelledError:
            return
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/services/flows/test_llm_heartbeat.py -v`
Expected: PASS

**Step 5: Wire heartbeat into plan_act.py planning and verification calls**

In `plan_act.py`, wrap the planner LLM call and verifier LLM call:

```python
from app.domain.services.flows.llm_heartbeat import LLMHeartbeat

# During planning:
async with LLMHeartbeat(
    phase=PlanningPhase.PLANNING,
    message="Generating plan...",
    interval_seconds=2.5,
) as heartbeat:
    plan = await self._planner.create_plan(...)  # existing call
    for event in heartbeat.drain():
        yield event

# During verification:
async with LLMHeartbeat(
    phase=PlanningPhase.VERIFYING,
    message="Checking plan quality...",
    interval_seconds=2.5,
) as heartbeat:
    verdict = await self._verifier.verify_plan(...)  # existing call
    for event in heartbeat.drain():
        yield event
```

**Step 6: Run full flow tests**

Run: `cd backend && pytest tests/domain/services/flows/ -v -k "plan_act" --timeout=30`
Expected: All existing tests PASS + new heartbeat tests PASS

**Step 7: Commit**

```bash
git add backend/app/domain/services/flows/llm_heartbeat.py backend/tests/domain/services/flows/test_llm_heartbeat.py backend/app/domain/services/flows/plan_act.py
git commit -m "feat(agent): add LLM heartbeat emitter for continuous progress during planning/verification"
```

---

### Task 1.3: Update Frontend to Handle New Phases

**Files:**
- Modify: `frontend/src/types/event.ts:219` (PlanningPhase type)
- Modify: `frontend/src/components/PlanningCard.vue:17-23` (phase descriptions)
- Modify: `frontend/src/utils/planningCard.ts` (builder logic)
- Test: `frontend/tests/components/PlanningCard.spec.ts`

**Step 1: Write the failing test**

Add to `frontend/tests/components/PlanningCard.spec.ts`:

```typescript
describe('PlanningCard new phases', () => {
  it('renders verifying phase with correct description', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'verifying' as PlanningPhase,
        message: 'Checking plan quality...',
      },
    })
    expect(wrapper.text()).toContain('Verifying plan')
  })

  it('renders executing_setup phase', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'executing_setup' as PlanningPhase,
        message: 'Preparing to execute...',
      },
    })
    expect(wrapper.text()).toContain('Starting execution')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test:run -- --reporter=verbose tests/components/PlanningCard.spec.ts`
Expected: FAIL (unknown phases)

**Step 3: Extend PlanningPhase type and PlanningCard**

In `frontend/src/types/event.ts`:

```typescript
export type PlanningPhase = 'received' | 'analyzing' | 'planning' | 'verifying' | 'executing_setup' | 'finalizing' | 'waiting'
```

In `frontend/src/components/PlanningCard.vue`:

```typescript
const PHASE_DESCRIPTIONS: Record<PlanningPhase, string> = {
  received: 'Understanding your request',
  analyzing: 'Breaking down your request',
  planning: 'Building an execution plan',
  verifying: 'Verifying plan',          // NEW
  executing_setup: 'Starting execution', // NEW
  finalizing: 'Preparing execution',
  waiting: 'Waiting for your input',
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test:run -- --reporter=verbose tests/components/PlanningCard.spec.ts`
Expected: PASS

**Step 5: Run lint + type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: Clean

**Step 6: Commit**

```bash
git add frontend/src/types/event.ts frontend/src/components/PlanningCard.vue frontend/src/utils/planningCard.ts frontend/tests/components/PlanningCard.spec.ts
git commit -m "feat(frontend): support verifying and executing_setup planning phases"
```

---

## Phase 2: Fast Draft Plan + Early Search (Backend)

**Problem:** Planning takes 18.7s (powerful model) + 12.1s verification before any tool fires. Research plans are formulaic (search -> read -> synthesize) and don't need a powerful model or verification.

**Solution:** Add a `draft_plan` mode that uses `FAST_MODEL`, skips verification for research tasks, and starts execution immediately.

---

### Task 2.1: Add Feature Flag and Draft Plan Config

**Files:**
- Modify: `backend/app/core/config_features.py`
- Test: `backend/tests/core/test_config_features.py` (if exists, else inline verification)

**Step 1: Add feature flag**

In `backend/app/core/config_features.py`, inside `FeatureFlagsSettingsMixin`:

```python
# Fast draft planning — uses FAST_MODEL for research tasks, skips verification
feature_fast_draft_plan: bool = False
# Threshold: skip verification if plan has <= N steps AND task is research
fast_draft_plan_max_steps: int = 5
```

**Step 2: Verify config loads**

Run: `cd backend && python -c "from app.core.config import get_settings; s = get_settings(); print(s.feature_fast_draft_plan, s.fast_draft_plan_max_steps)"`
Expected: `False 5`

**Step 3: Commit**

```bash
git add backend/app/core/config_features.py
git commit -m "feat(config): add feature_fast_draft_plan flag and max_steps threshold"
```

---

### Task 2.2: Add Draft Plan Mode to Planner

**Files:**
- Modify: `backend/app/domain/services/agents/planner.py`
- Test: `backend/tests/domain/services/agents/test_planner_draft_mode.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/agents/test_planner_draft_mode.py`:

```python
"""Tests for draft plan mode — uses fast model and simplified prompts."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_draft_plan_uses_fast_model():
    """When draft=True, planner should request FAST_MODEL from model router."""
    # Setup: mock the LLM service and model router
    # Call: planner.create_plan(message, draft=True)
    # Assert: LLM was called with fast_model, not powerful_model
    pass  # Implement based on planner constructor pattern


@pytest.mark.asyncio
async def test_draft_plan_produces_valid_plan():
    """Draft plan should return a Plan object with steps, even with fast model."""
    pass


@pytest.mark.asyncio
async def test_draft_plan_skips_complexity_analysis():
    """Draft mode should skip expensive complexity analysis heuristics."""
    pass
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/agents/test_planner_draft_mode.py -v`
Expected: FAIL

**Step 3: Add draft parameter to planner.create_plan()**

In `backend/app/domain/services/agents/planner.py`, modify `create_plan()`:

```python
async def create_plan(
    self,
    message: str,
    *,
    draft: bool = False,  # NEW: fast path for research tasks
    # ... existing params ...
) -> Plan:
    if draft:
        # Use fast model override
        original_model = self._llm_service.model_name
        if self._settings.fast_model:
            self._llm_service.model_name = self._settings.fast_model
        try:
            # Skip complexity analysis — assume medium
            plan = await self._generate_plan(message, complexity="medium")
        finally:
            self._llm_service.model_name = original_model
        return plan
    # ... existing full planning path ...
```

The exact implementation depends on how the planner currently delegates to the LLM. Key principle: `draft=True` means fast model, skip heuristics, no complexity analysis.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/services/agents/test_planner_draft_mode.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/planner.py backend/tests/domain/services/agents/test_planner_draft_mode.py
git commit -m "feat(planner): add draft=True mode for fast research planning"
```

---

### Task 2.3: Wire Fast Draft Plan into PlanActFlow

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Test: `backend/tests/domain/services/flows/test_plan_act_fast_draft.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/flows/test_plan_act_fast_draft.py`:

```python
"""Tests that PlanActFlow uses draft planning for research tasks when feature flag is on."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_research_mode_uses_draft_plan_when_flag_enabled():
    """When feature_fast_draft_plan=True and research_mode is set, planner.create_plan(draft=True)."""
    pass  # Assert planner called with draft=True


@pytest.mark.asyncio
async def test_research_mode_skips_verification_with_draft_plan():
    """Draft plan path should skip verification entirely (no VERIFYING state transition)."""
    pass  # Collect events, assert no VerificationEvent


@pytest.mark.asyncio
async def test_non_research_uses_full_plan():
    """When NOT in research mode, full planning + verification still applies."""
    pass  # Assert planner called with draft=False


@pytest.mark.asyncio
async def test_draft_plan_respects_max_steps_threshold():
    """If draft plan produces more than fast_draft_plan_max_steps steps, fall back to verification."""
    pass
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/flows/test_plan_act_fast_draft.py -v`
Expected: FAIL

**Step 3: Modify PlanActFlow planning section**

In `plan_act.py`, locate the planning state handler. Add the fast path:

```python
# In the PLANNING state handler:
use_draft = (
    self._feature_flags.get("feature_fast_draft_plan", False)
    and self._research_mode is not None  # research task
)

if use_draft:
    # Fast path: draft plan with fast model, no verification
    async with LLMHeartbeat(phase=PlanningPhase.PLANNING, message="Drafting research plan...") as hb:
        plan = await self._planner.create_plan(message, draft=True)
        for event in hb.drain():
            yield event
    yield PlanEvent(status="created", plan=plan)

    # Skip verification if plan is within threshold
    if len(plan.steps) <= self._settings.fast_draft_plan_max_steps:
        # Transition directly to EXECUTING (skip VERIFYING)
        self._state = AgentStatus.EXECUTING
    else:
        # Plan too complex — fall back to full verification
        self._state = AgentStatus.VERIFYING
else:
    # Existing full planning path (unchanged)
    ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/services/flows/test_plan_act_fast_draft.py -v`
Expected: PASS

**Step 5: Run all flow tests**

Run: `cd backend && pytest tests/domain/services/flows/ -v --timeout=30`
Expected: All PASS (existing + new)

**Step 6: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_plan_act_fast_draft.py
git commit -m "feat(flow): fast draft plan path for research tasks — skips verification, uses fast model"
```

---

## Phase 3: Phase Timeline UI (Frontend)

**Problem:** PlanningCard disappears after planning. During execution, there's no persistent indicator of which phase the agent is in. User loses context during long runs.

**Solution:** Replace PlanningCard with a persistent `PhaseStrip` component that shows the full lifecycle above the conversation.

---

### Task 3.1: Create PhaseStrip Component

**Files:**
- Create: `frontend/src/components/PhaseStrip.vue`
- Test: `frontend/tests/components/PhaseStrip.spec.ts`

**Step 1: Write the failing test**

Create `frontend/tests/components/PhaseStrip.spec.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PhaseStrip from '@/components/PhaseStrip.vue'

describe('PhaseStrip', () => {
  const defaultProps = {
    currentPhase: 'planning' as const,
    startTime: Date.now() - 5000,
    stepProgress: null as { current: number; total: number } | null,
  }

  it('renders all phase labels', () => {
    const wrapper = mount(PhaseStrip, { props: defaultProps })
    expect(wrapper.text()).toContain('Planning')
    expect(wrapper.text()).toContain('Searching')
    expect(wrapper.text()).toContain('Writing')
  })

  it('marks current phase as active', () => {
    const wrapper = mount(PhaseStrip, { props: defaultProps })
    const active = wrapper.find('[data-phase="planning"]')
    expect(active.classes()).toContain('phase--active')
  })

  it('marks completed phases', () => {
    const wrapper = mount(PhaseStrip, {
      props: { ...defaultProps, currentPhase: 'searching' },
    })
    const planning = wrapper.find('[data-phase="planning"]')
    expect(planning.classes()).toContain('phase--completed')
  })

  it('shows elapsed time', () => {
    const wrapper = mount(PhaseStrip, { props: defaultProps })
    expect(wrapper.text()).toMatch(/\d+s/)
  })

  it('shows determinate step progress when available', () => {
    const wrapper = mount(PhaseStrip, {
      props: {
        ...defaultProps,
        currentPhase: 'searching',
        stepProgress: { current: 2, total: 4 },
      },
    })
    expect(wrapper.text()).toContain('2 / 4')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test:run -- --reporter=verbose tests/components/PhaseStrip.spec.ts`
Expected: FAIL (component doesn't exist)

**Step 3: Implement PhaseStrip.vue**

Create `frontend/src/components/PhaseStrip.vue`:

```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

/**
 * Lifecycle phases displayed left-to-right. Maps to backend agent states.
 * 'queued' and 'cancelled' are terminal/pre states, not shown in strip.
 */
const PHASES = ['planning', 'verifying', 'searching', 'writing', 'done'] as const
type Phase = (typeof PHASES)[number]

const PHASE_LABELS: Record<Phase, string> = {
  planning: 'Planning',
  verifying: 'Verifying',
  searching: 'Searching',
  writing: 'Writing',
  done: 'Done',
}

interface Props {
  currentPhase: Phase
  startTime: number // Date.now() when session started
  stepProgress: { current: number; total: number } | null
}

const props = defineProps<Props>()

const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => {
    elapsed.value = Math.floor((Date.now() - props.startTime) / 1000)
  }, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const currentIndex = computed(() => PHASES.indexOf(props.currentPhase))

function phaseClass(phase: Phase) {
  const idx = PHASES.indexOf(phase)
  if (idx < currentIndex.value) return 'phase--completed'
  if (idx === currentIndex.value) return 'phase--active'
  return 'phase--pending'
}
</script>

<template>
  <div class="phase-strip" role="progressbar" :aria-valuenow="currentIndex" :aria-valuemax="PHASES.length - 1">
    <div
      v-for="phase in PHASES"
      :key="phase"
      :data-phase="phase"
      class="phase-step"
      :class="phaseClass(phase)"
    >
      <span class="phase-dot" />
      <span class="phase-label">{{ PHASE_LABELS[phase] }}</span>
    </div>

    <div class="phase-meta">
      <span v-if="stepProgress" class="step-counter">
        {{ stepProgress.current }} / {{ stepProgress.total }}
      </span>
      <span class="elapsed-time">{{ elapsed }}s</span>
    </div>
  </div>
</template>

<style scoped>
.phase-strip {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--surface-secondary, #fafafa);
  user-select: none;
}

.phase-step {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  opacity: 0.35;
  transition: opacity 0.3s ease;
}

.phase-step + .phase-step::before {
  content: '';
  display: inline-block;
  width: 1rem;
  height: 1px;
  background: currentColor;
  opacity: 0.3;
  margin-right: 0.25rem;
}

.phase--completed {
  opacity: 0.6;
}

.phase--active {
  opacity: 1;
  font-weight: 600;
}

.phase-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.phase--active .phase-dot {
  animation: pulse 1.5s ease-in-out infinite;
}

.phase--completed .phase-dot {
  background: var(--color-success, #22c55e);
}

.phase-meta {
  margin-left: auto;
  display: flex;
  gap: 0.5rem;
  align-items: center;
  opacity: 0.6;
}

.step-counter {
  font-variant-numeric: tabular-nums;
}

.elapsed-time {
  font-variant-numeric: tabular-nums;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test:run -- --reporter=verbose tests/components/PhaseStrip.spec.ts`
Expected: PASS

**Step 5: Lint + type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: Clean

**Step 6: Commit**

```bash
git add frontend/src/components/PhaseStrip.vue frontend/tests/components/PhaseStrip.spec.ts
git commit -m "feat(frontend): add PhaseStrip component for persistent lifecycle timeline"
```

---

### Task 3.2: Wire PhaseStrip into ChatPage

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- No new test file — integration behavior covered by existing ChatPage tests

**Step 1: Add PhaseStrip state derivation**

In `ChatPage.vue`, add a computed property that maps backend events to PhaseStrip phases:

```typescript
import PhaseStrip from '@/components/PhaseStrip.vue'

// Map backend agent states to PhaseStrip phases
const phaseStripPhase = computed(() => {
  // Derive from latest ProgressEvent phase and agent status
  const progress = planningProgress.value
  if (!progress) return null

  const mapping: Record<string, string> = {
    received: 'planning',
    analyzing: 'planning',
    planning: 'planning',
    verifying: 'verifying',
    executing_setup: 'searching',
    finalizing: 'writing',
    waiting: 'searching',
  }
  return mapping[progress.phase] ?? 'planning'
})

// Also derive from StepEvent / PlanEvent when planning is done
// PhaseStrip stays visible when any session is actively running
const showPhaseStrip = computed(() => {
  return isAgentRunning.value && phaseStripPhase.value !== null
})

// Step progress from plan data
const phaseStripStepProgress = computed(() => {
  if (!currentPlan.value) return null
  const completed = currentPlan.value.steps.filter(s => s.status === 'completed').length
  return { current: completed, total: currentPlan.value.steps.length }
})
```

**Step 2: Add PhaseStrip to template**

Place it above the message list, below the header:

```vue
<PhaseStrip
  v-if="showPhaseStrip"
  :current-phase="phaseStripPhase"
  :start-time="sessionStartTime"
  :step-progress="phaseStripStepProgress"
/>
```

**Step 3: Update event handler to keep phase state fresh**

In the `handleEvent` function, ensure phase transitions update during execution (not just planning):
- When `StepEvent(status=STARTED)` arrives → set phase to `'searching'`
- When report/summary generation starts → set phase to `'writing'`
- When `DoneEvent` arrives → set phase to `'done'`

**Step 4: Run lint + type-check + existing tests**

Run: `cd frontend && bun run lint && bun run type-check && bun run test:run`
Expected: Clean + all tests pass

**Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat(frontend): wire PhaseStrip into ChatPage with event-driven phase mapping"
```

---

### Task 3.3: Determinate Progress During Execution

**Files:**
- Modify: `frontend/src/components/PhaseStrip.vue` (add progress bar segment)
- Modify: `frontend/src/pages/ChatPage.vue` (derive progress from step events)

**Step 1: Add progress bar to PhaseStrip**

Add a thin progress bar below the phase dots that fills proportionally:

```vue
<!-- Inside PhaseStrip template, after phase-meta -->
<div v-if="stepProgress" class="progress-bar">
  <div
    class="progress-fill"
    :style="{ width: `${(stepProgress.current / stepProgress.total) * 100}%` }"
  />
</div>
```

```css
.progress-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--border-color, #e5e7eb);
}

.progress-fill {
  height: 100%;
  background: var(--color-primary, #3b82f6);
  transition: width 0.5s ease;
}
```

**Step 2: Run existing PhaseStrip tests**

Run: `cd frontend && bun run test:run -- --reporter=verbose tests/components/PhaseStrip.spec.ts`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/PhaseStrip.vue frontend/src/pages/ChatPage.vue
git commit -m "feat(frontend): add determinate progress bar to PhaseStrip based on step completion"
```

---

## Phase 4: Partial Outputs (Backend + Frontend)

**Problem:** Summarization is all-or-nothing. User waits for all steps to complete before seeing any results. A 4-step research plan shows nothing until all 4 searches are done.

**Solution:** Emit a `PartialResultEvent` after each step completes, containing a one-line headline extracted from the tool result.

---

### Task 4.1: Define PartialResultEvent

**Files:**
- Modify: `backend/app/domain/models/event.py`
- Test: `backend/tests/domain/models/test_events.py` (add event serialization test)

**Step 1: Add event model**

In `backend/app/domain/models/event.py`:

```python
class PartialResultEvent(BaseEvent):
    """Emitted after each step completes with a headline summary of results found so far."""
    type: Literal["partial_result"] = "partial_result"
    step_index: int
    step_title: str
    headline: str  # One-line summary, e.g. "Found 12 results about renewable energy trends"
    sources_count: int = 0
```

**Step 2: Write test**

```python
def test_partial_result_event_serialization():
    event = PartialResultEvent(
        step_index=0,
        step_title="Search for renewable energy",
        headline="Found 12 results about renewable energy trends",
        sources_count=12,
    )
    data = event.model_dump()
    assert data["type"] == "partial_result"
    assert data["step_index"] == 0
    assert data["sources_count"] == 12
```

**Step 3: Run test, implement, verify**

Run: `cd backend && pytest tests/domain/models/test_events.py -v -k "partial_result"`
Expected: PASS after implementation

**Step 4: Commit**

```bash
git add backend/app/domain/models/event.py backend/tests/domain/models/test_events.py
git commit -m "feat(events): add PartialResultEvent for step-level result headlines"
```

---

### Task 4.2: Emit PartialResultEvent After Step Completion

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py` (after step completion)
- Create: `backend/app/domain/services/flows/headline_extractor.py`
- Test: `backend/tests/domain/services/flows/test_headline_extractor.py`

**Step 1: Write headline extractor test**

Create `backend/tests/domain/services/flows/test_headline_extractor.py`:

```python
"""Tests for extracting one-line headlines from tool results."""
import pytest
from app.domain.services.flows.headline_extractor import extract_headline


def test_search_result_headline():
    tool_result = "Found 12 results for 'renewable energy trends':\n1. Solar power growth in 2026...\n2. Wind energy..."
    headline = extract_headline(tool_result, tool_name="web_search")
    assert "12" in headline or "renewable" in headline.lower()
    assert len(headline) <= 120


def test_browser_result_headline():
    tool_result = "Navigated to https://example.com/article\nPage title: Understanding AI Agents"
    headline = extract_headline(tool_result, tool_name="browser_navigate")
    assert "AI Agents" in headline or "example.com" in headline


def test_empty_result_headline():
    headline = extract_headline("", tool_name="web_search")
    assert headline  # Should return a fallback, not empty


def test_long_result_truncated():
    tool_result = "A" * 500
    headline = extract_headline(tool_result, tool_name="terminal")
    assert len(headline) <= 120
```

**Step 2: Implement headline extractor**

Create `backend/app/domain/services/flows/headline_extractor.py`:

```python
"""Extract a one-line headline from a tool result for partial output display."""
from __future__ import annotations

import re

_MAX_HEADLINE_LEN = 120


def extract_headline(tool_result: str, tool_name: str = "") -> str:
    """Return a <= 120 char headline summarising the tool result."""
    if not tool_result.strip():
        return f"{tool_name or 'Tool'} completed (no output)"

    # Search results — extract count and query
    count_match = re.search(r"Found (\d+) results?\b", tool_result)
    if count_match:
        first_line = tool_result.split("\n")[0].strip()
        return first_line[:_MAX_HEADLINE_LEN]

    # Browser — extract page title
    title_match = re.search(r"(?:Page title|Title):\s*(.+)", tool_result)
    if title_match:
        return f"Visited: {title_match.group(1).strip()}"[:_MAX_HEADLINE_LEN]

    # Default — first non-empty line, truncated
    for line in tool_result.split("\n"):
        line = line.strip()
        if line:
            if len(line) > _MAX_HEADLINE_LEN:
                return line[: _MAX_HEADLINE_LEN - 3] + "..."
            return line

    return f"{tool_name or 'Tool'} completed"
```

**Step 3: Wire into plan_act.py**

In the step completion handler (after `StepEvent(status=COMPLETED)` is yielded):

```python
from app.domain.services.flows.headline_extractor import extract_headline
from app.domain.models.event import PartialResultEvent

# After step completes successfully:
if step_result and step_result.tool_results:
    last_tool = step_result.tool_results[-1]
    headline = extract_headline(
        last_tool.result_text or "",
        tool_name=last_tool.tool_name,
    )
    sources_count = sum(
        1 for tr in step_result.tool_results
        if tr.tool_name in ("web_search", "scrape_structured")
    )
    yield PartialResultEvent(
        step_index=step.index,
        step_title=step.title,
        headline=headline,
        sources_count=sources_count,
    )
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/flows/test_headline_extractor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/headline_extractor.py backend/tests/domain/services/flows/test_headline_extractor.py backend/app/domain/services/flows/plan_act.py
git commit -m "feat(agent): emit PartialResultEvent with step headlines after each step completes"
```

---

### Task 4.3: Render Partial Results in Frontend

**Files:**
- Modify: `frontend/src/types/event.ts` (add PartialResultEventData)
- Create: `frontend/src/components/PartialResults.vue`
- Modify: `frontend/src/pages/ChatPage.vue` (handle event, render component)
- Test: `frontend/tests/components/PartialResults.spec.ts`

**Step 1: Add TypeScript type**

In `frontend/src/types/event.ts`:

```typescript
export interface PartialResultEventData extends BaseEventData {
  type: 'partial_result'
  step_index: number
  step_title: string
  headline: string
  sources_count: number
}

// Add to AgentSSEEvent union type
```

**Step 2: Create PartialResults component**

Create `frontend/src/components/PartialResults.vue`:

```vue
<script setup lang="ts">
interface PartialResult {
  stepIndex: number
  stepTitle: string
  headline: string
  sourcesCount: number
}

defineProps<{
  results: PartialResult[]
}>()
</script>

<template>
  <div v-if="results.length" class="partial-results">
    <div class="partial-results-header">Findings so far</div>
    <ul class="partial-results-list">
      <li v-for="r in results" :key="r.stepIndex" class="partial-result-item">
        <span class="result-headline">{{ r.headline }}</span>
        <span v-if="r.sourcesCount" class="result-sources">{{ r.sourcesCount }} sources</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.partial-results {
  padding: 0.5rem 0.75rem;
  margin: 0.5rem 0;
  border-left: 2px solid var(--color-primary, #3b82f6);
  background: var(--surface-secondary, #f8fafc);
  border-radius: 0 0.375rem 0.375rem 0;
  font-size: 0.8125rem;
}

.partial-results-header {
  font-weight: 600;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.6;
  margin-bottom: 0.375rem;
}

.partial-results-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.partial-result-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}

.result-headline {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-sources {
  flex-shrink: 0;
  opacity: 0.5;
  font-size: 0.75rem;
}
</style>
```

**Step 3: Wire into ChatPage**

In `ChatPage.vue`:
- Add `partialResults` reactive array
- In `handleEvent`, on `partial_result` event type, push to array
- Clear on `DoneEvent` or `ReportEvent`
- Render `<PartialResults>` below the PhaseStrip (or inline in the message thread)

**Step 4: Write test, run, verify**

Run: `cd frontend && bun run test:run -- --reporter=verbose tests/components/PartialResults.spec.ts`
Expected: PASS

**Step 5: Lint + type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: Clean

**Step 6: Commit**

```bash
git add frontend/src/types/event.ts frontend/src/components/PartialResults.vue frontend/tests/components/PartialResults.spec.ts frontend/src/pages/ChatPage.vue
git commit -m "feat(frontend): render partial results as provisional findings during execution"
```

---

## Phase 5: Latency Budgets (Backend)

**Problem:** Verification can take 12s+ and sometimes triggers re-planning loops. There's no timeout or degradation path.

**Solution:** Add a configurable verification timeout. If exceeded, auto-pass and continue to execution.

---

### Task 5.1: Add Verification Timeout

**Files:**
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Test: `backend/tests/domain/services/flows/test_plan_act_verification_timeout.py`

**Step 1: Add config**

In `config_features.py`:

```python
# Verification timeout — auto-pass if verification exceeds this (seconds)
verification_timeout_seconds: float = 8.0
# Maximum verification loops before auto-pass
max_verification_loops: int = 1  # Currently 2 in plan_act.py — reduce to 1
```

**Step 2: Write failing test**

```python
@pytest.mark.asyncio
async def test_verification_auto_passes_on_timeout():
    """If verification takes longer than verification_timeout_seconds, skip it and proceed."""
    # Mock verifier to sleep for 10s
    # Set timeout to 2s
    # Assert: execution starts without waiting for verifier
    # Assert: VerificationEvent with status=TIMEOUT_SKIP emitted
    pass
```

**Step 3: Implement timeout in plan_act.py**

Wrap the verification call with `asyncio.wait_for`:

```python
import asyncio

try:
    verdict = await asyncio.wait_for(
        self._verifier.verify_plan(plan),
        timeout=self._settings.verification_timeout_seconds,
    )
except asyncio.TimeoutError:
    logger.warning("Verification timed out after %.1fs — auto-passing", self._settings.verification_timeout_seconds)
    yield VerificationEvent(status="timeout_skip", message="Verification skipped (timeout)")
    self._state = AgentStatus.EXECUTING
    # Continue without verification
```

**Step 4: Run tests, verify, commit**

```bash
git add backend/app/core/config_features.py backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_plan_act_verification_timeout.py
git commit -m "feat(agent): add verification timeout with graceful auto-pass degradation"
```

---

## Phase 6: Cancel & Retry (Backend + Frontend)

**Problem:** No way to stop a running agent. User must wait for completion or reload the page.

**Solution:** Add a cancellation flag, API endpoint, and frontend cancel button.

---

### Task 6.1: Add Cancellation Signal (Backend)

**Files:**
- Create: `backend/app/domain/services/flows/cancellation.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Test: `backend/tests/domain/services/flows/test_cancellation.py`

**Step 1: Write test**

```python
@pytest.mark.asyncio
async def test_cancellation_signal_stops_execution():
    """Setting cancellation flag should stop the flow after current step."""
    cancel = CancellationSignal()
    assert not cancel.is_cancelled
    cancel.cancel()
    assert cancel.is_cancelled


@pytest.mark.asyncio
async def test_flow_checks_cancellation_between_steps():
    """PlanActFlow should check cancellation signal between each step."""
    pass
```

**Step 2: Implement CancellationSignal**

Create `backend/app/domain/services/flows/cancellation.py`:

```python
"""Cooperative cancellation signal for agent flows."""
from __future__ import annotations

import asyncio


class CancellationSignal:
    """Thread-safe cancellation flag checked between flow steps."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    async def wait(self, timeout: float | None = None) -> bool:
        """Wait for cancellation. Returns True if cancelled, False on timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
```

**Step 3: Wire into PlanActFlow**

In `plan_act.py`, accept `CancellationSignal` in constructor. Check between steps:

```python
# Between each step in execution:
if self._cancellation and self._cancellation.is_cancelled:
    logger.info("Cancellation requested — stopping after step %d", step.index)
    yield StepEvent(status="cancelled", step=step)
    self._state = AgentStatus.SUMMARIZING  # Summarize what we have
    break
```

**Step 4: Run tests, commit**

```bash
git add backend/app/domain/services/flows/cancellation.py backend/tests/domain/services/flows/test_cancellation.py backend/app/domain/services/flows/plan_act.py
git commit -m "feat(agent): add cooperative CancellationSignal for stopping running flows"
```

---

### Task 6.2: Add Cancel API Endpoint

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py`
- Test: `backend/tests/interfaces/api/test_session_cancel.py`

**Step 1: Write test**

```python
@pytest.mark.asyncio
async def test_cancel_session_returns_202():
    response = await client.post(f"/api/sessions/{session_id}/cancel")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "cancelling"


@pytest.mark.asyncio
async def test_cancel_nonexistent_session_returns_404():
    response = await client.post("/api/sessions/nonexistent/cancel")
    assert response.status_code == 404
```

**Step 2: Implement endpoint**

In `session_routes.py`:

```python
@router.post("/sessions/{session_id}/cancel", status_code=202)
async def cancel_session(session_id: str):
    """Request cancellation of a running session."""
    signal = active_cancellation_signals.get(session_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Session not found or not running")
    signal.cancel()
    return {"status": "cancelling", "session_id": session_id}
```

The `active_cancellation_signals` dict is populated when a session starts and cleaned up on completion.

**Step 3: Run tests, commit**

```bash
git add backend/app/interfaces/api/session_routes.py backend/tests/interfaces/api/test_session_cancel.py
git commit -m "feat(api): add POST /sessions/{id}/cancel endpoint for agent cancellation"
```

---

### Task 6.3: Add Cancel Button to Frontend

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue` (add cancel button near PhaseStrip)
- Modify: `frontend/src/api/` (add cancelSession API call)

**Step 1: Add API function**

In the appropriate API client file:

```typescript
export async function cancelSession(sessionId: string): Promise<void> {
  await apiClient.post(`/sessions/${sessionId}/cancel`)
}
```

**Step 2: Add cancel button to ChatPage**

Near the PhaseStrip or in the input area:

```vue
<button
  v-if="isAgentRunning"
  class="cancel-button"
  @click="handleCancel"
>
  Cancel
</button>
```

```typescript
async function handleCancel() {
  if (!currentSessionId.value) return
  try {
    await cancelSession(currentSessionId.value)
  } catch {
    // Session may have already completed
  }
}
```

**Step 3: Lint + type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: Clean

**Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.vue frontend/src/api/
git commit -m "feat(frontend): add cancel button for running agent sessions"
```

---

## Summary: Implementation Order

| Phase | Tasks | Impact | Effort | Dependencies |
|-------|-------|--------|--------|--------------|
| **1** | 1.1, 1.2, 1.3 | High (kills dark periods) | Small | None |
| **2** | 2.1, 2.2, 2.3 | Highest (62s -> ~12s for research) | Medium | None |
| **3** | 3.1, 3.2, 3.3 | High (persistent visibility) | Medium | Phase 1 (new phases) |
| **4** | 4.1, 4.2, 4.3 | High (early useful output) | Medium | None |
| **5** | 5.1 | Medium (verification timeout) | Small | None |
| **6** | 6.1, 6.2, 6.3 | Medium (user control) | Medium | None |

**Phases 1, 2, 4, 5 can be implemented in parallel** (no dependencies between them).
Phase 3 depends on Phase 1 (needs the new PlanningPhase values).
Phase 6 is independent.

**Feature flags** (all default `False` for safe rollout):
- `feature_fast_draft_plan` — Phase 2
- `verification_timeout_seconds` — Phase 5
- No flag needed for Phases 1, 3, 4, 6 (additive, non-breaking)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Fast model produces bad research plans | Gate behind feature flag; only for research_mode tasks; fall back to full plan if steps > threshold |
| Heartbeat events flood SSE stream | 2.5s interval = ~4-7 extra events per LLM call; trivial bandwidth |
| Cancel during LLM call leaves orphaned request | LLM call completes server-side but result is discarded; no resource leak |
| Partial results mislead user (incomplete data) | Label as "Findings so far" with clear "provisional" styling; replaced by final report |
| PhaseStrip stale after disconnect | Reconnect via existing cursor-based SSE resumption; PhaseStrip derives from latest event |
