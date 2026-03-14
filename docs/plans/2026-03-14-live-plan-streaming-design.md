# Live Plan Streaming in Live View — Design Document

**Date:** 2026-03-14
**Author:** Mohamed Elkholy
**Status:** Approved

## Problem

During the planning phase (~14-17s), the live view panel (right side) shows an empty CDP screencast — the sandbox desktop with nothing happening. The user only sees a small `PlanningCard` in the left chat panel with phase text like "Analyzing task complexity..." and a progress bar. The live view, the most prominent visual element, is completely dead during the user's first interaction with the agent.

## Solution

Stream the plan as a well-formatted markdown document into the live view's Monaco editor in real-time, using the same `StreamEvent` pattern as the existing "Writing report..." flow. An animated pen-and-paper SVG icon indicates active planning in the tool panel header.

## Approach: Synthetic Plan Stream

Keep the proven `ask_structured()` planner unchanged. Emit `StreamEvent(phase="planning")` at two points:

1. **During LLM wait** — Convert progress phases to markdown lines (immediate live view activity)
2. **After plan arrives** — Convert the `Plan` object to rich formatted markdown, stream it chunk-by-chunk

No extra LLM cost. No changes to the structured output path.

## Plan Markdown Format

### Phase 1 — During LLM Wait (progress phases)

```markdown
# Planning...

> Analyzing task complexity...
```

As new progress phases arrive, lines are appended:

```markdown
# Planning...

> Analyzing task complexity...
> Creating execution plan...
```

### Phase 2 — Full Plan (replaces phase 1 content)

```markdown
# AI Agent Frameworks Comparison 2026

> **Goal:** Research and compare LangGraph, CrewAI, AutoGen, and OpenAI
> Agents SDK across architecture, tool use, multi-agent coordination,
> and production readiness.

| Info            | Detail              |
|-----------------|---------------------|
| **Complexity**  | Very Complex        |
| **Steps**       | 3                   |
| **Est. Time**   | 10-15 min           |
| **Mode**        | Research            |

---

## Step 1 - Research

**Research LangGraph, CrewAI, AutoGen, and OpenAI Agents SDK architecture and capabilities**

Search for current documentation, GitHub repositories, and technical
reviews for each framework. Compare architecture patterns, tool use
APIs, and multi-agent coordination approaches.

> Tools: Web Search, Browser

---

## Step 2 - Analyze

**Analyze findings and compile structured comparison report with data tables**

Cross-reference research findings to identify key differences in
architecture patterns, production readiness, and developer experience.

> Tools: File Editor, Code Executor

---

## Step 3 - Verify & Deliver

**Review report accuracy, validate all citations, and deliver final research report**

Verify factual claims against sources, check citation integrity,
generate visual charts, and produce the final downloadable report.

> Tools: Web Search, Browser, File Editor

---

*Plan created by Pythinker*
```

Key design elements:
- **Title** from `plan.title` — prominent H1
- **Goal blockquote** from `plan.goal`
- **Metadata table** — complexity, step count, estimated time, mode
- **Each step** as H2 with step number and action verb category
- **Bold description** as step headline
- **Tool hint blockquote** with tool names
- **Horizontal rules** between sections
- **Footer** with attribution

## Backend Changes

### `planner.py` — New helpers and StreamEvent emissions

**`_format_plan_as_markdown(plan, complexity, mode)`** — Converts a `Plan` object + metadata into the formatted markdown string shown above.

**`_stream_plan_as_markdown(markdown_text)`** — Async generator that yields `StreamEvent(phase="planning")` events, splitting the markdown into ~100-char chunks with `asyncio.sleep(0.02)` between chunks (~50 chunks/sec, ~0.5s total for a typical 3-step plan).

**Changes to `create_plan()`:**

1. After each `ProgressEvent` yield, also yield a `StreamEvent(phase="planning")` with the progress line as markdown content.

2. After `ask_structured()` returns and the `Plan` object is built, call `_format_plan_as_markdown()` to get the full markdown, then yield chunks via `_stream_plan_as_markdown()`.

3. After all chunks, yield `StreamEvent(phase="planning", is_final=True)`.

4. Then yield the existing `PlanEvent(status=CREATED, plan=plan)` as before.

### `event.py` — Ensure `"planning"` is valid for StreamEvent.phase

Add `"planning"` to the phase field's accepted values if it uses a string enum.

## Frontend Changes

### `ChatPage.vue` — New reactive state and event handling

**New state:**
```typescript
const planStreamText = ref('')
const isPlanStreaming = ref(false)
```

**Extend `handleStreamEvent()`:**
```typescript
if (phase === 'planning') {
  if (streamData.content) {
    planStreamText.value += streamData.content
  }
  if (streamData.is_final) {
    isPlanStreaming.value = false
  } else {
    isPlanStreaming.value = true
  }
  return
}
```

**Extend `handlePlanEvent()`:**
```typescript
// After existing plan handling...
// Don't clear planStreamText immediately — let it persist until first tool event
```

**Clear plan overlay on first tool event:**
```typescript
// In handleToolEvent(), when the first tool starts:
if (planStreamText.value) {
  planStreamText.value = ''
  isPlanStreaming.value = false
}
```

**Pass as props to ToolPanelContent:**
```typescript
:plan-stream-text="planStreamText"
:is-plan-streaming="isPlanStreaming"
```

### `ToolPanelContent.vue` — Plan presentation overlay

**New props:**
```typescript
planStreamText: { type: String, default: '' }
isPlanStreaming: { type: Boolean, default: false }
```

**New computed:**
```typescript
const showPlanPresentation = computed(() => {
  if (!props.isPlanStreaming && !props.planStreamText) return false
  return props.planStreamText.length > 0
})
```

**Template (priority: below report, above tool views):**
```html
<div v-else-if="showPlanPresentation" class="absolute inset-0 ...">
  <EditorContentView
    :content="planStreamText"
    filename="Plan.md"
    :is-writing="isPlanStreaming"
  />
</div>
```

**Header label logic:**
```typescript
if (showPlanPresentation.value) {
  if (props.isPlanStreaming) return 'Creating plan...'
  return 'Plan'
}
```

**Header icon:** Use `PlanningPenIcon` component (animated SVG) when `showPlanPresentation && isPlanStreaming`.

### `PlanningPenIcon.vue` — NEW animated SVG component

**Location:** `frontend/src/components/icons/PlanningPenIcon.vue`

A custom animated SVG (24x24 viewBox, renders at 20x20px) with:

1. **Paper** — document shape with corner fold, `stroke="currentColor"`
2. **Writing lines** — 3-4 horizontal strokes with `stroke-dashoffset` animation (lines appear one by one as if being written)
3. **Pen** — angled pen shape with `animateTransform` moving down as lines appear
4. **Pen tip glow** — subtle opacity pulse at the write point

Animation: 2s loop, all elements synced. Color inherits `currentColor` (uses `text-purple-400` during planning).

### `useStreamingPresentationState.ts` — Add planning phase

Add `'planning'` phase to the state machine, triggered when `isPlanStreaming` is true. This enables `LiveMiniPreview` to show the plan when the tool panel is collapsed.

**Phase order:** `idle` -> `planning` -> `thinking` -> `summarizing` -> `summary_final`

### `LiveMiniPreview.vue` — Planning phase thumbnail

When `isPlanningPhase` is true, show a mini preview with:
- `PlanningPenIcon` (small)
- Headline: `"Creating plan..."`
- First few lines of `planStreamText` rendered as markdown preview

## Data Flow (End-to-End)

```
User sends message
  -> Backend: ProgressEvent(phase=RECEIVED)
  -> Backend: StreamEvent(phase="planning", content="# Planning...\n\n> Message received...")
  -> Frontend: planStreamText grows, Monaco editor shows "Plan.md"
  -> Frontend: ToolPanelContent header shows PlanningPenIcon + "Creating plan..."

  -> Backend: ProgressEvent(phase=ANALYZING)
  -> Backend: StreamEvent(phase="planning", content="\n> Analyzing task complexity...")
  -> Frontend: planStreamText grows, new line appears in editor

  -> Backend: ask_structured() returns PlanResponse (~14s)
  -> Backend: StreamEvent(phase="planning", content=full_plan_chunk) x N
  -> Backend: StreamEvent(phase="planning", is_final=True)
  -> Frontend: isPlanStreaming=false, header shows "Plan" (static)

  -> Backend: PlanEvent(status=CREATED, plan=plan)
  -> Frontend: plan steps appear in left panel, plan editor persists

  -> Backend: First ToolEvent (step 1 begins)
  -> Frontend: planStreamText cleared, tool view takes over live panel
```

## Edge Cases

| Case | Handling |
|------|----------|
| Plan creation fails (fallback plan) | Still format and stream the fallback plan markdown |
| User cancels during planning | Clear `planStreamText`, set `isPlanStreaming=false` |
| SSE reconnect during planning | Existing Redis queue reconnect handles StreamEvents |
| Fast path (greeting/knowledge) | No planning phase, no StreamEvents emitted |
| Plan verification enabled | Plan stays visible during verification |
| Deep research mode | Same flow, plan appears before workspace init |
| Report overlay active | Report takes priority (`v-if` over `v-else-if`) |

## Chunk Streaming Parameters

- **Chunk size:** ~80-120 characters per StreamEvent
- **Delay:** `asyncio.sleep(0.02)` between chunks (~50 chunks/sec)
- **Typical plan:** ~500-800 chars markdown -> ~0.5-1s streaming time
- **Progress phase lines:** Emitted immediately (no chunking delay)

## Files to Modify

| File | Type | Change |
|------|------|--------|
| `backend/app/domain/services/agents/planner.py` | Edit | Add `_format_plan_as_markdown()`, `_stream_plan_as_markdown()`, yield StreamEvents in `create_plan()` |
| `backend/app/domain/models/event.py` | Edit | Add `"planning"` to StreamEvent phase |
| `frontend/src/pages/ChatPage.vue` | Edit | Add `planStreamText`, `isPlanStreaming`, extend `handleStreamEvent()`, clear on tool event |
| `frontend/src/components/ToolPanelContent.vue` | Edit | Add `showPlanPresentation`, template block, header with PlanningPenIcon |
| `frontend/src/components/icons/PlanningPenIcon.vue` | New | Animated pen & paper SVG component |
| `frontend/src/composables/useStreamingPresentationState.ts` | Edit | Add `'planning'` phase |
| `frontend/src/components/LiveMiniPreview.vue` | Edit | Planning phase mini preview |
