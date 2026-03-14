# Live Plan Streaming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stream the agent's plan as formatted markdown into the live view Monaco editor during planning, giving users immediate visual feedback from first interaction.

**Architecture:** Emit `StreamEvent(phase="planning")` from the planner alongside existing `ProgressEvent`s — progress phases stream as markdown lines during the LLM wait, then the full formatted plan streams chunk-by-chunk after `ask_structured()` returns. Frontend handles `phase === 'planning'` identically to the existing `phase === 'summarizing'` report flow, rendering into `EditorContentView` via a plan presentation overlay in `ToolPanelContent`.

**Tech Stack:** Python (backend planner, asyncio), Vue 3 Composition API (frontend), SVG animation (pen & paper icon), Monaco Editor (plan display)

---

### Task 1: Add `"planning"` StreamEvent Phase (Backend)

**Files:**
- Modify: `backend/app/domain/models/event.py:685` (StreamEvent.phase docstring)

**Step 1: Update StreamEvent phase docstring**

The `phase` field on `StreamEvent` (line 685) is already a plain `str`, so `"planning"` is valid without code changes. Update the docstring to document the new phase:

```python
# event.py line 685 — change:
phase: str = "thinking"  # "thinking" for planning, "summarizing" for report generation

# to:
phase: str = "thinking"  # "thinking" for reasoning, "planning" for plan streaming, "summarizing" for report generation
```

**Step 2: Verify no validation blocks `"planning"`**

Run: `cd backend && grep -rn 'phase.*==.*thinking\|phase.*in.*\[' app/domain/models/event.py app/infrastructure/ app/domain/services/agents/execution.py | head -20`

Expected: No enum-based validation on `StreamEvent.phase` — it's a free `str`.

**Step 3: Commit**

```bash
git add backend/app/domain/models/event.py
git commit -m "docs(event): document 'planning' as valid StreamEvent phase"
```

---

### Task 2: Add `_format_plan_as_markdown()` Helper (Backend)

**Files:**
- Modify: `backend/app/domain/services/agents/planner.py`
- Test: `backend/tests/domain/services/test_planner_plan_markdown.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/test_planner_plan_markdown.py`:

```python
"""Tests for plan-to-markdown formatting."""
import pytest

from app.domain.models.plan import Plan, Step, ExecutionStatus


def _make_plan(steps: int = 3) -> Plan:
    return Plan(
        goal="Research and compare AI agent frameworks",
        title="AI Agent Frameworks Comparison 2026",
        language="en",
        message="I'll research these frameworks.",
        steps=[
            Step(
                id=f"step_{i}",
                description=f"Step {i + 1} description here",
                status=ExecutionStatus.PENDING,
                step_type="research" if i == 0 else "analysis",
                action_verb=["Research", "Analyze", "Verify"][i] if i < 3 else "Execute",
                target_object=f"target {i + 1}",
                tool_hint="Web Search, Browser" if i == 0 else "File Editor",
                expected_output=f"Expected output {i + 1}",
            )
            for i in range(steps)
        ],
    )


class TestFormatPlanAsMarkdown:
    def test_contains_title_as_h1(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = _make_plan()
        md = _format_plan_as_markdown(plan, complexity="complex", mode="research")
        assert "# AI Agent Frameworks Comparison 2026" in md

    def test_contains_goal_blockquote(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = _make_plan()
        md = _format_plan_as_markdown(plan, complexity="complex", mode="research")
        assert "> **Goal:**" in md
        assert "Research and compare AI agent frameworks" in md

    def test_contains_metadata_table(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = _make_plan()
        md = _format_plan_as_markdown(plan, complexity="complex", mode="research")
        assert "| **Complexity**" in md
        assert "| **Steps**" in md
        assert "| 3 " in md

    def test_contains_step_headers(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = _make_plan()
        md = _format_plan_as_markdown(plan, complexity="complex", mode="research")
        assert "## Step 1" in md
        assert "## Step 2" in md
        assert "## Step 3" in md

    def test_contains_tool_hints(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = _make_plan()
        md = _format_plan_as_markdown(plan, complexity="complex", mode="research")
        assert "Web Search, Browser" in md

    def test_contains_action_verb_labels(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = _make_plan()
        md = _format_plan_as_markdown(plan, complexity="complex", mode="research")
        assert "Research" in md
        assert "Analyze" in md

    def test_single_step_plan(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = _make_plan(steps=1)
        md = _format_plan_as_markdown(plan, complexity="simple", mode="chat")
        assert "## Step 1" in md
        assert "## Step 2" not in md

    def test_missing_optional_fields(self):
        from app.domain.services.agents.planner import _format_plan_as_markdown

        plan = Plan(
            goal="Do something",
            title="Simple Task",
            language="en",
            steps=[
                Step(
                    id="s1",
                    description="Just do it",
                    status=ExecutionStatus.PENDING,
                )
            ],
        )
        md = _format_plan_as_markdown(plan, complexity=None, mode=None)
        assert "# Simple Task" in md
        assert "## Step 1" in md
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_planner_plan_markdown.py -v`
Expected: FAIL — `ImportError: cannot import name '_format_plan_as_markdown'`

**Step 3: Write the implementation**

Add to `backend/app/domain/services/agents/planner.py`, before the `PlannerAgent` class definition (around line 170, near other module-level helpers like `_step_from_description`):

```python
def _format_plan_as_markdown(
    plan: Plan,
    complexity: str | None = None,
    mode: str | None = None,
) -> str:
    """Format a Plan object as a well-structured markdown document for live view display."""
    lines: list[str] = []

    # Title
    lines.append(f"# {plan.title or 'Execution Plan'}")
    lines.append("")

    # Goal blockquote
    if plan.goal:
        lines.append(f"> **Goal:** {plan.goal}")
        lines.append("")

    # Metadata table
    meta_rows: list[tuple[str, str]] = []
    if complexity:
        meta_rows.append(("**Complexity**", complexity.replace("_", " ").title()))
    meta_rows.append(("**Steps**", str(len(plan.steps))))
    if mode:
        meta_rows.append(("**Mode**", mode.replace("_", " ").title()))

    if meta_rows:
        lines.append("| Info | Detail |")
        lines.append("|------|--------|")
        for label, value in meta_rows:
            lines.append(f"| {label} | {value} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Steps
    for i, step in enumerate(plan.steps):
        verb = (step.action_verb or "").strip()
        label = f" \u00b7 {verb}" if verb else ""
        lines.append(f"## Step {i + 1}{label}")
        lines.append("")
        lines.append(f"**{step.description}**")
        lines.append("")

        if step.expected_output:
            lines.append(step.expected_output)
            lines.append("")

        if step.tool_hint:
            lines.append(f"> *Tools: {step.tool_hint}*")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Footer
    lines.append("*Plan created by Pythinker*")
    lines.append("")

    return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_planner_plan_markdown.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/planner.py backend/tests/domain/services/test_planner_plan_markdown.py
git commit -m "feat(planner): add _format_plan_as_markdown() helper for live view plan display"
```

---

### Task 3: Emit `StreamEvent(phase="planning")` in `create_plan()` (Backend)

**Files:**
- Modify: `backend/app/domain/services/agents/planner.py:392-616`
- Test: `backend/tests/domain/services/test_planner_stream_events.py`

**Step 1: Write the failing test**

Create `backend/tests/domain/services/test_planner_stream_events.py`:

```python
"""Tests for plan streaming events emitted during create_plan()."""
import pytest

from app.domain.models.event import ProgressEvent, StreamEvent, PlanEvent


class TestStreamPlanAsMarkdown:
    def test_chunks_content_correctly(self):
        from app.domain.services.agents.planner import _stream_plan_chunks

        text = "# Title\n\nSome content here that is long enough to be split into chunks."
        chunks = list(_stream_plan_chunks(text, chunk_size=20))
        assert len(chunks) > 1
        assert "".join(chunks) == text

    def test_single_chunk_for_short_text(self):
        from app.domain.services.agents.planner import _stream_plan_chunks

        text = "Short"
        chunks = list(_stream_plan_chunks(text, chunk_size=100))
        assert chunks == ["Short"]

    def test_empty_text(self):
        from app.domain.services.agents.planner import _stream_plan_chunks

        chunks = list(_stream_plan_chunks("", chunk_size=100))
        assert chunks == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_planner_stream_events.py -v`
Expected: FAIL — `ImportError: cannot import name '_stream_plan_chunks'`

**Step 3: Add `_stream_plan_chunks()` helper and emit StreamEvents in `create_plan()`**

Add to `planner.py` near `_format_plan_as_markdown`:

```python
def _stream_plan_chunks(text: str, chunk_size: int = 100) -> list[str]:
    """Split text into chunks for synthetic streaming, splitting at newlines when possible."""
    if not text:
        return []
    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + chunk_size, len(text))
        # Try to split at a newline within the chunk
        nl = text.rfind("\n", pos, end)
        if nl > pos and end < len(text):
            end = nl + 1  # include the newline
        chunks.append(text[pos:end])
        pos = end
    return chunks
```

Then modify `create_plan()` to emit `StreamEvent(phase="planning")` at three points:

**Point A — After the first `ProgressEvent(phase=RECEIVED)` at line 393:**

```python
        # Instant acknowledgment - user sees feedback immediately
        yield ProgressEvent(
            phase=PlanningPhase.RECEIVED, message="Message received, starting to process...", progress_percent=10
        )
        # Stream initial planning header to live view
        yield StreamEvent(
            phase="planning",
            content="# Planning...\n\n> Analyzing your request...\n",
        )
```

**Point B — After `ProgressEvent(phase=PLANNING)` at line 557:**

```python
        yield ProgressEvent(
            phase=PlanningPhase.PLANNING,
            message="Creating execution plan...",
            progress_percent=40,
            complexity_category=task_complexity,
        )
        # Update live view with planning progress
        yield StreamEvent(
            phase="planning",
            content="> Creating execution plan...\n",
        )
```

**Point C — After plan is created and before PlanEvent is yielded (after line 615, before line 616):**

```python
                # Stream the formatted plan to live view
                import asyncio

                plan_md = _format_plan_as_markdown(
                    plan,
                    complexity=task_complexity,
                    mode=getattr(self, '_research_mode', None),
                )
                # Replace progress header with full plan via is_replace flag
                yield StreamEvent(phase="planning", content=plan_md, lane="replace")

                yield StreamEvent(phase="planning", is_final=True)
                yield PlanEvent(status=PlanStatus.CREATED, plan=plan)
                return
```

Note: We use `lane="replace"` as a signal to the frontend to replace (not append) the plan text. This replaces the "# Planning..." header with the full formatted plan.

Also add the same streaming for the fallback plan path (after line 630):

```python
        fallback_md = _format_plan_as_markdown(fallback_plan, complexity=task_complexity)
        yield StreamEvent(phase="planning", content=fallback_md, lane="replace")
        yield StreamEvent(phase="planning", is_final=True)
        yield PlanEvent(status=PlanStatus.CREATED, plan=fallback_plan)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_planner_stream_events.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/planner.py backend/tests/domain/services/test_planner_stream_events.py
git commit -m "feat(planner): emit StreamEvent(phase='planning') during plan creation for live view"
```

---

### Task 4: Add `'planning'` Phase to Frontend Streaming Constants

**Files:**
- Modify: `frontend/src/constants/streamingPresentation.ts`

**Step 1: Add planning phase to StreamPhase type and constants**

In `frontend/src/constants/streamingPresentation.ts`:

```typescript
// Line 1 — add 'planning':
export type StreamPhase = 'idle' | 'planning' | 'thinking' | 'summarizing' | 'summary_final';

// Line 5 — add planning labels:
export const STREAMING_LABELS = {
  planning_active: 'Creating plan...',
  planning_final: 'Plan',
  thinking: 'Thinking',
  summarizing_active: 'Writing report...',
  summarizing_final: 'Report complete',
  completed: 'Session complete',
  initializing: 'Initializing',
  waiting: 'Initializing',
} as const;

// Line 27 — add planning transitions:
export const VALID_PHASE_TRANSITIONS: Record<StreamPhase, ReadonlyArray<StreamPhase>> = {
  idle: ['planning', 'thinking', 'summarizing'],
  planning: ['thinking', 'summarizing', 'idle'],
  thinking: ['summarizing', 'idle'],
  summarizing: ['summary_final', 'idle'],
  summary_final: ['idle'],
};
```

**Step 2: Run type-check**

Run: `cd frontend && bun run type-check`
Expected: PASS (no type errors from the new phase)

**Step 3: Commit**

```bash
git add frontend/src/constants/streamingPresentation.ts
git commit -m "feat(streaming): add 'planning' phase to StreamPhase type and constants"
```

---

### Task 5: Create `PlanningPenIcon.vue` Animated SVG Component

**Files:**
- Create: `frontend/src/components/icons/PlanningPenIcon.vue`

**Step 1: Check icons directory exists**

Run: `ls frontend/src/components/icons/ | head -5`

**Step 2: Create the animated SVG component**

Create `frontend/src/components/icons/PlanningPenIcon.vue`:

```vue
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    class="planning-pen-icon"
    aria-hidden="true"
  >
    <!-- Paper -->
    <path
      d="M5 3C5 2.44772 5.44772 2 6 2H15L19 6V21C19 21.5523 18.5523 22 18 22H6C5.44772 22 5 21.5523 5 21V3Z"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linejoin="round"
      opacity="0.5"
    />
    <!-- Corner fold -->
    <path
      d="M15 2V6H19"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linejoin="round"
      opacity="0.35"
    />

    <!-- Writing lines (stroke-dashoffset animation) -->
    <line x1="8" y1="10" x2="15" y2="10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"
          stroke-dasharray="7" class="plan-line plan-line-1" />
    <line x1="8" y1="13.5" x2="13" y2="13.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"
          stroke-dasharray="5" class="plan-line plan-line-2" />
    <line x1="8" y1="17" x2="15" y2="17" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"
          stroke-dasharray="7" class="plan-line plan-line-3" />

    <!-- Pen -->
    <g class="plan-pen">
      <path
        d="M17.5 8.5L20.5 5.5L21.5 6.5L18.5 9.5L17.5 8.5Z"
        fill="currentColor"
        opacity="0.85"
      />
      <line x1="17.5" y1="9.5" x2="20.5" y2="6.5" stroke="currentColor" stroke-width="0.8" />
      <!-- Pen tip dot -->
      <circle cx="17.5" cy="9.5" r="0.6" fill="currentColor" class="pen-tip" />
    </g>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 20 });
</script>

<style scoped>
.plan-line {
  opacity: 0.6;
}

.plan-line-1 {
  animation: line-write 2.4s ease-in-out infinite;
}
.plan-line-2 {
  animation: line-write 2.4s ease-in-out infinite 0.6s;
}
.plan-line-3 {
  animation: line-write 2.4s ease-in-out infinite 1.2s;
}

@keyframes line-write {
  0% { stroke-dashoffset: 7; opacity: 0.2; }
  40% { stroke-dashoffset: 0; opacity: 0.7; }
  80% { stroke-dashoffset: 0; opacity: 0.7; }
  100% { stroke-dashoffset: 7; opacity: 0.2; }
}

.plan-pen {
  animation: pen-move 2.4s ease-in-out infinite;
}

@keyframes pen-move {
  0% { transform: translate(0, 0); }
  33% { transform: translate(-2px, 3.5px); }
  66% { transform: translate(0, 7px); }
  100% { transform: translate(0, 0); }
}

.pen-tip {
  animation: tip-pulse 0.8s ease-in-out infinite;
}

@keyframes tip-pulse {
  0%, 100% { opacity: 0.5; r: 0.4; }
  50% { opacity: 1; r: 0.8; }
}
</style>
```

**Step 3: Run lint**

Run: `cd frontend && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/icons/PlanningPenIcon.vue
git commit -m "feat(ui): add animated pen & paper SVG icon for plan streaming"
```

---

### Task 6: Handle `phase="planning"` in `ChatPage.vue`

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:770-790` (state), `2937-2979` (handlers)

**Step 1: Add reactive state**

In the state block around line 779, after `isSummaryStreaming`:

```typescript
  planStreamText: '',       // Accumulated streaming plan markdown
  isPlanStreaming: false,    // True when plan is streaming to live view
```

**Step 2: Extend `handleStreamEvent()`**

At `ChatPage.vue:2952`, after `const phase = streamData.phase || 'thinking';`, add the `planning` branch before the existing `summarizing` branch:

```typescript
  if (phase === 'planning') {
    if (streamData.lane === 'replace' && streamData.content) {
      // Replace mode: full plan replaces the progress header
      planStreamText.value = streamData.content;
    } else if (streamData.content) {
      planStreamText.value += streamData.content;
    }
    if (streamData.is_final) {
      isPlanStreaming.value = false;
    } else {
      isPlanStreaming.value = true;
    }
    return;
  }
```

**Step 3: Clear plan overlay on first tool event**

In `handleToolEvent()` (around line 2589), add near the top:

```typescript
  // Dismiss plan overlay when execution starts
  if (planStreamText.value) {
    planStreamText.value = '';
    isPlanStreaming.value = false;
  }
```

**Step 4: Pass props to ToolPanelContent**

Find where `ToolPanelContent` is used in the template and add the new props alongside the existing `summary-stream-text` and `is-summary-streaming`:

```html
:plan-stream-text="planStreamText"
:is-plan-streaming="isPlanStreaming"
```

**Step 5: Run type-check and lint**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS (may show errors until Task 7 adds the props to ToolPanelContent)

**Step 6: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat(chat): handle StreamEvent phase='planning' for live view plan streaming"
```

---

### Task 7: Add Plan Presentation Overlay in `ToolPanelContent.vue`

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue:588-599` (props), `724-735` (computed), `234-244` (template), `1037-1044` (header), `1-30` (icon import + activity bar)

**Step 1: Add props**

At `ToolPanelContent.vue` props block (after line 590):

```typescript
  planStreamText?: string;
  isPlanStreaming?: boolean;
```

**Step 2: Add computed**

After `showReportPresentation` computed (line 735), add:

```typescript
const showPlanPresentation = computed(() => {
  // Don't show plan if report is showing
  if (showReportPresentation.value) return false;
  if (!props.isPlanStreaming && !props.planStreamText) return false;
  return (props.planStreamText || '').length > 0;
});
```

**Step 3: Add template block**

After the report presentation `</div>` at line 244, before the unified streaming view at line 247, add:

```html
          <!-- Streaming Plan — rendered in EditorContentView during planning phase -->
          <div
            v-else-if="showPlanPresentation"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <EditorContentView
              :content="planStreamText || ''"
              filename="Plan.md"
              :is-writing="isPlanStreaming"
            />
          </div>
```

**Step 4: Update header label**

At `contentHeaderLabel` computed (line 1037), add before the report check at line 1041:

```typescript
  if (showPlanPresentation.value) {
    if (props.isPlanStreaming) return 'Creating plan...';
    return 'Plan';
  }
```

**Step 5: Add PlanningPenIcon to activity bar**

Import `PlanningPenIcon` at the top of the script:

```typescript
import PlanningPenIcon from '@/components/icons/PlanningPenIcon.vue'
```

In the activity bar template area (lines 10-30), where the report activity icon is shown when `isSummaryStreaming`, add a planning icon condition. Find the section with `panel-report-activity-icon-streaming` and add before it:

```html
            <PlanningPenIcon
              v-if="showPlanPresentation && isPlanStreaming"
              :size="16"
              class="text-purple-400"
            />
```

**Step 6: Run type-check and lint**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS

**Step 7: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "feat(live-view): add plan presentation overlay with animated pen icon"
```

---

### Task 8: Add `'planning'` Phase to `useStreamingPresentationState`

**Files:**
- Modify: `frontend/src/composables/useStreamingPresentationState.ts:13-27` (input interface), `148-160` (desiredPhase), `198-218` (headline/viewType)

**Step 1: Add planning inputs to interface**

In `StreamingPresentationInput` (line 13), add:

```typescript
  isPlanStreaming?: MaybeRefOrGetter<boolean | undefined>;
  planStreamText?: MaybeRefOrGetter<string | undefined>;
```

**Step 2: Update `desiredPhase` computed**

At line 148, add planning check before the summary check:

```typescript
  const desiredPhase = computed<StreamPhase>(() => {
    const planStreaming = Boolean(resolve(input.isPlanStreaming || false));
    const planText = resolve(input.planStreamText || '') || '';
    const summaryStreaming = resolve(input.isSummaryStreaming);
    const summaryText = resolve(input.summaryStreamText || '') || '';
    const finalReportText = resolve(input.finalReportText || '') || '';
    const thinking = Boolean(resolve(input.isThinking || false));
    const activeOperation = Boolean(resolve(input.isActiveOperation || false));

    if (summaryStreaming) return 'summarizing';
    if (finalReportText.length > 0) return 'summary_final';
    if (!summaryStreaming && summaryText.length > 0) return 'summary_final';
    if (planStreaming) return 'planning';
    if (thinking || activeOperation) return 'thinking';
    return 'idle';
  });
```

**Step 3: Update `headline` computed**

At line 200, add planning headline before summarizing:

```typescript
    if (phase.value === 'planning') return STREAMING_LABELS.planning_active;
```

**Step 4: Update `isSummaryPhase` to also cover planning**

Add a new computed for planning phase:

```typescript
  const isPlanningPhase = computed(() => phase.value === 'planning');
```

Export it alongside `isSummaryPhase`.

**Step 5: Update `viewType` computed**

At line 215, add planning view type:

```typescript
  const viewType = computed<StreamingViewType>(() => {
    if (isPlanningPhase.value) return 'report';  // reuse report view type for plan editor
    if (isSummaryPhase.value) return 'report';
    return resolve(input.baseViewType || 'generic') || 'generic';
  });
```

**Step 6: Wire planning inputs where the composable is called**

In `ToolPanelContent.vue`, find where `useStreamingPresentationState` is called (around line 990) and add:

```typescript
  isPlanStreaming: computed(() => !!props.isPlanStreaming),
  planStreamText: computed(() => props.planStreamText || ''),
```

**Step 7: Run type-check**

Run: `cd frontend && bun run type-check`
Expected: PASS

**Step 8: Commit**

```bash
git add frontend/src/composables/useStreamingPresentationState.ts frontend/src/constants/streamingPresentation.ts frontend/src/components/ToolPanelContent.vue
git commit -m "feat(streaming): add planning phase to streaming presentation state machine"
```

---

### Task 9: Update `LiveMiniPreview.vue` for Planning Phase

**Files:**
- Modify: `frontend/src/components/LiveMiniPreview.vue`

**Step 1: Find the current summary phase handling**

Read `LiveMiniPreview.vue` and find where `isSummaryPhase` controls the report mini preview. Add analogous handling for planning.

**Step 2: Add planning phase preview**

Where the component checks for `isSummaryPhase` to show the report mini window, add a check for `isPlanningPhase`:

```html
<!-- Planning mini preview (same pattern as summary mini preview) -->
<div v-if="isPlanningPhase" class="streaming-mini-window planning-mini">
  <div class="flex items-center gap-1.5 mb-1">
    <PlanningPenIcon :size="14" class="text-purple-400" />
    <span class="text-xs font-medium text-[var(--text-secondary)]">
      {{ headline }}
    </span>
  </div>
  <!-- Mini markdown preview of plan text -->
  ...
</div>
```

Import `PlanningPenIcon` and wire `isPlanningPhase` from the streaming presentation state.

**Step 3: Run lint**

Run: `cd frontend && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/LiveMiniPreview.vue
git commit -m "feat(mini-preview): show plan streaming preview with pen icon"
```

---

### Task 10: Integration Test — Full E2E Verification

**Step 1: Run backend tests**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_planner_plan_markdown.py tests/domain/services/test_planner_stream_events.py -v`
Expected: All tests PASS

**Step 2: Run full backend lint**

Run: `cd backend && conda run -n pythinker ruff check . && ruff format --check .`
Expected: PASS

**Step 3: Run frontend checks**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS

**Step 4: Manual E2E test**

1. Start the dev stack: `./dev.sh watch`
2. Open `http://localhost:5174` in browser
3. Submit a Research query
4. **Verify:** Live view panel immediately shows "Plan.md" editor with "# Planning..." header
5. **Verify:** Animated pen icon visible in the panel header with "Creating plan..." label
6. **Verify:** Progress lines appear ("Analyzing your request...", "Creating execution plan...")
7. **Verify:** After ~14s, full formatted plan replaces the progress header with steps, metadata table, tool hints
8. **Verify:** When first tool event fires (search), plan overlay dismisses and tool view takes over
9. **Verify:** The left panel PlanningCard still works as before (not broken)

**Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address integration test issues for live plan streaming"
```
