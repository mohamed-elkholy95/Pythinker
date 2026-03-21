# Canvas Viewer Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-screen canvas viewer modal for charts/images that opens from the ToolPanel, matching Manus AI's canvas editor UX.

**Architecture:** 5 new Vue components in `frontend/src/components/canvas/`, wired into existing `ChatPage.vue` and `ChartToolViewEnhanced.vue`. The modal is mounted at page level (z-index overlay) and receives image data via props. All zoom/pan/tool state is local to the modal.

**Tech Stack:** Vue 3 Composition API, TypeScript, Lucide icons, CSS variables for theming.

---

### Task 1: CanvasZoomControls — Top-left zoom pill

**Files:**
- Create: `frontend/src/components/canvas/CanvasZoomControls.vue`

- [ ] **Step 1: Create component**

```vue
<script setup lang="ts">
import { Minus, Plus, Settings } from 'lucide-vue-next';

const props = defineProps<{
  zoom: number; // 0.1 - 5.0
}>();

const emit = defineEmits<{
  'zoom-in': [];
  'zoom-out': [];
  'zoom-reset': [];
  'settings-click': [];
}>();

const displayPercent = computed(() => `${Math.round(props.zoom * 100)}%`);
</script>
```

Template: Settings gear button + pill with `-` button, percentage text, `+` button.
Style: pill background `var(--fill-tsp-white-main)`, border `var(--border-main)`, rounded-full, 36px height.

- [ ] **Step 2: Verify renders in isolation** — import in a test page or Storybook equivalent.
- [ ] **Step 3: Commit** — `feat(canvas): add CanvasZoomControls component`

---

### Task 2: CanvasBottomToolbar — Floating bottom toolbar

**Files:**
- Create: `frontend/src/components/canvas/CanvasBottomToolbar.vue`

- [ ] **Step 1: Create component**

Props: `activeTool: 'select' | 'hand'`
Emits: `tool-change`

Template: Centered floating pill with 3 tool buttons:
- Select (MousePointer2 icon + ChevronDown) — dropdown with Select (V) and Hand tool (H)
- Image tool (ImageIcon)
- Notes (FileText icon + ChevronDown)

Style: `position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);` background with backdrop-blur, shadow, rounded-2xl, dark mode support.

- [ ] **Step 2: Commit** — `feat(canvas): add CanvasBottomToolbar component`

---

### Task 3: CanvasImageActionBar — Floating action bar above image

**Files:**
- Create: `frontend/src/components/canvas/CanvasImageActionBar.vue`

- [ ] **Step 1: Create component**

Emits: `download`

Template: Centered pill with action buttons:
- HD Upscale (disabled, future)
- Remove bg (disabled, future)
- Edit text (disabled, future)
- Separator line
- Download button (active)
- More (...) button

Style: white pill with shadow, `border-radius: 12px`, centered above image, `z-index: 10`.

- [ ] **Step 2: Commit** — `feat(canvas): add CanvasImageActionBar component`

---

### Task 4: CanvasImageFrame — Image card with selection handles

**Files:**
- Create: `frontend/src/components/canvas/CanvasImageFrame.vue`

- [ ] **Step 1: Create component**

Props: `imageUrl: string`, `filename: string`, `width: number`, `height: number`, `zoom: number`, `selected: boolean`

Template:
- Info bar: filename (left, muted) + dimensions "800 x 600" (right, muted)
- Image wrapped in a container with `transform: scale(zoom)`
- When `selected`: blue border (2px solid #3b82f6) with 4 corner circles (8px, blue fill, white 2px border)

- [ ] **Step 2: Commit** — `feat(canvas): add CanvasImageFrame component`

---

### Task 5: CanvasViewerModal — Main orchestrator modal

**Files:**
- Create: `frontend/src/components/canvas/CanvasViewerModal.vue`

- [ ] **Step 1: Create component**

Props:
```typescript
{
  visible: boolean;
  imageUrl: string;
  filename: string;
  width: number;
  height: number;
}
```
Emits: `close`, `download`

Template structure:
```
<Teleport to="body">
  <Transition name="canvas-fade">
    <div v-if="visible" class="canvas-viewer-overlay">
      <!-- Top bar -->
      <div class="canvas-viewer-topbar">
        <CanvasZoomControls :zoom="zoom" @zoom-in="zoomIn" @zoom-out="zoomOut" />
        <div class="canvas-viewer-topbar-right">
          <button @click="toggleFullscreen">↗</button>
          <span class="divider">|</span>
          <button @click="emit('close')">×</button>
        </div>
      </div>

      <!-- Canvas area -->
      <div class="canvas-viewer-content" @wheel="onWheel" @click.self="deselect">
        <CanvasImageActionBar @download="emit('download')" />
        <CanvasImageFrame :imageUrl :filename :width :height :zoom :selected />
      </div>

      <!-- Bottom toolbar -->
      <CanvasBottomToolbar :activeTool="activeTool" @tool-change="activeTool = $event" />
    </div>
  </Transition>
</Teleport>
```

Script: manages `zoom` (ref, default auto-fit), `activeTool` (ref), `selected` (ref, default true), keyboard listeners (Escape, V, H, +, -, 0, Cmd+S).

Style: overlay `position: fixed; inset: 0; z-index: 9999;` background `var(--background-gray-light)` light / `#1a1a1a` dark.

- [ ] **Step 2: Add keyboard shortcuts** — `onMounted` registers keydown listener, `onUnmounted` removes it.
- [ ] **Step 3: Add zoom logic** — scroll wheel handler, +/- button handlers, auto-fit calculation on open.
- [ ] **Step 4: Commit** — `feat(canvas): add CanvasViewerModal orchestrator component`

---

### Task 6: Wire into ChatPage and ChartToolViewEnhanced

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/components/toolViews/ChartToolViewEnhanced.vue`

- [ ] **Step 1: Add click-to-expand in ChartToolViewEnhanced**

On the `<img>` tag (line ~85), add `@click="emit('open-canvas')"` and `class="cursor-pointer"`.
Add emit: `'open-canvas': []`

- [ ] **Step 2: Mount CanvasViewerModal in ChatPage**

Import `CanvasViewerModal`. Add reactive state:
```typescript
const canvasViewer = reactive({
  visible: false,
  imageUrl: '',
  filename: '',
  width: 0,
  height: 0,
});
```

Mount at bottom of template (before closing `</div>`):
```vue
<CanvasViewerModal
  :visible="canvasViewer.visible"
  :imageUrl="canvasViewer.imageUrl"
  :filename="canvasViewer.filename"
  :width="canvasViewer.width"
  :height="canvasViewer.height"
  @close="canvasViewer.visible = false"
  @download="downloadCanvasImage"
/>
```

- [ ] **Step 3: Wire the open-canvas event from ToolPanel through to ChatPage**

In `ToolPanelContent.vue` or wherever `ChartToolViewEnhanced` is rendered, bubble the `open-canvas` event up. In `ChatPage.vue`, handle it by populating `canvasViewer` state and setting `visible = true`.

- [ ] **Step 4: Run lint + type-check**
```bash
cd frontend && bun run lint && bun run type-check
```

- [ ] **Step 5: Commit** — `feat(canvas): wire canvas viewer modal into ChatPage`

---

### Task 7: Test and verify

- [ ] **Step 1: Manual test** — Send a chart-generating prompt, click on the chart image, verify modal opens
- [ ] **Step 2: Verify zoom** — scroll wheel, +/- buttons, keyboard shortcuts
- [ ] **Step 3: Verify close** — Escape key, X button, click outside
- [ ] **Step 4: Verify dark mode** — toggle theme, check all elements render correctly
- [ ] **Step 5: Verify non-chart content** — terminal, browser views should NOT trigger canvas viewer
- [ ] **Step 6: Final commit** — `fix(canvas): polish and verify canvas viewer modal`
