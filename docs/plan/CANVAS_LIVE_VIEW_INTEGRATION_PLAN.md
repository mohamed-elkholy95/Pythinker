# Canvas Editor Live View Integration — Full Enhancement Plan

**Created:** 2026-02-24
**Scope:** Embed the Konva.js canvas editor inside the live-view panel (same design as `TakeOverView`) so users and the agent can open, interact with, and edit canvas projects inline — without leaving the chat session.
**Status:** Planning

---

## 1. Executive Summary

Pythinker already has a **complete, production-grade canvas system** (Konva.js + Vue 3 + FastAPI DDD).
However the editor lives on a standalone page (`/chat/canvas/:projectId`) that is completely isolated from the agent session flow.

This plan closes that gap by embedding the canvas editor directly **inside the live-view slot** — the same mechanism used by the browser takeover UI (`TakeOverView.vue`).

### What this enables

| Trigger | Behavior |
|---------|----------|
| Agent tool call `canvas_create_project` / `canvas_add_element` | Canvas editor panel auto-opens in live view with the active project loaded |
| User types "create a design" / "open canvas" in chat | Agent calls canvas tool → live view switches to canvas editor |
| User manually clicks a "Canvas" button in the tool panel | Canvas editor opens for the active session project |
| Agent finishes editing (canvas tool returns) | Live view switches back to browser screencast, canvas minimizes |

---

## 2. Current State Analysis

### 2.1 Existing canvas infrastructure (all production-ready)

**Frontend:**
- `frontend/src/pages/CanvasPage.vue` — standalone full-featured editor
- `frontend/src/components/canvas/editor/CanvasStage.vue` — Konva stage with full interaction
- `frontend/src/composables/useCanvasEditor.ts` — state machine (load, CRUD, selection, zoom/pan, auto-save)
- `frontend/src/composables/useCanvasHistory.ts` — undo/redo
- `frontend/src/composables/useCanvasExport.ts` — PNG/JSON export
- `frontend/src/api/canvas.ts` — all REST endpoints

**Backend:**
- `backend/app/domain/models/canvas.py` — DDD models
- `backend/app/domain/services/tools/canvas.py` — agent canvas tool
- `backend/app/application/services/canvas_service.py` — orchestration with async locks
- `backend/app/infrastructure/models/canvas_documents.py` — MongoDB persistence
- `backend/app/interfaces/api/canvas_routes.py` — REST endpoints
- `backend/app/interfaces/schemas/canvas.py` — Pydantic v2 schemas

### 2.2 Live view slot architecture (takeover pattern)

`TakeOverView.vue` uses a **CustomEvent bus** + a `fixed z-[60]` overlay that replaces the live view:

```
window.dispatchEvent(new CustomEvent('takeover', {
  detail: { sessionId: '...', active: true }
}))
```

The component listens for this event, becomes visible (`shouldShow` computed), and renders the live browser viewer full-screen. **This exact pattern is the architectural target for canvas.**

### 2.3 Gaps

1. **No `CanvasTakeOverView.vue`** — canvas editor isn't surfaced in the live view slot.
2. **No canvas SSE events** — agent canvas tool results don't trigger live view to switch.
3. **No session-scoped canvas project link** — sessions don't know their active canvas project.
4. **No canvas view mode in `BrowserToolView`** — tool panel doesn't offer "Canvas" view tab.
5. **No agent intent detection** — frontend doesn't listen for canvas tool events to auto-open.

---

## 3. Design Principles

1. **Same design language as TakeOverView** — address bar replaced by canvas toolbar, same z-index, same overlay pattern.
2. **CustomEvent bus** — zero new dependencies; reuse the existing `window.dispatchEvent` pattern.
3. **Session-scoped project** — one active canvas project per session; stored in session state.
4. **Agent-driven OR user-driven** — canvas opens via agent tool call SSE event OR user click.
5. **Graceful coexistence** — canvas and browser takeover must not conflict; canvas takes z-[61] (above takeover z-[60]).
6. **Reuse, don't duplicate** — embed `CanvasStage`, `CanvasToolbar`, `CanvasPropertyPanel` etc. directly inside the new component; don't rewrite them.

---

## 4. Target Architecture

```
┌──────────────────────────────────────────────────────────┐
│  ChatPage / ToolPanelContent                             │
│  ├─ BrowserToolView  (screen / output tabs)              │
│  │  └─ [Canvas] tab (new) ─────────────────┐            │
│  └─ CanvasTakeOverView (fixed overlay z-61) │            │
│     ├─ Compact topbar (back, project name,  │            │
│     │  save status, undo/redo, export, Exit)│            │
│     ├─ CanvasToolbar (left, vertical)       │            │
│     ├─ CanvasStage (center, full height)    │            │
│     ├─ CanvasPropertyPanel (right)          │            │
│     └─ CanvasLayerPanel (right, collapsible)│            │
└─────────────────────────────────────────────────────────-┘
```

### 4.1 Event bus contract

```typescript
// Open canvas editor for a session+project
window.dispatchEvent(new CustomEvent('canvas-editor', {
  detail: { sessionId: string, projectId: string, active: boolean }
}))
```

### 4.2 Session–project linkage

Add `active_canvas_project_id: str | None` field to `Session` domain model and `SessionDocument`.
When agent calls `canvas_create_project`, the canvas tool stores the project id in session state.
Frontend reads this via SSE `tool` event or via a new `GET /sessions/{id}/canvas-project` endpoint.

### 4.3 Canvas SSE event flow

```
Agent calls canvas_create_project()
  → CanvasService.create_project()
  → SSE event: { type: "canvas", action: "project_created", project_id: "..." }
  → Frontend receives event in useAgentEvents()
  → Dispatches CustomEvent('canvas-editor', { active: true, projectId })
  → CanvasTakeOverView becomes visible
```

---

## 5. Implementation Phases

---

### Phase 1 — CanvasTakeOverView Component (P0, Frontend)

**Goal:** Create the canvas overlay component mirroring `TakeOverView.vue`.

**New file:** `frontend/src/components/CanvasTakeOverView.vue`

**Design spec:**
- `fixed inset-0 z-[61]` — above browser takeover z-[60], below any system modals
- **Topbar** (44px, same height as `TakeOverView` address bar):
  - Left: `ArrowLeft` back button (closes canvas, returns to live view) + editable project name + save status badge
  - Center: Tool mode chips: Select / Rectangle / Ellipse / Text / Image / Pen / Line / Hand (replaces URL bar)
  - Right: Undo / Redo / Save / Export / `Exit Canvas` button (same style as `Exit Takeover`)
- **Body** (flex-1): `CanvasStage` fills center, `CanvasPropertyPanel` + `CanvasLayerPanel` on right (260px), collapsible via toggle button
- **Zoom controls**: `CanvasZoomControls` floating bottom-right (same as `CanvasPage`)
- **Onboarding tooltip**: first-time overlay explaining AI + user co-editing (same pattern as takeover onboarding)
- **Exit behavior**: dispatches `canvas-editor` event with `active: false`; no dialog needed (unlike takeover — canvas has auto-save)

**Composable integration:**
- Uses `useCanvasEditor()` (instance-scoped, no shared state leak)
- Uses `useCanvasHistory()` for undo/redo
- Uses `useCanvasExport()` for PNG/JSON export
- Listens for `CustomEvent('canvas-editor', ...)` via `window.addEventListener`

**Event bus listener:**
```typescript
const handleCanvasEditorEvent = (event: Event) => {
  const { active, sessionId, projectId } = (event as CustomEvent).detail
  canvasActive.value = active
  if (active && projectId) {
    currentProjectId.value = projectId
    loadProject(projectId)
  }
}
onMounted(() => window.addEventListener('canvas-editor', handleCanvasEditorEvent))
onBeforeUnmount(() => window.removeEventListener('canvas-editor', handleCanvasEditorEvent))
```

**Checklist:**
- [ ] `CanvasTakeOverView.vue` created in `frontend/src/components/`
- [ ] Registered in `ChatPage.vue` (or the layout that contains `TakeOverView`)
- [ ] Same CSS variable usage as `TakeOverView` (no hardcoded colors)
- [ ] Dark mode compatible (all `var(--*)` tokens)
- [ ] Keyboard shortcut parity with `CanvasPage` (Ctrl+Z, Ctrl+S, Delete, Escape)

---

### Phase 2 — Canvas Tab in BrowserToolView (P0, Frontend)

**Goal:** Add a third tab "Canvas" in `BrowserToolView.vue` alongside "Screen" and "Output".

**File:** `frontend/src/components/toolViews/BrowserToolView.vue`

**Changes:**
1. Add `'canvas'` to the `viewMode` type union: `'screen' | 'output' | 'canvas'`
2. Add Canvas tab button in the view mode toggle strip (use `Paintbrush` icon from lucide)
3. Add canvas view panel content: a `CanvasMiniPreview` thumbnail grid listing session's canvas projects, with a "Open Full Editor" button per project that dispatches `CustomEvent('canvas-editor', ...)`
4. Add a "New Canvas" button when no projects exist yet

**Canvas tab layout:**
```
┌─────────────────────────────────────────┐
│ [Screen] [Output] [Canvas ✦]            │  ← tab strip
├─────────────────────────────────────────┤
│  My Designs                      [+ New]│
│  ┌──────────┐  ┌──────────┐            │
│  │ thumbnail│  │ thumbnail│            │
│  │          │  │          │            │
│  │ "Logo v1"│  │"Mockup"  │            │
│  │ [Open]   │  │[Open]    │            │
│  └──────────┘  └──────────┘            │
└─────────────────────────────────────────┘
```

**Checklist:**
- [ ] Tab added with `Paintbrush` icon and "Canvas" label
- [ ] `CanvasMiniPreview` shown in grid (2-column)
- [ ] "Open" button dispatches `canvas-editor` event
- [ ] "New Canvas" button calls `createProject()` then dispatches event
- [ ] Canvas project list fetched from `GET /canvas/projects` (reuse `canvas.ts` API)

---

### Phase 3 — Session–Canvas Project Linkage (P1, Backend)

**Goal:** Sessions track their active canvas project so agent actions auto-open the editor.

**Backend changes:**

#### 3a. Domain model — `backend/app/domain/models/session.py`
```python
# Add to Session model
active_canvas_project_id: str | None = None
```

#### 3b. Document — `backend/app/infrastructure/models/documents.py`
```python
# Add to SessionDocument
active_canvas_project_id: str | None = None
```

#### 3c. Canvas tool — `backend/app/domain/services/tools/canvas.py`
After `canvas_create_project()` succeeds, persist the project id to session:
```python
# After create_project() call
await self._session_service.set_active_canvas_project(
    session_id=self._session_id,
    project_id=project.id
)
```

#### 3d. New API endpoint — `backend/app/interfaces/api/session_routes.py`
```
GET /sessions/{session_id}/canvas-project
→ { "project_id": "..." | null }
```

#### 3e. Session lifecycle service — `backend/app/application/services/session_lifecycle_service.py`
```python
async def set_active_canvas_project(self, session_id: str, project_id: str) -> None: ...
async def get_active_canvas_project(self, session_id: str) -> str | None: ...
```

**Checklist:**
- [ ] `active_canvas_project_id` added to domain model + document
- [ ] Canvas tool persists project id on creation
- [ ] `GET /sessions/{id}/canvas-project` endpoint added
- [ ] Frontend `api/agent.ts` — add `getSessionCanvasProject(sessionId)`

---

### Phase 4 — Canvas SSE Events (P1, Backend + Frontend)

**Goal:** When the agent performs canvas operations, the frontend automatically opens/updates the canvas editor.

#### 4a. New SSE event type

**File:** `backend/app/interfaces/schemas/event.py` (and/or domain event model)

```python
class CanvasEvent(BaseModel):
    type: Literal["canvas"] = "canvas"
    action: Literal["project_created", "project_updated", "element_added", "element_modified"]
    project_id: str
    element_id: str | None = None
    project_name: str | None = None
```

#### 4b. Emit from canvas tool

**File:** `backend/app/domain/services/tools/canvas.py`

After each canvas operation, emit an SSE event to the session:
```python
await self._event_emitter.emit(CanvasEvent(
    action="project_created",
    project_id=project.id,
    project_name=project.name,
))
```

#### 4c. Frontend event handler

**File:** `frontend/src/composables/useAgentEvents.ts` (or equivalent SSE handler)

```typescript
case 'canvas':
  if (event.action === 'project_created' || event.action === 'project_updated') {
    window.dispatchEvent(new CustomEvent('canvas-editor', {
      detail: {
        sessionId: currentSessionId,
        projectId: event.project_id,
        active: true
      }
    }))
  }
  break
```

**Checklist:**
- [ ] `CanvasEvent` schema added to event types
- [ ] Canvas tool emits events after each operation
- [ ] Frontend SSE handler dispatches `canvas-editor` CustomEvent
- [ ] `CanvasTakeOverView` auto-loads updated project when it receives a new `project_id`
- [ ] Canvas editor refreshes elements when SSE `project_updated` arrives while open

---

### Phase 5 — Agent Canvas Tool Enhancements (P1, Backend)

**Goal:** Make agent canvas tool session-aware and emit typed events.

**File:** `backend/app/domain/services/tools/canvas.py`

**Enhancements:**

1. **Auto-open signal**: canvas tool response metadata includes `{ "open_canvas": true, "project_id": "..." }` so even non-SSE paths (polling) can trigger the UI.

2. **Draw-tool — freehand path input**: Add `canvas_draw_path(points: list[tuple[float, float]], stroke_color, stroke_width)` for freehand drawing — extends existing `line`/`path` element type.

3. **Page management tools**:
   - `canvas_add_page(name, width, height, background)` — add artboard
   - `canvas_switch_page(page_index)` — set active page

4. **Batch operations**: Accept list of operations in `canvas_modify_elements` to reduce round-trips for multi-element updates.

5. **Export tool**: `canvas_export_png(project_id)` — returns base64 PNG; agent can embed in its response.

**Checklist:**
- [ ] `open_canvas` metadata in tool responses
- [ ] `canvas_draw_path()` method added
- [ ] `canvas_add_page()` / `canvas_switch_page()` methods added
- [ ] `canvas_export_png()` method added
- [ ] All new methods registered in tool registry

---

### Phase 6 — AI Panel Enhancements (P2, Frontend + Backend)

**Goal:** Enhance `CanvasAIPanel.vue` with agent-driven generation from within the canvas editor.

**Enhancements:**

1. **Chat with canvas**: Mini chat input inside the canvas editor panel. User types "add a blue rounded button at top right" → sent to agent as a tool-execution request → agent calls `canvas_add_element()` → SSE triggers canvas refresh.

2. **Style presets**: Pre-built style palettes (Modern, Material, Flat, Glassmorphism) applied via AI edit API.

3. **Smart resize**: AI suggests optimal dimensions based on content (social media sizes, print formats, screen sizes).

4. **Agent awareness indicator**: When agent is actively editing the canvas, show a pulsing indicator ("Agent is editing…") similar to the typing indicator in chat.

**Checklist:**
- [ ] Mini chat input in `CanvasAIPanel`
- [ ] Agent-active pulsing indicator
- [ ] Style preset buttons
- [ ] Smart resize presets (Instagram 1:1, Twitter 16:9, A4, 1920×1080)

---

### Phase 7 — Canvas Collaboration Signals (P2)

**Goal:** Agent and user can edit the canvas concurrently without conflicts.

**Design:**
- Use existing `_project_locks` in `CanvasService` (already implemented as per-project `asyncio.Lock`)
- Frontend shows "Agent is editing…" pill when lock is held by agent
- User edits are queued and merged after agent releases lock
- Optimistic updates on frontend with rollback on conflict

**Checklist:**
- [ ] Lock state exposed via `GET /canvas/projects/{id}/lock-status` endpoint
- [ ] Frontend polls (or SSE push) for lock status
- [ ] Visual indicator when agent holds lock
- [ ] Optimistic update + rollback on user edits

---

## 6. File Change Map

### New files

| File | Purpose |
|------|---------|
| `frontend/src/components/CanvasTakeOverView.vue` | Canvas editor live view overlay |

### Modified files

| File | Change |
|------|--------|
| `frontend/src/components/toolViews/BrowserToolView.vue` | Add Canvas tab (Phase 2) |
| `frontend/src/components/ToolPanelContent.vue` | Register `CanvasTakeOverView`, add canvas open handler |
| `frontend/src/api/agent.ts` | Add `getSessionCanvasProject()` |
| `frontend/src/composables/useAgentEvents.ts` | Handle `canvas` SSE event type |
| `backend/app/domain/models/session.py` | Add `active_canvas_project_id` field |
| `backend/app/infrastructure/models/documents.py` | Add `active_canvas_project_id` to `SessionDocument` |
| `backend/app/domain/services/tools/canvas.py` | Session linkage + SSE events + new tools |
| `backend/app/application/services/session_lifecycle_service.py` | Canvas project getter/setter |
| `backend/app/interfaces/api/session_routes.py` | `GET /sessions/{id}/canvas-project` |
| `backend/app/interfaces/schemas/event.py` | `CanvasEvent` schema |

---

## 7. UX Flow Diagrams

### 7.1 Agent-triggered canvas open

```
User: "Create a landing page design"
  ↓
Agent calls canvas_create_project("Landing Page")
  ↓
Backend: creates project, saves active_canvas_project_id to session
Backend: emits SSE { type: "canvas", action: "project_created", project_id: "abc" }
  ↓
Frontend useAgentEvents receives canvas SSE
  ↓
Frontend dispatches CustomEvent('canvas-editor', { active: true, projectId: "abc" })
  ↓
CanvasTakeOverView becomes visible (z-[61], full screen)
  ↓
Agent continues calling canvas_add_element() calls
  ↓
Each call: SSE project_updated → canvas editor auto-refreshes
  ↓
Agent done → canvas stays open for user to refine
```

### 7.2 User-triggered canvas open

```
User clicks [Canvas] tab in BrowserToolView
  ↓
Canvas project list shown (from GET /canvas/projects)
  ↓
User clicks [Open] on a project thumbnail
  ↓
CustomEvent('canvas-editor', { active: true, projectId }) dispatched
  ↓
CanvasTakeOverView opens
  ↓
User edits canvas (drag, resize, add elements)
  ↓
Auto-save every 3s (useCanvasEditor auto-save)
  ↓
User clicks [Exit Canvas] button
  ↓
CustomEvent('canvas-editor', { active: false })
  ↓
Live view returns to browser screencast
```

### 7.3 Canvas + Browser Takeover coexistence

```
z-index stack:
  [61] CanvasTakeOverView   ← canvas editor
  [60] TakeOverView          ← browser takeover
  [50] ToolPanelContent      ← live view panel
  [40] ChatPage              ← chat messages
```

Only one can be visible at a time — canvas open dispatches browser takeover close and vice versa.

---

## 8. CanvasTakeOverView Detailed Spec

### 8.1 Template structure

```vue
<template>
  <div v-if="shouldShow" class="fixed bg-[var(--background-gray-main)] z-[61] w-full h-full inset-0 flex flex-col">

    <!-- Canvas topbar (44px, mirrors TakeOverView address bar) -->
    <div class="canvas-takeover-topbar">
      <!-- Left: back + project name + save status -->
      <button @click="handleClose"><ArrowLeft /></button>
      <input v-model="projectName" @blur="handleProjectNameChange" />
      <span v-if="saving">Saving…</span>
      <span v-else-if="isDirty">Unsaved</span>

      <!-- Center: tool selection (replaces URL bar) -->
      <div class="canvas-tool-chips">
        <button v-for="tool in tools" :key="tool.id"
                :class="{ active: editorState.activeTool === tool.id }"
                @click="setTool(tool.id)">
          <component :is="tool.icon" :size="14" />
          <span>{{ tool.label }}</span>
        </button>
      </div>

      <!-- Right: undo/redo/save/export/exit -->
      <button @click="handleUndo" :disabled="!canUndo"><Undo2 /></button>
      <button @click="handleRedo" :disabled="!canRedo"><Redo2 /></button>
      <button @click="saveProject"><Save /></button>
      <button @click="showExportDialog = true"><Download /></button>
      <button @click="handleClose" class="exit-canvas-btn">Exit Canvas</button>
    </div>

    <!-- Editor body -->
    <div class="flex flex-1 min-h-0">
      <!-- Vertical tool icons (sidebar) - collapsed version of CanvasToolbar -->
      <CanvasToolbar :active-tool="editorState.activeTool" @tool-change="setTool" />

      <!-- Main stage -->
      <div class="relative flex-1 min-w-0">
        <CanvasStage
          ref="stageRef"
          :elements="elements"
          :selected-element-ids="editorState.selectedElementIds"
          :editor-state="editorState"
          :page-width="pageWidth"
          :page-height="pageHeight"
          :page-background="pageBackground"
          @element-select="handleElementSelect"
          @element-move="handleElementMove"
          @element-transform="handleElementTransform"
          @stage-click="clearSelection"
          @pan-change="handlePanChange"
          @wheel="handleWheel"
        />
        <CanvasZoomControls :zoom="editorState.zoom" class="absolute bottom-4 right-4 z-10"
          @zoom-in="zoomIn" @zoom-out="zoomOut" @fit="handleFitToScreen" @reset="resetZoom" />

        <!-- Agent editing indicator -->
        <div v-if="agentIsEditing" class="agent-editing-pill">
          <span class="agent-editing-dot"></span>
          Agent is editing…
        </div>
      </div>

      <!-- Right panels (collapsible) -->
      <aside v-if="showRightPanel" class="canvas-takeover-right-panels">
        <CanvasPropertyPanel :element="selectedElements[0] || null" @property-change="handlePropertyChange" />
        <CanvasLayerPanel :elements="elements" :selected-element-ids="editorState.selectedElementIds"
          @select="handleElementSelect" @toggle-visibility="handleToggleVisibility"
          @toggle-lock="handleToggleLock" @bring-to-front="bringToFront" @send-to-back="sendToBack" />
      </aside>
      <button class="panel-toggle-btn" @click="showRightPanel = !showRightPanel">
        <ChevronRight :class="{ 'rotate-180': showRightPanel }" />
      </button>
    </div>

    <!-- Export dialog -->
    <CanvasExportDialog v-if="showExportDialog" :project="project"
      @close="showExportDialog = false"
      @export-png="handleExportPNG" @export-json="handleExportJSON" />

    <!-- First-time onboarding tooltip -->
    <Transition name="fade">
      <div v-if="showOnboarding" class="canvas-onboarding-tooltip">
        <Paintbrush class="w-4 h-4 text-purple-600" />
        <div>
          <h4>Canvas is open!</h4>
          <p>You and the agent can edit this design together. Changes save automatically.</p>
        </div>
        <button @click="dismissOnboarding"><X /></button>
      </div>
    </Transition>
  </div>
</template>
```

### 8.2 Key CSS variables

```css
.canvas-takeover-topbar {
  height: 44px;            /* matches TakeOverView */
  background: var(--background-white-main);
  border-bottom: 1px solid var(--border-light);
}

.exit-canvas-btn {
  /* matches TakeOverView exit button style */
  background: var(--Button-primary-black);
  color: var(--text-onblack);
  border-radius: 999px;
  border: 2px solid var(--border-dark);
  box-shadow: 0px 8px 32px 0px rgba(0,0,0,0.32);
}

.agent-editing-pill {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.agent-editing-dot {
  width: 8px;
  height: 8px;
  background: var(--function-success);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

.canvas-takeover-right-panels {
  width: 260px;
  border-left: 1px solid var(--border-light);
  overflow-y: auto;
  background: var(--background-white-main);
}
```

---

## 9. Backend Canvas SSE Event Schema

```python
# backend/app/interfaces/schemas/event.py

class CanvasAction(str, Enum):
    project_created = "project_created"
    project_updated = "project_updated"
    element_added = "element_added"
    element_modified = "element_modified"
    element_deleted = "element_deleted"
    export_ready = "export_ready"

class CanvasSSEEvent(BaseModel):
    type: Literal["canvas"] = "canvas"
    action: CanvasAction
    project_id: str
    project_name: str | None = None
    element_id: str | None = None
    export_url: str | None = None  # for export_ready
```

---

## 10. Testing Plan

### Frontend
```bash
cd frontend && bun run lint && bun run type-check
```

Manual test matrix:
1. Agent creates canvas project → live view auto-opens canvas editor
2. Agent adds element → canvas stage refreshes without flash
3. User edits element → auto-save runs after 3s
4. User clicks Exit Canvas → live view returns to browser screencast
5. Browser takeover while canvas open → canvas closes, takeover opens (z-index order)
6. Canvas open while browser takeover active → takeover closes, canvas opens
7. Keyboard shortcuts work inside canvas overlay (Ctrl+Z, Ctrl+S, Delete, Escape)
8. Dark mode: all design tokens render correctly
9. Right panel collapse/expand works
10. Export dialog opens and exports PNG

### Backend
```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

New tests:
- `tests/interfaces/api/test_session_routes.py` — `GET /sessions/{id}/canvas-project`
- `tests/domain/services/tools/test_canvas_tool.py` — session project linkage
- `tests/application/services/test_canvas_service.py` — SSE event emission

---

## 11. Rollout Order

| Phase | Effort | Priority | Description |
|-------|--------|----------|-------------|
| Phase 1 | Medium | P0 | `CanvasTakeOverView.vue` component |
| Phase 2 | Small | P0 | Canvas tab in `BrowserToolView` |
| Phase 3 | Small | P1 | Session–canvas project linkage (backend) |
| Phase 4 | Small | P1 | Canvas SSE events |
| Phase 5 | Medium | P1 | Agent canvas tool enhancements |
| Phase 6 | Large | P2 | AI panel chat input + style presets |
| Phase 7 | Large | P2 | Collaboration signals + lock state |

**Recommended start:** Phase 1 + Phase 2 together (pure frontend, zero backend changes, immediately usable).

---

## 12. Definition of Done

- [ ] Canvas editor opens inside the live view panel (same visual design as browser takeover)
- [ ] Agent canvas tool calls auto-trigger canvas editor to open
- [ ] User can open canvas manually via "Canvas" tab in the tool panel
- [ ] Canvas edits auto-save; no data loss on Exit
- [ ] Canvas and browser takeover coexist cleanly (correct z-index, one active at a time)
- [ ] Agent-editing indicator shows when agent holds canvas lock
- [ ] Keyboard shortcuts work inside canvas overlay
- [ ] Dark mode compatible
- [ ] `bun run lint && bun run type-check` passes (frontend)
- [ ] `ruff check . && pytest tests/` passes (backend)
