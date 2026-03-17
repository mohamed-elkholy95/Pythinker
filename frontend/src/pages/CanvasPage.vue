<template>
  <div class="canvas-page">
    <div v-if="loading" class="canvas-loading">
      <div class="canvas-loading-spinner" />
      <span class="canvas-loading-text">Loading project...</span>
    </div>

    <template v-else-if="project">
      <div class="canvas-studio-shell">
        <CanvasWorkspaceHeader
          :project-name="project.name"
          :sync-status="canvasSyncStatus"
          :mode="workspaceMode"
          :session-id="routeSessionId"
          :version="project.version"
          :element-count="elements.length"
          secondary-action-label="Return to Chat"
          primary-action-label="Export"
          @secondary-action="handleBack"
          @primary-action="showExportDialog = true"
        />

        <CanvasSyncBanner
          v-if="pageSyncBanner"
          :status="pageSyncBanner.status"
          :title="pageSyncBanner.title"
          :description="pageSyncBanner.description"
          :primary-action-label="pageSyncBanner.primaryActionLabel"
          :secondary-action-label="pageSyncBanner.secondaryActionLabel"
          @primary-action="handlePrimarySyncAction"
          @secondary-action="handleSecondarySyncAction"
        />

        <div class="canvas-studio-actions">
          <div class="canvas-project-name-shell">
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
            <span
              v-else-if="editorState.isDirty"
              class="canvas-save-indicator canvas-save-unsaved"
            >
              Unsaved changes
            </span>
          </div>

          <div class="canvas-studio-actions__buttons">
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
              class="canvas-topbar-btn"
              title="Fit canvas"
              @click="handleFitToScreen"
            >
              <ArrowLeftRight :size="18" />
            </button>
          </div>
        </div>

        <div class="canvas-body">
          <div class="canvas-toolbar-shell">
            <CanvasToolbar
              :active-tool="editorState.activeTool"
              @tool-change="setTool"
            />
          </div>

          <div class="canvas-stage-shell">
            <div class="canvas-stage-wrapper">
              <CanvasStage
                ref="stageRef"
                :elements="elements"
                :selected-element-ids="editorState.selectedElementIds"
                :highlighted-element-ids="syncState.highlightedElementIds"
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

              <CanvasZoomControls
                :zoom="editorState.zoom"
                class="canvas-zoom-controls"
                @zoom-in="handleZoomIn"
                @zoom-out="handleZoomOut"
                @fit="handleFitToScreen"
                @reset="handleResetZoom"
              />
            </div>
          </div>

          <aside class="canvas-right-panels">
            <CanvasActivityRail
              :session-id="routeSessionId"
              :server-version="syncState.serverVersion"
              :pending-remote-version="syncState.pendingRemoteVersion"
              :element-count="elements.length"
              :last-operation="formattedLastRemoteOperation"
              :last-source="syncState.lastRemoteSource"
              :changed-element-ids="syncState.lastChangedElementIds"
              :updated-at="project.updated_at"
            />
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

        <CanvasExportDialog
          v-if="showExportDialog"
          :project="project"
          @close="showExportDialog = false"
          @export-png="handleExportPNG"
          @export-json="handleExportJSON"
        />
      </div>
    </template>

    <div v-else class="canvas-empty">
      <h2 class="canvas-empty-title">Canvas Editor</h2>
      <p class="canvas-empty-subtitle">Create a new project to get started.</p>
      <button class="canvas-empty-btn" @click="handleCreateProject">
        Create New Project
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeftRight, Redo2, Save, Undo2 } from 'lucide-vue-next'

import { getSessionProject } from '@/api/canvas'
import CanvasActivityRail from '@/components/canvas/CanvasActivityRail.vue'
import CanvasSyncBanner from '@/components/canvas/CanvasSyncBanner.vue'
import CanvasWorkspaceHeader from '@/components/canvas/CanvasWorkspaceHeader.vue'
import CanvasAIPanel from '@/components/canvas/editor/CanvasAIPanel.vue'
import CanvasExportDialog from '@/components/canvas/editor/CanvasExportDialog.vue'
import CanvasLayerPanel from '@/components/canvas/editor/CanvasLayerPanel.vue'
import CanvasPropertyPanel from '@/components/canvas/editor/CanvasPropertyPanel.vue'
import CanvasStage from '@/components/canvas/editor/CanvasStage.vue'
import CanvasToolbar from '@/components/canvas/editor/CanvasToolbar.vue'
import CanvasZoomControls from '@/components/canvas/editor/CanvasZoomControls.vue'
import { useCanvasEditor } from '@/composables/useCanvasEditor'
import { useCanvasExport } from '@/composables/useCanvasExport'
import { useCanvasHistory } from '@/composables/useCanvasHistory'
import type {
  CanvasElement,
  CanvasProject,
  CanvasSyncStatus,
} from '@/types/canvas'

const route = useRoute()
const router = useRouter()
const routeProjectId = computed(() => route.params.projectId as string | undefined)
const routeSessionId = computed(() =>
  typeof route.query.sessionId === 'string' ? route.query.sessionId : null,
)

const {
  project,
  editorState,
  syncState,
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
  syncFromRemoteProject,
  applyPendingRemoteUpdate,
  dismissPendingRemoteUpdate,
} = useCanvasEditor()

const { canUndo, canRedo, pushState, undo, redo } = useCanvasHistory()
const { exportPNG, exportJSON } = useCanvasExport()

const showExportDialog = ref(false)
const projectName = ref('')
const stageRef = ref<InstanceType<typeof CanvasStage> | null>(null)
const hasUserAdjustedViewport = ref(false)
const isApplyingViewportTransform = ref(false)
let sessionSyncTimer: ReturnType<typeof setInterval> | null = null

const pageWidth = computed(() => activePage.value?.width ?? project.value?.width ?? 1920)
const pageHeight = computed(() => activePage.value?.height ?? project.value?.height ?? 1080)
const pageBackground = computed(() => activePage.value?.background ?? project.value?.background ?? '#FFFFFF')
const formattedLastRemoteOperation = computed(() =>
  syncState.value.lastRemoteOperation?.replace(/_/g, ' ') ?? null,
)
const canvasSyncStatus = computed<CanvasSyncStatus>(() => {
  if (saving.value || loading.value) return 'syncing'
  if (syncState.value.hasRemoteConflict) return 'conflict'
  if (syncState.value.isStale) return 'stale'
  if (routeSessionId.value) return 'live'
  return 'saved'
})
const workspaceMode = computed<'agent' | 'manual'>(() => (
  editorState.value.isDirty || syncState.value.hasRemoteConflict || syncState.value.isStale
    ? 'manual'
    : 'agent'
))
const pageSyncBanner = computed(() => {
  if (syncState.value.hasRemoteConflict) {
    return {
      status: 'conflict' as const,
      title: 'Agent updated this canvas',
      description: syncState.value.pendingRemoteVersion !== null
        ? `A newer remote version (v${syncState.value.pendingRemoteVersion}) is waiting while you finish your local draft.`
        : 'A newer remote version is waiting while you finish your local draft.',
      primaryActionLabel: 'Apply latest',
      secondaryActionLabel: 'Keep my draft',
    }
  }

  if (syncState.value.isStale) {
    return {
      status: 'stale' as const,
      title: 'Your draft is behind the latest agent canvas',
      description: syncState.value.pendingRemoteVersion !== null
        ? `Reload v${syncState.value.pendingRemoteVersion} when you are ready to replace your draft with the latest agent output.`
        : 'Reload the latest agent output when you are ready to replace your draft.',
      primaryActionLabel: 'Reload canvas',
      secondaryActionLabel: '',
    }
  }

  return null
})

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

watch(
  () => project.value?.name,
  (name) => {
    if (name !== undefined) {
      projectName.value = name
    }
  },
  { immediate: true },
)

onMounted(async () => {
  await loadInitialCanvasProject()
  startSessionSync()
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  stopSessionSync()
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

watch(
  () => routeSessionId.value,
  () => {
    stopSessionSync()
    startSessionSync()
  },
)

function handleBack() {
  router.push('/chat')
}

function handleProjectNameChange() {
  if (!project.value || projectName.value === project.value.name) return
  project.value.name = projectName.value
  markDirty()
}

async function handleCreateProject() {
  const newProject = await createProject(
    'Untitled project',
    undefined,
    undefined,
    { sessionId: routeSessionId.value ?? undefined },
  )
  if (newProject) {
    router.replace({
      path: `/chat/canvas/${newProject.id}`,
      query: routeSessionId.value ? { sessionId: routeSessionId.value } : undefined,
    })
    pushState(newProject.pages)
  }
}

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
  syncState.value.sessionId = updatedProject.session_id
  syncState.value.serverVersion = updatedProject.version
  syncState.value.pendingRemoteVersion = null
  syncState.value.hasRemoteConflict = false
  syncState.value.isStale = false
  syncState.value.lastRemoteOperation = 'ai_edit'
  syncState.value.lastRemoteSource = 'manual'
  syncState.value.lastChangedElementIds = []
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

async function handlePrimarySyncAction() {
  if (routeSessionId.value) {
    await applyPendingRemoteUpdate(() => getSessionProject(routeSessionId.value!))
    return
  }
  await applyPendingRemoteUpdate()
}

function handleSecondarySyncAction() {
  dismissPendingRemoteUpdate()
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
  const stage = typeof stageRef.value?.getStage === 'function'
    ? stageRef.value.getStage()
    : null
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

async function loadInitialCanvasProject() {
  if (routeProjectId.value) {
    await loadProject(routeProjectId.value)
    if (project.value) {
      pushState(project.value.pages)
      await fitViewportToContent({ force: true })
    }
    return
  }

  if (!routeSessionId.value) {
    return
  }

  try {
    const sessionProject = await getSessionProject(routeSessionId.value)
    const syncResult = await syncFromRemoteProject(sessionProject, {
      operation: 'session_link',
      source: 'system',
    })
    if (syncResult !== 'ignored') {
      await router.replace({
        path: `/chat/canvas/${sessionProject.id}`,
        query: { sessionId: routeSessionId.value },
      })
      pushState(sessionProject.pages)
      await fitViewportToContent({ force: true })
    }
  } catch {
    // Session may not have an active canvas yet.
  }
}

async function syncSessionProject() {
  if (!routeSessionId.value) return
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return

  try {
    const sessionProject = await getSessionProject(routeSessionId.value)
    if (project.value && sessionProject.id !== project.value.id && editorState.value.isDirty) {
      return
    }

    const syncResult = await syncFromRemoteProject(sessionProject, {
      operation: 'agent_sync',
      source: 'agent',
    })

    if (!routeProjectId.value || routeProjectId.value !== sessionProject.id) {
      await router.replace({
        path: `/chat/canvas/${sessionProject.id}`,
        query: { sessionId: routeSessionId.value },
      })
    }

    if (syncResult === 'applied') {
      await fitViewportToContent()
    }
  } catch {
    // Session may not expose an active canvas while the agent is idle.
  }
}

function startSessionSync() {
  if (!routeSessionId.value) return
  void syncSessionProject()
  sessionSyncTimer = setInterval(() => {
    void syncSessionProject()
  }, 3000)
}

function stopSessionSync() {
  if (sessionSyncTimer) {
    clearInterval(sessionSyncTimer)
    sessionSyncTimer = null
  }
}

function handleExportPNG() {
  const stageNode = typeof stageRef.value?.getStage === 'function'
    ? stageRef.value.getStage()
    : null
  if (stageNode) exportPNG(stageNode)
  showExportDialog.value = false
}

function handleExportJSON() {
  if (project.value) {
    exportJSON(project.value)
  }
  showExportDialog.value = false
}

function handleKeydown(event: KeyboardEvent) {
  const isCtrlOrMeta = event.ctrlKey || event.metaKey
  const target = event.target as HTMLElement
  const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable

  if (isCtrlOrMeta && event.key === 's') {
    event.preventDefault()
    saveProject()
    return
  }

  if (isCtrlOrMeta && event.key === 'z') {
    event.preventDefault()
    if (event.shiftKey) {
      handleRedo()
    } else {
      handleUndo()
    }
    return
  }

  if (isInput) return

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

  if (event.key === 'Escape') {
    clearSelection()
    return
  }

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
  background:
    radial-gradient(circle at top left, rgba(17, 24, 39, 0.04), transparent 26%),
    linear-gradient(180deg, #f7f6f3 0%, #efede8 100%);
  overflow: hidden;
}

.canvas-studio-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  flex: 1;
  min-height: 0;
  padding: var(--space-5);
}

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

.canvas-studio-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
}

.canvas-project-name-shell {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.canvas-studio-actions__buttons {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.canvas-topbar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  min-width: 36px;
  padding: 0 10px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  background: var(--background-white-main);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.canvas-topbar-btn:hover:not(:disabled) {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-dark);
  color: var(--text-primary);
}

.canvas-topbar-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.canvas-project-name {
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 10px 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  max-width: 320px;
  min-width: 220px;
  outline: none;
  transition: border-color 0.15s, background 0.15s;
}

.canvas-project-name:hover {
  border-color: var(--border-dark);
}

.canvas-project-name:focus {
  border-color: rgba(17, 24, 39, 0.2);
  background: var(--background-white-main);
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

.canvas-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  gap: var(--space-4);
}

.canvas-toolbar-shell {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 12px 28px var(--shadow-XS);
  overflow: hidden;
}

.canvas-stage-shell {
  flex: 1;
  min-width: 0;
  padding: var(--space-4);
  border: 1px solid rgba(17, 24, 39, 0.08);
  border-radius: 28px;
  background:
    radial-gradient(circle at top center, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.58)),
    linear-gradient(180deg, #d7d4cf 0%, #cbc7c2 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9), 0 18px 44px rgba(15, 23, 42, 0.08);
}

.canvas-stage-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(17, 24, 39, 0.06);
  border-radius: 24px;
  background:
    radial-gradient(circle at center, rgba(17, 24, 39, 0.03), rgba(17, 24, 39, 0) 64%),
    #dedad4;
}

.canvas-zoom-controls {
  position: absolute;
  bottom: 16px;
  right: 16px;
  z-index: 10;
}

.canvas-right-panels {
  width: 320px;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-y: auto;
}

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

@media (max-width: 1180px) {
  .canvas-body {
    flex-direction: column;
  }

  .canvas-toolbar-shell {
    align-self: flex-start;
  }

  .canvas-right-panels {
    width: 100%;
    min-width: 0;
  }
}

@media (max-width: 820px) {
  .canvas-studio-shell {
    padding: var(--space-4);
  }

  .canvas-studio-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .canvas-project-name {
    min-width: 0;
    width: 100%;
    max-width: none;
  }

  .canvas-studio-actions__buttons {
    justify-content: flex-end;
  }
}
</style>
