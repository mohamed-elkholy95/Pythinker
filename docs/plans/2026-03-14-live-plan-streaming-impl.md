# Live Plan Streaming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show useful, structured planning activity in the live view during plan creation, then keep the final rendered plan visible until execution actually starts.

**Architecture:** Use the validated two-stage approach from the design doc. Phase 1 is frontend-owned: `ChatPage.vue` derives a lightweight markdown scaffold from existing `ProgressEvent`s and deduplicates repeated planning heartbeats. Phase 2 is backend-owned: `planner.py` formats the final `Plan` into deterministic markdown and streams it via `StreamEvent(phase="planning")`, while the frontend routes both panel and mini-preview presentation through the existing shared `useStreamingPresentationState()` path.

**Tech Stack:** Python 3.12 asyncio, Pydantic models, Vue 3 Composition API, Vitest, Monaco Editor, Lucide icons

---

## Guardrails

- Follow [2026-03-14-live-plan-streaming-design.md](/home/mac/Desktop/Pythinker-main/docs/plans/2026-03-14-live-plan-streaming-design.md) as the source of truth.
- Do **not** add backend `StreamEvent`s for progress lines. Phase 1 stays frontend-derived from `ProgressEvent`.
- Do **not** add or change backend event schemas just to allow `"planning"`; `StreamEvent.phase` is already a string.
- Do **not** create `PlanningPenIcon.vue`. Reuse an existing Lucide icon such as `PencilLine`.
- Keep synthetic plan chunks coarse because the current Monaco wrapper rewrites the full model on each prop change.
- Do **not** invent planner metadata like time estimates or mode labels that do not exist in the `Plan` object today.
- Keep the final plan visible until the first real tool enters `calling` or `running`.

## References

- Design: [2026-03-14-live-plan-streaming-design.md](/home/mac/Desktop/Pythinker-main/docs/plans/2026-03-14-live-plan-streaming-design.md)
- Vue best practices: use computed/derived state, keep watcher cleanup explicit
- Monaco best practices: avoid excessive model rewrites
- Python asyncio best practices: let `CancelledError` propagate through async generators

---

### Task 1: Add Backend Plan Markdown Formatting and Planning Stream Tests

**Files:**
- Modify: `backend/app/domain/services/agents/planner.py`
- Create: `backend/tests/unit/agents/test_planner_plan_streaming.py`

**Step 1: Write the failing backend tests**

Create `backend/tests/unit/agents/test_planner_plan_streaming.py` with focused coverage for:

- `_format_plan_as_markdown()` includes:
  - H1 from `plan.title`
  - goal blockquote from `plan.goal`
  - metadata table with `Complexity`, `Steps`, and `Planner`
  - step sections using `action_verb`, `description`, `expected_output`, and `tool_hint`
- `_format_plan_as_markdown()` omits:
  - unsupported metadata such as time estimates
  - `Expected output` block when `expected_output` is missing
  - `Tool hint` block when `tool_hint` is missing
- `create_plan()` emits one or more `StreamEvent(phase="planning")` items before `PlanEvent(status=CREATED, ...)`
- `create_plan()` emits `StreamEvent(is_final=True, phase="planning")` before the `PlanEvent`
- fallback-plan path also emits the same planning stream sequence

Use a small synthetic `Plan` fixture with three steps and structured fields already supported by `Step`.

**Step 2: Run the backend test to confirm failure**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/unit/agents/test_planner_plan_streaming.py -q
```

Expected: FAIL because the markdown formatter / planning stream helpers do not exist yet.

**Step 3: Implement the minimal backend behavior**

In `backend/app/domain/services/agents/planner.py`:

- Add `_format_plan_as_markdown(plan, *, complexity, planner_kind) -> str`
- Add a small synchronous chunk helper such as `_iter_plan_markdown_chunks(text, chunk_size=180)` so chunking can be unit-tested without spinning an event loop
- Add `_stream_plan_as_markdown(text) -> AsyncGenerator[StreamEvent, None]`
- Wire the success path so it:
  - builds the final `Plan`
  - formats markdown
  - emits planning chunks
  - emits `StreamEvent(content="", is_final=True, phase="planning")`
  - emits the existing `PlanEvent(status=CREATED, plan=plan)`
- Wire the fallback-plan path through the same formatter and planning stream

Implementation rules:

- Do not stream progress-phase scaffold text from the backend
- Keep chunk size roughly `140-220` characters
- Keep total synthetic delay budget under `250ms`
- Do not catch or suppress `asyncio.CancelledError`
- Do not change `backend/app/domain/models/event.py`

**Step 4: Re-run the backend test**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/unit/agents/test_planner_plan_streaming.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/planner.py backend/tests/unit/agents/test_planner_plan_streaming.py
git commit -m "feat(planner): stream final plan markdown to live view"
```

---

### Task 2: Extend the Shared Streaming Presentation State for Planning

**Files:**
- Modify: `frontend/src/constants/streamingPresentation.ts`
- Modify: `frontend/src/composables/useStreamingPresentationState.ts`
- Test: `frontend/tests/composables/useStreamingPresentationState.spec.ts`

**Step 1: Add failing composable tests**

Extend `frontend/tests/composables/useStreamingPresentationState.spec.ts` with cases for:

- planning phase activates when `planPresentationText` exists
- `isPlanStreaming=true` yields headline `"Creating plan..."`
- `isPlanStreaming=false` with retained `planPresentationText` yields `"Plan ready"`
- summary streaming still overrides planning
- planning preview text comes from `planPresentationText`, not tool preview text
- transitions allow `idle -> planning -> thinking` and `planning -> idle`

**Step 2: Run the targeted frontend test**

Run:

```bash
cd frontend && bun run test:run tests/composables/useStreamingPresentationState.spec.ts
```

Expected: FAIL because the composable does not know about planning yet.

**Step 3: Implement planning support in the shared state machine**

Update `frontend/src/constants/streamingPresentation.ts`:

- add `'planning'` to `StreamPhase`
- add planning labels
- update `VALID_PHASE_TRANSITIONS`

Update `frontend/src/composables/useStreamingPresentationState.ts`:

- extend the input shape with:
  - `isPlanStreaming`
  - `planPresentationText`
- make phase precedence:
  - `summarizing`
  - `summary_final`
  - `planning`
  - `thinking`
  - `idle`
- expose `isPlanningPhase`
- produce planning-aware `headline`
- produce planning-aware `previewText`

Implementation rules:

- reuse `computed()` and existing derived-state patterns
- do not create a second presentation state machine for plan streaming
- do not add a new `StreamingViewType` unless it is strictly needed by the code after implementation

**Step 4: Re-run the targeted frontend test**

Run:

```bash
cd frontend && bun run test:run tests/composables/useStreamingPresentationState.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/constants/streamingPresentation.ts frontend/src/composables/useStreamingPresentationState.ts frontend/tests/composables/useStreamingPresentationState.spec.ts
git commit -m "feat(frontend): add planning phase to streaming presentation state"
```

---

### Task 3: Add ChatPage Planning Presentation Lifecycle

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- Create: `frontend/tests/pages/ChatPage.planning-presentation.spec.ts`

**Step 1: Write failing ChatPage lifecycle tests**

Create `frontend/tests/pages/ChatPage.planning-presentation.spec.ts` with focused state tests for:

- progress scaffold starts with `# Planning...`
- `received` progress is ignored for visible markdown
- repeated `planning` heartbeat messages append only once
- first `StreamEvent(phase="planning")` clears the progress scaffold and starts the final markdown body
- `PlanEvent` does not clear the final markdown
- first tool with status `calling` or `running` clears the planning presentation
- reset/cancel paths clear planning presentation state

Mirror the lightweight state transitions already used in `ChatPage.planner-completion.spec.ts`; do not attempt to fully mount `ChatPage.vue`.

**Step 2: Run the targeted ChatPage test**

Run:

```bash
cd frontend && bun run test:run tests/pages/ChatPage.planning-presentation.spec.ts
```

Expected: FAIL because `ChatPage.vue` does not track plan presentation state yet.

**Step 3: Implement the ChatPage state and lifecycle**

Update `frontend/src/pages/ChatPage.vue`:

- add state fields:
  - `planPresentationText`
  - `isPlanStreaming`
  - `planPresentationSource`
  - `lastPlanningProgressSignature`
- in `handleProgressEvent()`:
  - keep existing progress card behavior
  - append frontend-derived scaffold lines
  - ignore `received`
  - dedupe repeated planning heartbeat messages
  - stop mutating scaffold once streamed final markdown has started
- in `handleStreamEvent()`:
  - add `phase === 'planning'` branch
  - on first planning stream chunk, clear scaffold and switch to stream mode
  - append streamed markdown chunks
  - set `isPlanStreaming` from `is_final`
- in `handlePlanEvent()`:
  - keep existing plan/progress cleanup
  - do not clear `planPresentationText`
- in `handleToolEvent()`:
  - clear planning presentation on first real tool `calling` / `running`
- update all existing reset/cleanup sites that currently clear summary/thinking state so they also clear planning presentation state
- pass `planPresentationText` and `isPlanStreaming` into:
  - the bottom `TaskProgressBar`
  - the right-side `ToolPanel`

Implementation rules:

- do not invent a backend-only replace protocol such as `lane="replace"`
- do not remove or repurpose existing `thinkingText` behavior

**Step 4: Re-run the targeted ChatPage test**

Run:

```bash
cd frontend && bun run test:run tests/pages/ChatPage.planning-presentation.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.vue frontend/tests/pages/ChatPage.planning-presentation.spec.ts
git commit -m "feat(chat): add planning presentation lifecycle for live view"
```

---

### Task 4: Add the Right-Panel Planning Overlay and Header Behavior

**Files:**
- Modify: `frontend/src/components/ToolPanel.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue`
- Test: `frontend/tests/components/ToolPanel.spec.ts`
- Test: `frontend/tests/components/ToolPanelContent.spec.ts`

**Step 1: Add failing ToolPanel/ToolPanelContent tests**

Extend `frontend/tests/components/ToolPanel.spec.ts` to verify:

- `planPresentationText` is forwarded to `ToolPanelContent`
- `isPlanStreaming` is forwarded to `ToolPanelContent`

Extend `frontend/tests/components/ToolPanelContent.spec.ts` to verify:

- planning overlay renders when `planPresentationText` is present
- report overlay still has higher priority than planning overlay
- planning overlay uses `EditorContentView` with `filename="Plan.md"`
- planning header shows `"Creating plan..."` while streaming
- planning header shows `"Plan ready"` after final chunk
- replay/timeline guard hides planning overlay when user is inspecting older timeline steps

**Step 2: Run the targeted component tests**

Run:

```bash
cd frontend && bun run test:run tests/components/ToolPanel.spec.ts tests/components/ToolPanelContent.spec.ts
```

Expected: FAIL because the planning props and overlay do not exist yet.

**Step 3: Implement right-panel planning presentation**

Update `frontend/src/components/ToolPanel.vue`:

- add new props:
  - `planPresentationText`
  - `isPlanStreaming`
- forward both to `ToolPanelContent`

Update `frontend/src/components/ToolPanelContent.vue`:

- add the two planning props
- compute `showPlanPresentation` with the same replay-awareness used by the report overlay
- render ordering:
  1. report overlay
  2. planning overlay
  3. unified tool streaming
  4. normal tool/live/replay views
- render planning overlay via `EditorContentView`
- make header text/icon planning-aware using the shared streaming state
- reuse an existing Lucide icon such as `PencilLine`

Implementation rules:

- do not create a dedicated `PlanningPenIcon.vue`
- keep report behavior unchanged

**Step 4: Re-run the targeted component tests**

Run:

```bash
cd frontend && bun run test:run tests/components/ToolPanel.spec.ts tests/components/ToolPanelContent.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/ToolPanel.vue frontend/src/components/ToolPanelContent.vue frontend/tests/components/ToolPanel.spec.ts frontend/tests/components/ToolPanelContent.spec.ts
git commit -m "feat(panel): add planning overlay to live tool panel"
```

---

### Task 5: Wire Planning State Through TaskProgressBar and LiveMiniPreview

**Files:**
- Modify: `frontend/src/components/TaskProgressBar.vue`
- Modify: `frontend/src/components/LiveMiniPreview.vue`
- Test: `frontend/tests/components/TaskProgressBar.spec.ts`
- Test: `frontend/tests/components/LiveMiniPreview.spec.ts`

**Step 1: Add failing preview tests**

Extend `frontend/tests/components/TaskProgressBar.spec.ts` to verify:

- planning props are accepted and forwarded into both thumbnail instances

Extend `frontend/tests/components/LiveMiniPreview.spec.ts` to verify:

- planning preview renders when `planPresentationText` is present
- `"Creating plan..."` appears while `isPlanStreaming=true`
- `"Plan ready"` appears after final chunk
- summary/report preview still wins when both report and plan data are present

**Step 2: Run the targeted preview tests**

Run:

```bash
cd frontend && bun run test:run tests/components/TaskProgressBar.spec.ts tests/components/LiveMiniPreview.spec.ts
```

Expected: FAIL because those props and planning preview logic do not exist yet.

**Step 3: Implement collapsed-preview planning presentation**

Update `frontend/src/components/TaskProgressBar.vue`:

- add props:
  - `planPresentationText`
  - `isPlanStreaming`
- pass both props into the expanded and collapsed `LiveMiniPreview` instances
- thread the same props into its internal `useStreamingPresentationState()` call if that state is still used for thumbnail labels

Update `frontend/src/components/LiveMiniPreview.vue`:

- add props:
  - `planPresentationText`
  - `isPlanStreaming`
- pass both into `useStreamingPresentationState()`
- add `isPlanningPhase` handling to the template
- generalize preview text selection so:
  - report text wins first
  - plan text wins second
  - tool preview stays fallback
- reuse the existing mini markdown renderer for plan preview content

Implementation rules:

- do not fork a second markdown renderer just for plans
- do not regress final-report preview behavior

**Step 4: Re-run the targeted preview tests**

Run:

```bash
cd frontend && bun run test:run tests/components/TaskProgressBar.spec.ts tests/components/LiveMiniPreview.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/TaskProgressBar.vue frontend/src/components/LiveMiniPreview.vue frontend/tests/components/TaskProgressBar.spec.ts frontend/tests/components/LiveMiniPreview.spec.ts
git commit -m "feat(preview): show planning state in collapsed live previews"
```

---

### Task 6: Run Integration Verification and Final Checks

**Files:**
- Verify only

**Step 1: Run targeted backend coverage for the new planner behavior**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/unit/agents/test_planner.py tests/unit/agents/test_planner_plan_streaming.py -q
```

Expected: PASS.

**Step 2: Run targeted frontend coverage for all touched presentation paths**

Run:

```bash
cd frontend && bun run test:run \
  tests/composables/useStreamingPresentationState.spec.ts \
  tests/pages/ChatPage.planning-presentation.spec.ts \
  tests/components/ToolPanel.spec.ts \
  tests/components/ToolPanelContent.spec.ts \
  tests/components/TaskProgressBar.spec.ts \
  tests/components/LiveMiniPreview.spec.ts
```

Expected: PASS.

**Step 3: Run repo-standard checks**

Run:

```bash
cd frontend && bun run lint && bun run type-check
```

Run:

```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Expected: PASS.

**Step 4: Perform manual smoke verification**

Manual checks:

- submit a new prompt that requires planning
- confirm live view switches from idle browser frame to `Plan.md` scaffold
- confirm duplicate `"Generating plan..."` heartbeats do not create repeated lines
- confirm first streamed final-plan chunk replaces the scaffold
- confirm final plan stays visible after `PlanEvent`
- confirm first real tool start clears the plan overlay and returns to tool/live view
- confirm collapsed preview shows the same planning state when the right panel is closed

**Step 5: Final commit if verification required follow-up fixes**

```bash
git add backend/app/domain/services/agents/planner.py \
  backend/tests/unit/agents/test_planner_plan_streaming.py \
  frontend/src/constants/streamingPresentation.ts \
  frontend/src/composables/useStreamingPresentationState.ts \
  frontend/src/pages/ChatPage.vue \
  frontend/src/components/ToolPanel.vue \
  frontend/src/components/ToolPanelContent.vue \
  frontend/src/components/TaskProgressBar.vue \
  frontend/src/components/LiveMiniPreview.vue \
  frontend/tests/composables/useStreamingPresentationState.spec.ts \
  frontend/tests/pages/ChatPage.planning-presentation.spec.ts \
  frontend/tests/components/ToolPanel.spec.ts \
  frontend/tests/components/ToolPanelContent.spec.ts \
  frontend/tests/components/TaskProgressBar.spec.ts \
  frontend/tests/components/LiveMiniPreview.spec.ts
git commit -m "feat(live-view): stream plan presentation during planning"
```

If no follow-up fixes were needed after verification, skip this commit.
