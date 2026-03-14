# Live Plan Streaming in Live View — Design Document

**Date:** 2026-03-14
**Author:** Mohamed Elkholy
**Status:** Revised after architecture validation

## Problem

During the planning phase, the live view panel shows a mostly idle browser/sandbox frame while the left chat column shows a small `PlanningCard`. For first-message interactions this leaves the primary visual surface inactive for 10-17 seconds, even though the agent is already analyzing and building a plan.

## Review Outcome

The original direction is good, but four parts of the first draft were not aligned with the current codebase:

1. Phase-1 planning text should **not** be duplicated as backend `StreamEvent`s. The frontend already receives `ProgressEvent`s, and the orchestration flow already emits repeated `PlanningPhase.PLANNING` heartbeats while the planner waits on the LLM. Mirroring those as extra stream events would add protocol noise and duplicate lines.
2. `StreamEvent.phase` is already a plain string. No backend event-model/schema change is required to allow `"planning"`.
3. Planning/report/thinking presentation should stay in the shared `useStreamingPresentationState()` path. A ToolPanel-only state fork would drift from `TaskProgressBar` and `LiveMiniPreview`.
4. The rendered plan markdown must use deterministic planner data. The original example invented metadata such as `Mode` and `Est. Time`, which are not first-class planner outputs today.

## Validated Solution

Use a **two-stage presentation model**:

1. **Phase 1: frontend-derived planning scaffold**
   Build a lightweight markdown scaffold in `ChatPage.vue` from the existing `ProgressEvent`s.
2. **Phase 2: backend-streamed final plan markdown**
   After the `Plan` object is built, stream a formatted markdown version of the final plan via `StreamEvent(phase="planning")`.

This keeps the current planner logic intact, avoids duplicate transport events, and reuses the existing report/streaming presentation architecture.

## Current Code Constraints

These constraints are already true in the repo and must shape the implementation:

- `backend/app/domain/services/flows/plan_act.py` already emits repeated `ProgressEvent(phase=PlanningPhase.PLANNING, message="Generating plan...")` heartbeats while `create_plan()` is running.
- `backend/app/domain/models/event.py` already defines `StreamEvent.phase` as `str`, so `"planning"` is already valid.
- `frontend/src/constants/streamingPresentation.ts` currently only knows `idle`, `thinking`, `summarizing`, and `summary_final`; this is the real phase-model change point.
- `frontend/src/components/ui/MonacoEditor.vue` updates content with `model.setValue()` on every prop change, so synthetic plan streaming must use a small number of coarse chunks rather than many tiny updates.

## UX Behavior

### Phase 1: Progress-Derived Scaffold

As soon as meaningful planning progress arrives, the live panel should switch from the idle browser frame to a markdown editor overlay:

```markdown
# Planning...

> Analyzing task complexity...
> Creating execution plan...
```

Rules:

- Ignore `received` for the markdown body. It is useful as transport/ack feedback but too noisy as a visible plan line.
- Deduplicate repeated `planning` heartbeat messages such as `"Generating plan..."`.
- Keep existing `thinkingText` behavior intact for the left-side reasoning surfaces; the planning overlay is a new live-view presentation layer, not a replacement for internal reasoning telemetry.

### Phase 2: Final Plan Markdown

Once the planner has built a `Plan`, replace the scaffold with a richer markdown view streamed into the editor:

```markdown
# AI Agent Frameworks Comparison 2026

> Research and compare LangGraph, CrewAI, AutoGen, and OpenAI Agents SDK
> across architecture, tool use, multi-agent coordination, and production readiness.

| Info | Detail |
| --- | --- |
| Complexity | Complex |
| Steps | 3 |
| Planner | Standard |

---

## Step 1 — Research

Research LangGraph, CrewAI, AutoGen, and OpenAI Agents SDK architecture and capabilities.

Expected output: Collected source notes and comparison criteria.

> Tool hint: browser, web_search

---

## Step 2 — Analyze

Analyze findings and produce a structured comparison with decision-ready takeaways.

Expected output: Draft comparison sections and supporting tables.

> Tool hint: file, code_executor

---

## Step 3 — Deliver

Validate the comparison, finalize the report, and deliver the output.

Expected output: Final markdown report with verified claims.

> Tool hint: file
```

Formatting rules:

- H1 from `plan.title`
- Goal as blockquote from `plan.goal`
- Metadata table includes only fields already available at planning time:
  - `Complexity`
  - `Steps`
  - `Planner` (`Draft`, `Standard`, or `Fallback`)
- Optional intro paragraph from `plan.message`
- Each step rendered from deterministic step data:
  - Heading prefers `action_verb`, otherwise `Step N`
  - Main body uses `description`
  - Optional `Expected output` from `expected_output`
  - Optional `Tool hint` from `tool_hint`
- Omit fabricated metadata such as time estimates or mode labels until the planner produces real fields for them

## State Ownership

### Backend Owns

- Final formatted plan markdown
- Synthetic chunk streaming for the final plan only
- Fallback-plan formatting through the same formatter

### Frontend Owns

- Phase-1 scaffold text derived from `ProgressEvent`
- Deduplication of repeated progress heartbeats
- Overlay visibility and lifecycle
- Clearing the overlay when the first real tool starts

This split avoids duplicate backend events while still keeping the final plan rendering deterministic and centralized.

## Backend Changes

### `backend/app/domain/services/agents/planner.py`

Add:

- `_format_plan_as_markdown(plan, *, complexity, planner_kind) -> str`
- `_stream_plan_as_markdown(markdown_text) -> AsyncGenerator[StreamEvent, None]`

Behavior:

1. Keep the existing `ask_structured()` path unchanged.
2. After the `Plan` object is built, call `_format_plan_as_markdown(...)`.
3. Stream the markdown as `StreamEvent(phase="planning")` chunks.
4. Emit `StreamEvent(phase="planning", is_final=True)` after the last chunk.
5. Then emit `PlanEvent(status=CREATED, plan=plan)`.
6. Apply the same formatting/streaming path to the fallback plan.

Streaming constraints:

- Chunk size target: `140-220` characters
- Target chunk count: `4-8`
- Total synthetic delay budget: `<= 250ms`
- Do not swallow `asyncio.CancelledError`

Rationale:

- The current Monaco wrapper performs full-model `setValue()` updates on every content change, so coarse chunks are safer than 40-50 tiny updates per second.
- The stream is only for visible animation; it must not noticeably delay plan availability.

### No Backend Model or Schema Change

No change is needed in:

- `backend/app/domain/models/event.py`
- `backend/app/interfaces/schemas/event.py`

Reason: `StreamEvent.phase` and `StreamEventData.phase` are already string-typed.

## Frontend Changes

### `frontend/src/pages/ChatPage.vue`

Add planning presentation state:

```typescript
const planPresentationText = ref('')
const isPlanStreaming = ref(false)
const planPresentationSource = ref<'idle' | 'progress' | 'stream' | 'final'>('idle')
const lastPlanningProgressSignature = ref('')
```

Add a helper that builds the scaffold from progress events:

```typescript
const updatePlanProgressPresentation = (progressData: ProgressEventData) => {
  if (planPresentationSource.value === 'stream' || planPresentationSource.value === 'final') {
    return
  }

  const phase = normalizePlanningPhase(progressData.phase)
  if (phase === 'received') return

  const line = progressData.message?.trim()
  if (!line) return

  const signature = `${phase}:${line}`
  if (signature === lastPlanningProgressSignature.value) return
  lastPlanningProgressSignature.value = signature

  if (!planPresentationText.value) {
    planPresentationText.value = '# Planning...\n\n'
  }

  planPresentationText.value += `> ${line}\n`
  planPresentationSource.value = 'progress'
}
```

Update `handleProgressEvent()`:

- Continue updating the existing planning card/progress state
- Also call `updatePlanProgressPresentation(progressData)`
- Stop modifying the scaffold once final plan markdown streaming has started

Update `handleStreamEvent()`:

```typescript
if (phase === 'planning') {
  if (planPresentationSource.value !== 'stream') {
    planPresentationText.value = ''
    planPresentationSource.value = 'stream'
  }

  if (streamData.content) {
    planPresentationText.value += streamData.content
  }

  isPlanStreaming.value = !streamData.is_final
  if (streamData.is_final) {
    planPresentationSource.value = 'final'
  }
  return
}
```

Important behavior:

- Keep the existing `thinking` stream handling for reasoning views
- Do not clear `planPresentationText` in `handlePlanEvent()`
- Clear the planning presentation on the first real tool start (`calling` / `running`)
- Clear it on cancellation, reset, or session teardown
- Pass the new planning props into both the bottom-dock `TaskProgressBar` and the right-side `ToolPanel`

### `frontend/src/components/ToolPanel.vue`

Thread the new props through to `ToolPanelContent`:

- `planPresentationText`
- `isPlanStreaming`

### `frontend/src/components/ToolPanelContent.vue`

Add planning props and render ordering:

1. report overlay
2. planning overlay
3. unified tool streaming
4. normal tool/live/replay views

Add:

```typescript
planPresentationText?: string
isPlanStreaming?: boolean
```

Add a replay-aware guard similar to the report overlay:

```typescript
const showPlanPresentation = computed(() => {
  if (props.showTimeline && !props.realTime && !isViewingLatestTimelineStep.value) return false
  return (props.planPresentationText || '').length > 0
})
```

Render the planning overlay with `EditorContentView`:

```html
<div
  v-else-if="showPlanPresentation"
  class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
>
  <EditorContentView
    :content="props.planPresentationText || ''"
    filename="Plan.md"
    :is-writing="!!props.isPlanStreaming"
  />
</div>
```

Header behavior:

- Use the shared streaming state machine for the label
- Reuse an existing Lucide icon such as `PencilLine` or `FileText` with a subtle pulse
- Do **not** create a bespoke `PlanningPenIcon.vue` unless design review later decides the existing icon set is insufficient

This follows the repo's reuse-first rule and keeps the surface area smaller.

### `frontend/src/components/TaskProgressBar.vue`

Add the same planning props so the collapsed/expanded `LiveMiniPreview` can show planning state when the tool panel is closed:

- `planPresentationText`
- `isPlanStreaming`

Thread them into both `LiveMiniPreview` instances.

### `frontend/src/components/LiveMiniPreview.vue`

Extend the mini preview so planning shares the same visual path as report preview:

- show planning preview when the shared streaming state is in the `planning` phase
- reuse the existing lightweight markdown renderer for the preview body
- show `"Creating plan..."` while streaming and `"Plan ready"` after final chunk

### `frontend/src/composables/useStreamingPresentationState.ts`

This is the central architecture change on the frontend.

Extend the input shape:

```typescript
isPlanStreaming?: MaybeRefOrGetter<boolean | undefined>
planPresentationText?: MaybeRefOrGetter<string | undefined>
```

Extend the phase model:

```typescript
type StreamPhase = 'idle' | 'planning' | 'thinking' | 'summarizing' | 'summary_final'
```

Desired phase precedence:

1. `summarizing`
2. `summary_final`
3. `planning`
4. `thinking`
5. `idle`

Reasoning:

- Summary/report must always win
- Planning should win over generic thinking/tool activity while the overlay is still visible
- Once the first tool starts and planning text is cleared, normal tool/thinking presentation resumes

The composable should expose:

- `isPlanningPhase`
- planning-aware `headline`
- planning-aware `previewText`

### `frontend/src/constants/streamingPresentation.ts`

Update:

- `StreamPhase`
- `VALID_PHASE_TRANSITIONS`
- `STREAMING_LABELS`

Suggested transitions:

- `idle -> planning`
- `planning -> thinking`
- `planning -> idle`
- `planning -> summarizing`
- existing summary transitions remain unchanged

## Data Flow

```text
User sends message
  -> Backend: ProgressEvent(received) [existing]
  -> Frontend: no plan markdown yet

  -> Backend: ProgressEvent(analyzing, "Analyzing task complexity...")
  -> Frontend: build scaffold
     # Planning...
     > Analyzing task complexity...

  -> Backend: ProgressEvent(planning, "Creating execution plan...")
  -> Frontend: append deduped scaffold line

  -> Backend: repeated ProgressEvent(planning, "Generating plan...") heartbeat(s)
  -> Frontend: append once, ignore duplicates

  -> Backend: plan built
  -> Backend: StreamEvent(phase="planning", content=chunk_1)
  -> Frontend: clear scaffold, switch source=stream, start final markdown

  -> Backend: StreamEvent(phase="planning", content=chunk_n)
  -> Backend: StreamEvent(phase="planning", is_final=true)
  -> Frontend: isPlanStreaming=false, source=final, plan markdown remains visible

  -> Backend: PlanEvent(CREATED, plan=plan)
  -> Frontend: left-side plan UI updates; live panel keeps final plan markdown

  -> Backend: first real ToolEvent(status=calling)
  -> Frontend: clear planning presentation and return to tool/live view
```

## Edge Cases

| Case | Handling |
| --- | --- |
| Planner fallback plan | Format and stream fallback markdown through the same phase-2 path |
| User cancels during planning | Clear planning presentation state immediately |
| Replan flow | Reuse the same formatter; planner metadata row shows `Planner = Standard` unless draft/fallback was used |
| Verification after plan creation | Keep the final plan visible; do not resume appending progress scaffold |
| Timeline replay mode | Hide planning overlay unless the user is at the latest/live position |
| Fast draft plan | Same UI; metadata row shows `Planner = Draft` |
| First tool never starts because execution aborts | Final plan remains visible until reset/error/cancel |

## Files to Modify

### Edit

- `backend/app/domain/services/agents/planner.py`
- `frontend/src/pages/ChatPage.vue`
- `frontend/src/components/ToolPanel.vue`
- `frontend/src/components/ToolPanelContent.vue`
- `frontend/src/components/TaskProgressBar.vue`
- `frontend/src/components/LiveMiniPreview.vue`
- `frontend/src/composables/useStreamingPresentationState.ts`
- `frontend/src/constants/streamingPresentation.ts`

### Test Updates

- `backend/tests/unit/agents/test_planner.py`
- `frontend/tests/composables/useStreamingPresentationState.spec.ts`
- `frontend/tests/components/ToolPanelContent.spec.ts`
- `frontend/tests/components/ToolPanel.spec.ts`
- add or extend `ChatPage` tests for planning presentation lifecycle

### No Change Required

- `backend/app/domain/models/event.py`
- `backend/app/interfaces/schemas/event.py`
- `frontend/src/types/event.ts`

## Test Plan

### Backend

- plan markdown formatter renders deterministic fields only
- formatter omits `Expected output` / `Tool hint` when absent
- fallback plan streams through the same path
- planning stream emits `phase="planning"` chunks followed by `is_final=True`

### Frontend

- repeated planning heartbeat progress events do not append duplicate scaffold lines
- first `planning` stream chunk replaces the scaffold instead of appending to it
- planning overlay takes priority over live/tool view but not over report overlay
- planning overlay hides on first real tool start
- replay/timeline guard suppresses stale planning overlays when viewing older timeline steps
- `useStreamingPresentationState` accepts `planning` transitions and exposes the right headline/preview text

## Context7 Validation Notes

Validated against Context7 MCP and official docs:

- **Vue 3 (`/vuejs/docs`)**
  - Use `computed()` for derived UI state instead of duplicating reactive state in multiple components.
  - Use watcher cleanup/effect-scope cleanup patterns for timers and transient subscriptions.
  - This supports extending `useStreamingPresentationState()` rather than creating a separate ToolPanel-only planning state machine.
- **Python asyncio (`/python/cpython`)**
  - Async generators should allow cancellation to propagate and should rely on normal generator finalization.
  - `_stream_plan_as_markdown()` must not suppress `CancelledError`.
- **Monaco Editor (`/microsoft/monaco-editor`)**
  - Text models support full-value updates, but frequent model rewrites should be minimized.
  - Because the current wrapper uses `model.setValue()` on every prop change, planning chunks should be coarse and bounded.

Official references consulted during validation:

- `https://vuejs.org/guide/essentials/computed.html`
- `https://vuejs.org/guide/essentials/watchers.html`
- `https://docs.python.org/3/library/asyncio-task.html`
- `https://microsoft.github.io/monaco-editor/typedoc/interfaces/editor.ITextModel.html`
