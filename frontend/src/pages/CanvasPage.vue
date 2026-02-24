<template>
  <div class="canvas-page">
    <!-- Loading overlay -->
    <div v-if="loading" class="canvas-loading">
      <div class="canvas-loading-spinner" />
      <span class="canvas-loading-text">Loading project...</span>
    </div>

    <!-- Main editor layout -->
    <template v-else-if="project">
      <!-- Top bar -->
      <header class="canvas-topbar">
        <div class="canvas-topbar-left">
          <button
            class="canvas-topbar-btn"
            title="Back"
            @click="handleBack"
          >
            <ArrowLeft :size="18" />
          </button>
          <input
            v-model="projectName"
            class="canvas-project-name"
            type="text"
            placeholder="Untitled project"
            @blur="handleProjectNameChange"
            @keydown.enter="($event.target as HTMLInputElement).blur()"
          />
          <span v-if="saving" class="canvas-save-indicator">
            <Save :size="14" />
            Saving...
          </span>
          <span v-else-if="editorState.isDirty" class="canvas-save-indicator canvas-save-unsaved">
            Unsaved changes
          </span>
        </div>

        <div class="canvas-topbar-right">
          <button
            class="canvas-topbar-btn"
            title="Undo (Ctrl+Z)"
            :disabled="!canUndo"
            @click="handleUndo"
          >
            <Undo2 :size="18" />
          </button>
          <button
            class="canvas-topbar-btn"
            title="Redo (Ctrl+Shift+Z)"
            :disabled="!canRedo"
            @click="handleRedo"
          >
            <Redo2 :size="18" />
          </button>
          <button
            class="canvas-topbar-btn"
            title="Save (Ctrl+S)"
            @click="saveProject"
          >
            <Save :size="18" />
          </button>
          <button
            class="canvas-topbar-btn canvas-topbar-btn--primary"
            title="Export"
            @click="showExportDialog = true"
          >
            <Download :size="18" />
            <span>Export</span>
          </button>
        </div>
      </header>

      <!-- Editor body: toolbar + stage + right panels -->
      <div class="canvas-body">
        <!-- Left toolbar -->
        <CanvasToolbar
          :active-tool="editorState.activeTool"
          @tool-change="setTool"
        />

        <!-- Center stage -->
        <div class="canvas-stage-wrapper">
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

          <!-- Floating zoom controls -->
          <CanvasZoomControls
            :zoom="editorState.zoom"
            class="canvas-zoom-controls"
            @zoom-in="handleZoomIn"
            @zoom-out="handleZoomOut"
            @fit="handleFitToScreen"
            @reset="handleResetZoom"
          />
        </div>

        <!-- Right panels -->
        <aside class="canvas-right-panels">
          <CanvasPropertyPanel
            :element="selectedElements[0] || null"
            @property-change="handlePropertyChange"
          />
          <CanvasLayerPanel
            :elements="elements"
            :selected-element-ids="editorState.selectedElementIds"
            @select="handleElementSelect"
            @toggle-visibility="handleToggleVisibility"
            @toggle-lock="handleToggleLock"
            @bring-to-front="handleBringToFront"
            @send-to-back="handleSendToBack"
          />
          <CanvasAIPanel
            :project-id="project.id"
            @image-generated="handleImageGenerated"
            @project-updated="handleProjectUpdated"
          />
        </aside>
      </div>

      <!-- Export dialog -->
      <CanvasExportDialog
        v-if="showExportDialog"
        :project="project"
        @close="showExportDialog = false"
        @export-png="handleExportPNG"
        @export-json="handleExportJSON"
      />
    </template>

    <!-- No project: prompt to create -->
    <div v-else class="canvas-empty">
      <h2 class="canvas-empty-title">Canvas Editor</h2>
      <p class="canvas-empty-subtitle">Create a new project to get started.</p>
      <button
        class="canvas-empty-btn"
        @click="handleCreateProject"
      >
        Create New Project
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Undo2, Redo2, Save, Download, ArrowLeft } from 'lucide-vue-next'
import { useCanvasEditor } from '@/composables/useCanvasEditor'
import { useCanvasHistory } from '@/composables/useCanvasHistory'
import { useCanvasExport } from '@/composables/useCanvasExport'
import type { CanvasElement, CanvasProject } from '@/types/canvas'
import CanvasStage from '@/components/canvas/editor/CanvasStage.vue'
import CanvasToolbar from '@/components/canvas/editor/CanvasToolbar.vue'
import CanvasPropertyPanel from '@/components/canvas/editor/CanvasPropertyPanel.vue'
import CanvasLayerPanel from '@/components/canvas/editor/CanvasLayerPanel.vue'
import CanvasAIPanel from '@/components/canvas/editor/CanvasAIPanel.vue'
import CanvasZoomControls from '@/components/canvas/editor/CanvasZoomControls.vue'
import CanvasExportDialog from '@/components/canvas/editor/CanvasExportDialog.vue'

const route = useRoute()
const router = useRouter()
const routeProjectId = computed(() => route.params.projectId as string | undefined)

const {
  project,
  editorState,
  loading,
  saving,
  activePage,
  elements,
  selectedElements,
  loadProject,
  createProject,
  saveProject,
  markDirty,
  addElement,
  updateElement,
  deleteElements,
  selectElement,
  clearSelection,
  selectAll,
  setTool,
  setZoom,
  zoomIn,
  zoomOut,
  resetZoom,
  setPan,
  bringToFront,
  sendToBack,
} = useCanvasEditor()

const { canUndo, canRedo, pushState, undo, redo } = useCanvasHistory()
const { exportPNG, exportJSON } = useCanvasExport()

const showExportDialog = ref(false)
const projectName = ref('')
const stageRef = ref<InstanceType<typeof CanvasStage> | null>(null)
const hasUserAdjustedViewport = ref(false)
const isApplyingViewportTransform = ref(false)

const pageWidth = computed(() => activePage.value?.width ?? project.value?.width ?? 1920)
const pageHeight = computed(() => activePage.value?.height ?? project.value?.height ?? 1080)
const pageBackground = computed(() => activePage.value?.background ?? project.value?.background ?? '#FFFFFF')

interface Bounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

interface StageWheelPayload {
  deltaY: number
  ctrl: boolean
  pointerX: number
  pointerY: number
  stageX: number
  stageY: number
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `el-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

// Sync project name with local editable input
watch(
  () => project.value?.name,
  (name) => {
    if (name !== undefined) {
      projectName.value = name
    }
  },
  { immediate: true },
)

// --- Lifecycle ---
onMounted(async () => {
  if (routeProjectId.value) {
    await loadProject(routeProjectId.value)
    if (project.value) {
      pushState(project.value.pages)
      await fitViewportToContent({ force: true })
    }
  }
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})

watch(
  () => routeProjectId.value,
  async (projectId, previousProjectId) => {
    if (!projectId || projectId === previousProjectId) return
    await loadProject(projectId)
    if (project.value) {
      pushState(project.value.pages)
      hasUserAdjustedViewport.value = false
      await fitViewportToContent({ force: true })
    }
  },
)

// --- Navigation ---
function handleBack() {
  router.push('/chat')
}

// --- Project name ---
function handleProjectNameChange() {
  if (!project.value || projectName.value === project.value.name) return
  project.value.name = projectName.value
  markDirty()
}

// --- Create project ---
async function handleCreateProject() {
  const newProject = await createProject('Untitled project')
  if (newProject) {
    router.replace({ path: `/chat/canvas/${newProject.id}` })
    pushState(newProject.pages)
  }
}

// --- Element events ---
function handleElementSelect(elementId: string, multi?: boolean) {
  selectElement(elementId, multi)
}

function handleElementMove(elementId: string, x: number, y: number) {
  if (project.value) {
    pushState(project.value.pages)
  }
  updateElement(elementId, { x, y })
}

function handleElementTransform(
  elementId: string,
  updates: Partial<CanvasElement>,
) {
  if (project.value) {
    pushState(project.value.pages)
  }
  updateElement(elementId, updates)
}

function handlePropertyChange(
  elementId: string,
  updates: Partial<CanvasElement>,
) {
  if (project.value) {
    pushState(project.value.pages)
  }
  updateElement(elementId, updates)
}

function handleAddElement(element: CanvasElement) {
  if (project.value) {
    pushState(project.value.pages)
  }
  addElement(element)
}

function handleProjectUpdated(updatedProject: CanvasProject) {
  if (!updatedProject) return
  if (project.value) {
    pushState(project.value.pages)
  }
  project.value = updatedProject
  editorState.value.selectedElementIds = []
  editorState.value.isDirty = false
  void fitViewportToContent()
}

function handleImageGenerated(urls: string[] | null | undefined) {
  const generatedUrls = Array.isArray(urls)
    ? urls.filter((url): url is string => typeof url === 'string' && url.trim().length > 0)
    : []
  if (!project.value || generatedUrls.length === 0) return
  const url = generatedUrls[0]
  const width = Math.min(512, pageWidth.value)
  const height = Math.min(512, pageHeight.value)
  const x = Math.max(0, Math.round((pageWidth.value - width) / 2))
  const y = Math.max(0, Math.round((pageHeight.value - height) / 2))
  const maxZ = elements.value.reduce((max, el) => Math.max(max, el.z_index), 0)
  const element: CanvasElement = {
    id: generateId(),
    type: 'image',
    name: 'AI Image',
    x,
    y,
    width,
    height,
    rotation: 0,
    scale_x: 1,
    scale_y: 1,
    opacity: 1,
    visible: true,
    locked: false,
    z_index: maxZ + 1,
    corner_radius: 0,
    src: url,
  }
  handleAddElement(element)
}

function handleToggleVisibility(elementId: string, visible: boolean) {
  if (project.value) {
    pushState(project.value.pages)
  }
  updateElement(elementId, { visible })
}

function handleToggleLock(elementId: string, locked: boolean) {
  if (project.value) {
    pushState(project.value.pages)
  }
  updateElement(elementId, { locked })
}

function handleBringToFront(elementId: string) {
  if (project.value) {
    pushState(project.value.pages)
  }
  bringToFront(elementId)
}

function handleSendToBack(elementId: string) {
  if (project.value) {
    pushState(project.value.pages)
  }
  sendToBack(elementId)
}

// --- Wheel zoom ---
function handlePanChange(x: number, y: number) {
  if (isApplyingViewportTransform.value) return
  hasUserAdjustedViewport.value = true
  setPan(Math.round(x), Math.round(y))
}

function handleWheel(payload: StageWheelPayload) {
  hasUserAdjustedViewport.value = true
  const currentZoom = editorState.value.zoom
  const scaleFactor = payload.deltaY > 0 ? 0.9 : 1.1
  const nextZoom = Math.max(0.1, Math.min(currentZoom * scaleFactor, 5))
  if (Math.abs(nextZoom - currentZoom) < 0.0001) return

  const worldX = (payload.pointerX - payload.stageX) / currentZoom
  const worldY = (payload.pointerY - payload.stageY) / currentZoom
  const nextPanX = payload.pointerX - worldX * nextZoom
  const nextPanY = payload.pointerY - worldY * nextZoom

  setZoom(nextZoom)
  setPan(Math.round(nextPanX), Math.round(nextPanY))
}

async function handleFitToScreen() {
  hasUserAdjustedViewport.value = false
  await fitViewportToContent({ force: true })
}

// --- Undo / Redo ---
function handleUndo() {
  if (!project.value) return
  const restored = undo(project.value.pages)
  if (restored) {
    project.value.pages = restored
    markDirty()
  }
}

function handleRedo() {
  if (!project.value) return
  const restored = redo(project.value.pages)
  if (restored) {
    project.value.pages = restored
    markDirty()
  }
}

function handleZoomIn() {
  hasUserAdjustedViewport.value = true
  zoomIn()
}

function handleZoomOut() {
  hasUserAdjustedViewport.value = true
  zoomOut()
}

function handleResetZoom() {
  hasUserAdjustedViewport.value = true
  resetZoom()
}

function getElementBounds(element: CanvasElement): Bounds | null {
  if (!element.visible) return null

  const scaleX = Math.abs(Number.isFinite(element.scale_x) ? element.scale_x : 1)
  const scaleY = Math.abs(Number.isFinite(element.scale_y) ? element.scale_y : 1)

  if ((element.type === 'line' || element.type === 'path') && Array.isArray(element.points) && element.points.length >= 2) {
    let minPx = Number.POSITIVE_INFINITY
    let minPy = Number.POSITIVE_INFINITY
    let maxPx = Number.NEGATIVE_INFINITY
    let maxPy = Number.NEGATIVE_INFINITY

    for (let index = 0; index < element.points.length - 1; index += 2) {
      const px = element.points[index]
      const py = element.points[index + 1]
      if (!Number.isFinite(px) || !Number.isFinite(py)) continue
      minPx = Math.min(minPx, px)
      minPy = Math.min(minPy, py)
      maxPx = Math.max(maxPx, px)
      maxPy = Math.max(maxPy, py)
    }

    if (!Number.isFinite(minPx) || !Number.isFinite(minPy) || !Number.isFinite(maxPx) || !Number.isFinite(maxPy)) {
      return null
    }

    return {
      minX: element.x + minPx * scaleX,
      minY: element.y + minPy * scaleY,
      maxX: element.x + maxPx * scaleX,
      maxY: element.y + maxPy * scaleY,
    }
  }

  const width = Math.max(1, Math.abs(element.width * scaleX))
  const height = Math.max(1, Math.abs(element.height * scaleY))

  return {
    minX: element.x,
    minY: element.y,
    maxX: element.x + width,
    maxY: element.y + height,
  }
}

function getContentBounds(): Bounds | null {
  if (elements.value.length === 0) return null
  const visibleElements = elements.value.filter((element) => element.visible !== false)
  if (visibleElements.length === 0) return null

  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY

  for (const element of visibleElements) {
    const bounds = getElementBounds(element)
    if (!bounds) continue
    minX = Math.min(minX, bounds.minX)
    minY = Math.min(minY, bounds.minY)
    maxX = Math.max(maxX, bounds.maxX)
    maxY = Math.max(maxY, bounds.maxY)
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null
  }

  return { minX, minY, maxX, maxY }
}

async function waitForStageReady() {
  await nextTick()
  await new Promise<void>((resolve) => {
    if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
      resolve()
      return
    }
    window.requestAnimationFrame(() => resolve())
  })
}

function applyViewportToBounds(bounds: Bounds, padding: number) {
  const stage = stageRef.value?.getStage()
  if (!stage) return

  const stageWidth = stage.width()
  const stageHeight = stage.height()
  if (stageWidth <= 0 || stageHeight <= 0) return

  const contentWidth = Math.max(1, bounds.maxX - bounds.minX)
  const contentHeight = Math.max(1, bounds.maxY - bounds.minY)
  const innerWidth = Math.max(1, stageWidth - padding * 2)
  const innerHeight = Math.max(1, stageHeight - padding * 2)

  const zoom = Math.max(0.1, Math.min(Math.min(innerWidth / contentWidth, innerHeight / contentHeight), 5))
  const offsetX = Math.round((stageWidth - contentWidth * zoom) / 2 - bounds.minX * zoom)
  const offsetY = Math.round((stageHeight - contentHeight * zoom) / 2 - bounds.minY * zoom)

  isApplyingViewportTransform.value = true
  setZoom(zoom)
  setPan(offsetX, offsetY)
  isApplyingViewportTransform.value = false
}

async function fitViewportToContent(options?: { force?: boolean }) {
  if (!project.value) return
  if (hasUserAdjustedViewport.value && !options?.force) return

  await waitForStageReady()
  const bounds = getContentBounds()

  if (bounds) {
    applyViewportToBounds(bounds, 72)
    return
  }

  applyViewportToBounds(
    { minX: 0, minY: 0, maxX: pageWidth.value, maxY: pageHeight.value },
    36,
  )
}

// --- Export ---
function handleExportPNG() {
  const stageNode = stageRef.value?.getStage()
  if (stageNode) exportPNG(stageNode)
  showExportDialog.value = false
}

function handleExportJSON() {
  if (project.value) {
    exportJSON(project.value)
  }
  showExportDialog.value = false
}

// --- Keyboard shortcuts ---
function handleKeydown(event: KeyboardEvent) {
  const isCtrlOrMeta = event.ctrlKey || event.metaKey
  const target = event.target as HTMLElement
  const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable

  // Ctrl+S: Save
  if (isCtrlOrMeta && event.key === 's') {
    event.preventDefault()
    saveProject()
    return
  }

  // Ctrl+Z: Undo, Ctrl+Shift+Z: Redo
  if (isCtrlOrMeta && event.key === 'z') {
    event.preventDefault()
    if (event.shiftKey) {
      handleRedo()
    } else {
      handleUndo()
    }
    return
  }

  // Skip remaining shortcuts when focused on text input
  if (isInput) return

  // Delete or Backspace: delete selected elements
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault()
    if (editorState.value.selectedElementIds.length > 0) {
      if (project.value) {
        pushState(project.value.pages)
      }
      deleteElements([...editorState.value.selectedElementIds])
    }
    return
  }

  // Escape: clear selection
  if (event.key === 'Escape') {
    clearSelection()
    return
  }

  // Ctrl+A: select all
  if (isCtrlOrMeta && event.key === 'a') {
    event.preventDefault()
    selectAll()
  }
}
</script>

<style scoped>
.canvas-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100%;
  background: var(--background-white-main);
  overflow: hidden;
}

/* Loading */
.canvas-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
}

.canvas-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-light);
  border-top-color: var(--text-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.canvas-loading-text {
  font-size: 14px;
  color: var(--text-secondary);
}

/* Top bar */
.canvas-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  min-height: 48px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-light);
  background: var(--background-white-main);
  gap: 8px;
}

.canvas-topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.canvas-topbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.canvas-topbar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  min-width: 32px;
  padding: 0 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s, color 0.15s;
}

.canvas-topbar-btn:hover:not(:disabled) {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-topbar-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.canvas-topbar-btn--primary {
  background: var(--text-primary);
  color: var(--background-white-main);
  padding: 0 12px;
}

.canvas-topbar-btn--primary:hover:not(:disabled) {
  opacity: 0.85;
  background: var(--text-primary);
  color: var(--background-white-main);
}

.canvas-project-name {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  max-width: 280px;
  min-width: 120px;
  outline: none;
  transition: border-color 0.15s;
}

.canvas-project-name:hover {
  border-color: var(--border-light);
}

.canvas-project-name:focus {
  border-color: var(--text-tertiary);
}

.canvas-save-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.canvas-save-unsaved {
  color: var(--text-secondary);
}

/* Editor body */
.canvas-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Stage wrapper */
.canvas-stage-wrapper {
  flex: 1;
  position: relative;
  min-width: 0;
  overflow: hidden;
}

.canvas-zoom-controls {
  position: absolute;
  bottom: 16px;
  right: 16px;
  z-index: 10;
}

/* Right panels */
.canvas-right-panels {
  width: 260px;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border-light);
  background: var(--background-white-main);
  overflow-y: auto;
}

/* Empty state */
.canvas-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
}

.canvas-empty-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.canvas-empty-subtitle {
  font-size: 14px;
  color: var(--text-tertiary);
}

.canvas-empty-btn {
  margin-top: 8px;
  height: 40px;
  padding: 0 20px;
  border: none;
  border-radius: 10px;
  background: var(--text-primary);
  color: var(--background-white-main);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}

.canvas-empty-btn:hover {
  opacity: 0.85;
}
</style>
