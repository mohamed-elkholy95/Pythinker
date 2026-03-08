# Konva Canvas Agent Sync Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Turn the existing Konva canvas editor and agent live-view surfaces into one professional, session-aware design workspace that stays synchronized with backend canvas state and agent tool execution.

**Architecture:** Reuse the current editable artboard stack (`CanvasPage.vue` + `CanvasStage.vue` + `useCanvasEditor.ts`) and the current live agent viewer stack (`SandboxViewer.vue` + `KonvaLiveStage.vue`). Add a thin session-aware canvas sync contract between backend and frontend: backend emits authoritative, versioned canvas update events for agent mutations; frontend tracks the active canvas project for the current session and refreshes or patches the shared model only when the backend version advances. Keep the side-panel canvas view read-mostly and route deep editing to the dedicated canvas page instead of building a second full editor in the tool panel.

**Tech Stack:** Vue 3, TypeScript, vue-konva/Konva, Pinia/composables, FastAPI, Pydantic v2, Mongo/Beanie canvas persistence, SSE event stream, existing agent tool pipeline.

---

## Assumptions

1. This is a single-user plus AI-agent workspace, not a true multi-user collaborative editor.
2. The correct short-term target is “agent/manual session sync with professional UX”, not Figma-style OT/CRDT collaboration.
3. The existing Konva components should be unified and hardened, not replaced with a new canvas stack.
4. The current `canvas_update` SSE type is intended product behavior, even though the backend does not appear to emit it today.

If any of those assumptions are wrong, rewrite this plan before implementation.

---

## Current Repo Findings

1. The dedicated editor already exists in:
   - `frontend/src/pages/CanvasPage.vue`
   - `frontend/src/components/canvas/editor/CanvasStage.vue`
   - `frontend/src/composables/useCanvasEditor.ts`
   - `frontend/src/composables/useCanvasHistory.ts`

2. The live Konva viewer already exists in:
   - `frontend/src/components/SandboxViewer.vue`
   - `frontend/src/components/KonvaLiveStage.vue`
   - `frontend/src/composables/useKonvaScreencast.ts`
   - `frontend/src/composables/useAgentActionOverlay.ts`
   - `frontend/src/composables/useAgentCursor.ts`

3. The chat/tool panel already knows about canvas tools in:
   - `frontend/src/components/ToolPanelContent.vue`
   - `frontend/src/components/toolViews/CanvasLiveView.vue`
   - `frontend/src/components/toolViews/GenericContentView.vue`
   - `frontend/src/components/canvas/CanvasMiniPreview.vue`

4. Backend canvas persistence already supports `session_id` on the domain model, and the response model already returns it, but the public API still lacks a clean request-level session binding flow and a lookup-by-session endpoint:
   - `backend/app/domain/models/canvas.py`
   - `backend/app/interfaces/api/canvas_routes.py`
   - `backend/app/interfaces/schemas/canvas.py`
   - `backend/app/infrastructure/models/canvas_documents.py`
   - `backend/app/infrastructure/repositories/mongo_canvas_repository.py`

5. Agent-driven canvas tools already exist and are added into the main flow in:
   - `backend/app/domain/services/tools/canvas.py`
   - `backend/app/domain/services/flows/plan_act.py`

6. The frontend expects `canvas_update` SSE events:
   - `frontend/src/pages/ChatPage.vue`
   - `frontend/src/types/event.ts`

7. The backend defines `CanvasUpdateEvent`, but no clear emission path currently exists:
   - `backend/app/domain/models/event.py`

8. Current live canvas refresh behavior is coarse-grained:
   - `CanvasLiveView.vue` debounces and reloads the full project from REST.
   - There is no version-based guard, conflict state, or changed-element provenance in the UI.

---

## Approach Options

### Option A: Recommended
Use versioned session-linked canvas update events plus debounced authoritative fetches.

- Pros:
  - Reuses the existing REST project fetch path.
  - Keeps SSE payloads small and simple.
  - Avoids building a brittle patch engine in the first pass.
  - Cleanly supports agent/manual conflict handling.
- Cons:
  - Live canvas updates still refresh from the backend, not directly from streamed diffs.

### Option B: Full snapshot on every `canvas_update`

- Pros:
  - Simplest frontend application logic.
  - No second fetch required.
- Cons:
  - Heavy SSE payloads for large projects.
  - More expensive serialization on every tool call.

### Option C: Operational diff / CRDT-style sync

- Pros:
  - Best future path for true collaborative editing.
- Cons:
  - Too much complexity for the current product stage.
  - Requires conflict resolution, patch ordering, replay guarantees, and much broader test coverage.

**Recommendation:** Implement Option A now. Leave Option C explicitly out of scope.

---

## UX Target

The finished experience should feel like a serious design workspace, not a generic tool preview:

1. The chat-side canvas panel should show:
   - current project identity
   - live agent state
   - last canvas operation
   - element count and version
   - “Open Studio” CTA
   - a clear stale/conflict banner when agent updates arrive during manual editing

2. The full canvas page should feel like a design studio:
   - clean studio top bar with project title, sync badge, session link, agent/manual mode badge
   - artboard centered on a neutral matte, not floating on white
   - compact but professional left toolbar
   - structured right rail for properties, layers, and agent activity
   - visual highlight for newly agent-modified elements

3. Manual editing and agent editing must not silently overwrite each other.

---

## Task 1: Normalize the backend canvas/session contract

**Status:** Not Started

**Files:**
- Modify: `backend/app/interfaces/schemas/canvas.py`
- Modify: `backend/app/interfaces/api/canvas_routes.py`
- Modify: `backend/app/application/services/canvas_service.py`
- Modify: `backend/app/domain/repositories/canvas_repository.py`
- Modify: `backend/app/infrastructure/repositories/mongo_canvas_repository.py`
- Modify: `backend/app/infrastructure/models/canvas_documents.py`
- Modify: `frontend/src/api/canvas.ts`
- Modify: `frontend/src/types/canvas.ts`
- Create: `backend/tests/interfaces/api/test_canvas_routes.py`

**Step 1: Write failing backend API tests**

Add tests for:
1. optional `session_id` accepted by `CreateProjectRequest` and persisted on create
2. session-linked lookup of the active project for a chat session
3. session-aware ownership checks for the lookup endpoint

Run:

```bash
eval "$(conda shell.zsh hook)" && conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_canvas_routes.py -q
```

Expected: FAIL because the request schema does not yet accept `session_id`, and the route/repository path does not yet expose lookup-by-session.

**Step 2: Extend schema and route surface**

Implement:
1. `session_id` as an optional request field on project creation
2. a read endpoint that resolves the active canvas project for a given session
3. response fields for `version` and `updated_at` if not already passed through cleanly

**Step 3: Extend repository support**

Implement a repository lookup for the most recent or active canvas project by `session_id`, add `find_by_session_id` to the domain repository protocol, and add the Mongo index if needed.

**Step 4: Extend frontend client types**

Update `frontend/src/api/canvas.ts` and `frontend/src/types/canvas.ts` so the frontend can:
1. create a project attached to a session
2. resolve the session’s active canvas project
3. reason about server version and sync metadata

**Step 5: Re-run targeted tests**

Run:

```bash
eval "$(conda shell.zsh hook)" && conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_canvas_routes.py -q
cd /home/mac/Desktop/Pythinker-main/frontend && bun run type-check
```

**Step 6: Commit**

```bash
git add backend/app/interfaces/schemas/canvas.py backend/app/interfaces/api/canvas_routes.py backend/app/application/services/canvas_service.py backend/app/domain/repositories/canvas_repository.py backend/app/infrastructure/repositories/mongo_canvas_repository.py backend/app/infrastructure/models/canvas_documents.py backend/tests/interfaces/api/test_canvas_routes.py frontend/src/api/canvas.ts frontend/src/types/canvas.ts
git commit -m "feat: add session-aware canvas contract"
```

---

## Task 2: Emit real canvas update events from agent canvas mutations

**Status:** Not Started

**Files:**
- Modify: `backend/app/domain/models/event.py`
- Modify: `backend/app/domain/services/tools/canvas.py`
- Modify: `backend/app/domain/services/tool_content_handlers/canvas.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Create: `backend/tests/domain/services/test_agent_task_runner_canvas_events.py`
- Modify: `backend/tests/domain/services/test_code_executor_artifact_sync.py`

**Step 1: Write failing event-emission tests**

Add tests proving that:
1. mutating canvas `ToolEvent`s cause the execution layer to emit `CanvasUpdateEvent`
2. emitted payload includes `project_id`, `session_id`, `operation`, `project_name`, `element_count`, and `version`
3. non-mutating reads do not emit unnecessary update events

Run:

```bash
eval "$(conda shell.zsh hook)" && conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_task_runner_canvas_events.py -q
```

Expected: FAIL because the tool execution/content-handler path does not currently enqueue any `CanvasUpdateEvent`.

**Step 2: Extend `CanvasUpdateEvent` for authoritative sync**

Add the minimum fields the frontend actually needs:
1. `session_id`
2. `version`
3. optional `changed_element_ids`
4. optional `source` (`agent`, `manual`, `system`) if useful for UI badges

Do not add full project snapshots to the event in this phase.

**Step 3: Emit from the existing ToolEvent/content-handler/execution path**

Keep the current tool architecture intact:
1. let `CanvasTool` continue returning `ToolResult`
2. enrich canvas metadata through the existing canvas tool-content path
3. emit one `CanvasUpdateEvent` from `AgentTaskRunner._handle_tool_event()` after the canvas content handler has run and only for successful mutating canvas operations

If the event needs richer metadata than current `ToolResult.data` provides, extend the returned canvas tool payload, but do not add an out-of-band `emit_event` callback to `CanvasTool`.

**Step 4: Keep existing tool content enrichment**

Do not remove the existing `CanvasToolContent` flow. The new event stream should complement it, not replace it.

**Step 5: Re-run targeted backend tests**

Run:

```bash
eval "$(conda shell.zsh hook)" && conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_task_runner_canvas_events.py tests/domain/services/test_code_executor_artifact_sync.py -q
```

**Step 6: Commit**

```bash
git add backend/app/domain/models/event.py backend/app/domain/services/tools/canvas.py backend/app/domain/services/tool_content_handlers/canvas.py backend/app/domain/services/agent_task_runner.py backend/tests/domain/services/test_agent_task_runner_canvas_events.py backend/tests/domain/services/test_code_executor_artifact_sync.py
git commit -m "feat: emit canvas update events for agent mutations"
```

---

## Task 3: Add a shared frontend canvas live-sync layer

**Status:** Not Started

**Files:**
- Create: `frontend/src/composables/useCanvasLiveSync.ts`
- Modify: `frontend/src/components/toolViews/CanvasLiveView.vue`
- Modify: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue`
- Modify: `frontend/src/api/canvas.ts`
- Create: `frontend/tests/composables/useCanvasLiveSync.spec.ts`
- Create: `frontend/tests/components/CanvasLiveView.spec.ts`
- Modify: `frontend/tests/components/ToolPanelContent.spec.ts`

**Step 1: Write failing frontend tests**

Add tests for:
1. `CanvasLiveView` only refreshing when the backend version advances
2. debounced refresh coalescing multiple agent events
3. `ToolPanelContent` resolving canvas state from event-driven project metadata
4. dirty editor sessions queuing remote changes instead of silently replacing local state

Run:

```bash
cd frontend && bun run test:run -- CanvasLiveView ToolPanelContent useCanvasLiveSync
```

Expected: FAIL because the current live path only knows `project_id` and always refetches wholesale.

**Step 2: Build `useCanvasLiveSync.ts`**

This composable should:
1. accept `sessionId`, `projectId`, and incoming canvas update metadata
2. track last seen server `version`
3. debounce fetches
4. expose `isStale`, `pendingRemoteVersion`, `lastOperation`, and `refreshNow`

Do not create a large global store unless the composable proves insufficient.

**Step 3: Wire the chat/session layer**

`ChatPage.vue` should:
1. consume real `canvas_update` events
2. retain `activeCanvasProjectId`
3. keep the latest version/operation metadata available to the tool panel

`ToolPanelContent.vue` should:
1. resolve canvas view state from either tool content or `canvas_update`
2. trigger refresh only when the canvas tab is visible or newly opened

**Step 4: Upgrade `CanvasLiveView.vue`**

Replace the current “dumb debounced reload” path with:
1. version-aware refresh
2. stale indicator
3. last operation label
4. optional “Apply latest agent changes” CTA when manual edits are dirty

**Step 5: Re-run frontend tests**

Run:

```bash
cd frontend && bun run test:run -- CanvasLiveView ToolPanelContent useCanvasLiveSync
cd frontend && bun run type-check
```

**Step 6: Commit**

```bash
git add frontend/src/composables/useCanvasLiveSync.ts frontend/src/components/toolViews/CanvasLiveView.vue frontend/src/pages/ChatPage.vue frontend/src/components/ToolPanelContent.vue frontend/src/api/canvas.ts frontend/tests/composables/useCanvasLiveSync.spec.ts frontend/tests/components/CanvasLiveView.spec.ts frontend/tests/components/ToolPanelContent.spec.ts
git commit -m "feat: add versioned frontend canvas live sync"
```

---

## Task 4: Professionalize the canvas workspace UI without duplicating the editor

**Status:** Not Started

**Files:**
- Modify: `frontend/src/pages/CanvasPage.vue`
- Modify: `frontend/src/components/toolViews/CanvasLiveView.vue`
- Modify: `frontend/src/components/canvas/editor/CanvasToolbar.vue`
- Modify: `frontend/src/components/canvas/editor/CanvasLayerPanel.vue`
- Modify: `frontend/src/components/canvas/editor/CanvasPropertyPanel.vue`
- Modify: `frontend/src/components/canvas/editor/CanvasAIPanel.vue`
- Create: `frontend/src/components/canvas/CanvasWorkspaceHeader.vue`
- Create: `frontend/src/components/canvas/CanvasSyncBanner.vue`
- Create: `frontend/src/components/canvas/CanvasActivityRail.vue`
- Create: `frontend/tests/components/CanvasWorkspaceHeader.spec.ts`
- Create: `frontend/tests/components/CanvasSyncBanner.spec.ts`
- Create: `frontend/tests/components/CanvasActivityRail.spec.ts`

**Step 1: Design and lock the visual hierarchy**

Implement a consistent studio hierarchy:
1. studio header
2. artboard matte
3. left tool rail
4. right inspector rail
5. activity/status surfaces

The side-panel live view must stay compact; the full editor gets the richer shell.

**Step 2: Create a reusable workspace header**

`CanvasWorkspaceHeader.vue` should support:
1. project name
2. sync badge
3. agent/manual mode badge
4. linked session badge
5. version text
6. primary CTA (`Open Studio`, `Return to Chat`, `Export`)

**Step 3: Improve the live panel**

Replace the generic “Agent is designing...” header with:
1. last operation
2. live/stale/conflict state
3. project name
4. version + element count
5. explicit open-editor action

**Step 4: Improve the full editor shell**

On `CanvasPage.vue`:
1. put the artboard on a neutral studio matte
2. tighten spacing and align control grouping
3. collapse secondary inspector content on smaller widths
4. reserve an activity rail for agent changes and sync state

**Step 5: Re-run focused frontend tests**

Run:

```bash
cd frontend && bun run test:run -- CanvasWorkspaceHeader CanvasSyncBanner CanvasActivityRail CanvasLiveView
cd frontend && bun run lint:check
```

**Step 6: Commit**

```bash
git add frontend/src/pages/CanvasPage.vue frontend/src/components/toolViews/CanvasLiveView.vue frontend/src/components/canvas/editor/CanvasToolbar.vue frontend/src/components/canvas/editor/CanvasLayerPanel.vue frontend/src/components/canvas/editor/CanvasPropertyPanel.vue frontend/src/components/canvas/editor/CanvasAIPanel.vue frontend/src/components/canvas/CanvasWorkspaceHeader.vue frontend/src/components/canvas/CanvasSyncBanner.vue frontend/src/components/canvas/CanvasActivityRail.vue frontend/tests/components/CanvasWorkspaceHeader.spec.ts frontend/tests/components/CanvasSyncBanner.spec.ts frontend/tests/components/CanvasActivityRail.spec.ts
git commit -m "feat: professionalize canvas workspace shell"
```

---

## Task 5: Make agent/manual interaction safe and understandable

**Status:** Not Started

**Files:**
- Modify: `frontend/src/composables/useCanvasEditor.ts`
- Modify: `frontend/src/composables/useCanvasHistory.ts`
- Modify: `frontend/src/pages/CanvasPage.vue`
- Modify: `frontend/src/components/toolViews/CanvasLiveView.vue`
- Modify: `frontend/src/components/canvas/editor/CanvasStage.vue`
- Create: `frontend/tests/components/CanvasPage.sync.spec.ts`
- Create: `frontend/tests/composables/useCanvasEditor.sync.spec.ts`

**Step 1: Write failing sync/conflict tests**

Add tests for:
1. agent update arriving while editor is clean → auto-refresh
2. agent update arriving while editor is dirty → queue remote version and show banner
3. accepting remote version replaces local state and clears stale queue
4. dismissing remote update leaves editor dirty but marks view stale

Run:

```bash
cd frontend && bun run test:run -- CanvasPage.sync useCanvasEditor.sync
```

Expected: FAIL because the current editor has no remote conflict model.

**Step 2: Extend editor state with remote-sync metadata**

Add only the minimum state needed:
1. `serverVersion`
2. `pendingRemoteVersion`
3. `hasRemoteConflict`
4. `lastRemoteOperation`

Do not build a generalized collaboration engine.

**Step 3: Add visible conflict and follow-mode UX**

`CanvasPage.vue` and `CanvasLiveView.vue` should support:
1. “Follow agent” in read-only/live mode
2. “Agent updated this canvas” banner in manual mode
3. “Apply latest” and “Keep my draft” actions

**Step 4: Add changed-element highlighting**

Use transient highlight rings or selection flash in `CanvasStage.vue` when the backend reports changed element IDs.

Keep this subtle; do not introduce constant motion.

**Step 5: Re-run focused tests**

Run:

```bash
cd frontend && bun run test:run -- CanvasPage.sync useCanvasEditor.sync CanvasLiveView
cd frontend && bun run type-check
```

**Step 6: Commit**

```bash
git add frontend/src/composables/useCanvasEditor.ts frontend/src/composables/useCanvasHistory.ts frontend/src/pages/CanvasPage.vue frontend/src/components/toolViews/CanvasLiveView.vue frontend/src/components/canvas/editor/CanvasStage.vue frontend/tests/components/CanvasPage.sync.spec.ts frontend/tests/composables/useCanvasEditor.sync.spec.ts
git commit -m "feat: add safe agent manual canvas sync UX"
```

---

## Task 6: Apply Konva-specific performance and interaction hardening

**Status:** Not Started

**Files:**
- Modify: `frontend/src/components/canvas/editor/CanvasStage.vue`
- Modify: `frontend/src/components/canvas/KonvaCanvas.vue`
- Modify: `frontend/src/components/KonvaLiveStage.vue`
- Modify: `frontend/src/composables/useKonvaScreencast.ts`
- Create: `frontend/tests/components/CanvasStage.performance.spec.ts`

**Context7 basis to apply during implementation:**
1. keep non-interactive layers at `listening: false`
2. use `getNode()` refs for imperative high-frequency paths
3. use `batchDraw()` instead of full redraw churn
4. use a dedicated drag layer when drag performance needs isolation
5. cache only genuinely expensive shapes/images

**Step 1: Write failing or missing coverage**

Add tests for:
1. non-interactive layers staying non-listening
2. drag behavior not mutating transform state incorrectly
3. stage resize and responsive fit behavior

**Step 2: Harden `CanvasStage.vue`**

Implement only targeted improvements:
1. keep background and decorative overlays non-listening
2. add a drag layer if transform/drag performance justifies it
3. prevent unnecessary image churn
4. keep transformer attachment explicit and testable

**Step 3: Keep the live viewer path consistent**

Do not rewrite `KonvaLiveStage.vue`; only align shared patterns and guardrails where the editor and live viewer overlap.

`KonvaCanvas.vue` is not the primary editor renderer. Treat it as the shared responsive stage wrapper currently used by auxiliary Konva surfaces such as the timeline path, and only touch it if a shared sizing/input concern belongs there.

**Step 4: Re-run focused tests**

Run:

```bash
cd frontend && bun run test:run -- CanvasStage.performance ToolPanelContent
cd frontend && bun run lint:check && bun run type-check
```

**Step 5: Commit**

```bash
git add frontend/src/components/canvas/editor/CanvasStage.vue frontend/src/components/canvas/KonvaCanvas.vue frontend/src/components/KonvaLiveStage.vue frontend/src/composables/useKonvaScreencast.ts frontend/tests/components/CanvasStage.performance.spec.ts
git commit -m "perf: harden Konva canvas interactions"
```

---

## Task 7: Final integration verification and documentation

**Status:** Not Started

**Files:**
- Modify: `docs/plans/2026-03-08-konva-canvas-agent-sync-workspace.md`
- Create if needed: `backend/tests/interfaces/api/test_canvas_routes.py`
- Create if needed: `frontend/tests/components/CanvasLiveView.spec.ts`
- Create if needed: `frontend/tests/composables/useCanvasLiveSync.spec.ts`
- Create if needed: `frontend/tests/components/CanvasSyncBanner.spec.ts`
- Create if needed: `frontend/tests/components/CanvasActivityRail.spec.ts`
- Use existing: `backend/tests/application/services/test_canvas_service_concurrency.py`
- Create if needed: `backend/tests/domain/services/test_agent_task_runner_canvas_events.py`

**Step 1: Run targeted backend suite**

```bash
eval "$(conda shell.zsh hook)" && conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_canvas_routes.py tests/domain/services/test_agent_task_runner_canvas_events.py tests/application/services/test_canvas_service_concurrency.py -q
```

**Step 2: Run full frontend verification**

```bash
cd frontend && bun run lint:check && bun run type-check && bun run test:run
```

**Step 3: Run backend quality gates**

```bash
eval "$(conda shell.zsh hook)" && conda activate pythinker && cd backend && ruff check . && ruff format --check .
```

**Step 4: Run full backend tests if targeted suites are green**

```bash
eval "$(conda shell.zsh hook)" && conda activate pythinker && cd backend && pytest tests/
```

**Step 5: Update this plan with factual status**

Mark each task as:
1. `Completed`
2. `In Progress`
3. `Not Started`

No task may be marked completed without fresh verification evidence.

**Step 6: Final commit**

```bash
git add docs/plans/2026-03-08-konva-canvas-agent-sync-workspace.md
git commit -m "docs: finalize Konva canvas agent sync plan"
```

---

## Out of Scope

1. True multi-user canvas collaboration
2. CRDT/OT conflict resolution
3. Replacing Konva with another rendering stack
4. Rebuilding the live agent viewer from scratch
5. Full Canva/Figma parity feature expansion

---

## Acceptance Criteria

1. Agent-created canvas projects are session-linked and discoverable from the chat session.
2. Backend emits real `canvas_update` events for successful mutating canvas tool calls.
3. The frontend canvas live view refreshes only on authoritative backend version changes.
4. Manual editing and agent editing have visible conflict handling rather than silent overwrites.
5. The full canvas page looks and behaves like a professional design workspace.
6. Konva performance follows library best practices already reflected in the live viewer path.
7. Frontend and backend tests cover the session contract, event contract, and conflict UX.

---

## Notes For Implementation

1. Prefer a thin sync layer over a new global state system.
2. Reuse `CanvasStage.vue`; do not create a second editor renderer.
3. Reuse the existing imperative Konva pattern (`getNode()` + `batchDraw()`) only where update frequency justifies it.
4. Preserve the existing tool-content previews; enrich them with real sync metadata instead of replacing them.
5. If the product later needs true collaboration, create a separate design and plan rather than stretching this one.
