<template>
  <div class="canvas-live-view">
    <CanvasWorkspaceHeader
      :project-name="projectTitle"
      :sync-status="effectiveSyncStatus"
      :mode="live ? 'agent' : 'manual'"
      :session-id="sessionId"
      :version="projectVersion"
      :element-count="headerElementCount"
      primary-action-label="Open Studio"
      @primary-action="openFullEditor"
    />

    <CanvasSyncBanner
      v-if="bannerState"
      :status="bannerState.status"
      :title="bannerState.title"
      :description="bannerState.description"
      :primary-action-label="bannerState.primaryActionLabel"
      :secondary-action-label="bannerState.secondaryActionLabel"
      @primary-action="emit('apply-latest')"
      @secondary-action="emit('keep-draft')"
    />

    <div class="canvas-live-summary">
      <div class="canvas-live-summary__status">
        <div v-if="live" class="canvas-live-dot" />
        <span class="canvas-live-summary__eyebrow">
          {{ live ? 'Agent is designing' : 'Canvas inspection' }}
        </span>
      </div>
      <div class="canvas-live-summary__details">
        <span>{{ operationLabel }}</span>
        <span>v{{ projectVersion }}</span>
        <span>{{ headerElementCount }} elements</span>
      </div>
    </div>

    <!-- Activity indicator / toolbar header -->
    <div class="canvas-live-header">
      <div v-if="!live" class="canvas-live-toolbar">
        <div class="canvas-tool-group">
          <button
            class="canvas-tool-btn"
            :class="{ active: editorState.activeTool === 'select' }"
            title="Select"
            @click="setTool('select')"
          >
            <MousePointer2 :size="14" />
          </button>
          <button
            class="canvas-tool-btn"
            :class="{ active: editorState.activeTool === 'hand' }"
            title="Pan"
            @click="setTool('hand')"
          >
            <Hand :size="14" />
          </button>
        </div>
        <div class="canvas-tool-group">
          <button class="canvas-tool-btn" title="Zoom in" @click="zoomIn">
            <ZoomIn :size="14" />
          </button>
          <button class="canvas-tool-btn" title="Zoom out" @click="zoomOut">
            <ZoomOut :size="14" />
          </button>
          <button class="canvas-tool-btn" title="Fit to view" @click="fitToView">
            <Maximize2 :size="14" />
          </button>
        </div>
        <div class="canvas-tool-spacer" />
        <button
          class="canvas-open-editor-btn"
          title="Open full editor"
          @click="openFullEditor"
        >
            <ExternalLink :size="12" />
          <span>Studio Tools</span>
        </button>
      </div>
    </div>

    <!-- Canvas stage container -->
    <div class="canvas-live-stage">
      <div v-if="loading" class="canvas-live-loading">
        <Loader2 :size="24" class="animate-spin text-[var(--text-tertiary)]" />
        <span class="text-sm text-[var(--text-tertiary)]">Loading canvas...</span>
      </div>
      <div v-else-if="error" class="canvas-live-error">
        <AlertCircle :size="24" class="text-[var(--text-tertiary)]" />
        <span class="text-sm text-[var(--text-tertiary)]">{{ error }}</span>
        <button class="canvas-retry-btn" @click="refresh">Retry</button>
      </div>
      <CanvasStage
        v-else-if="project && activePage"
        ref="stageRef"
        :elements="activePage.elements"
        :selected-element-ids="live ? [] : editorState.selectedElementIds"
        :editor-state="effectiveEditorState"
        :page-width="project.width"
        :page-height="project.height"
        :page-background="activePage.background || project.background || '#ffffff'"
        @element-select="handleElementSelect"
        @element-move="handleElementMove"
        @element-transform="handleElementTransform"
        @stage-click="handleStageClick"
        @wheel="handleWheel"
        @pan-change="handlePanChange"
      />
      <div v-else class="canvas-live-empty">
        <Palette :size="32" class="text-[var(--text-quaternary)]" />
        <span class="text-sm text-[var(--text-tertiary)]">Waiting for canvas...</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  MousePointer2,
  Hand,
  ZoomIn,
  ZoomOut,
  Maximize2,
  ExternalLink,
  Loader2,
  AlertCircle,
  Palette,
} from 'lucide-vue-next'
import CanvasStage from '@/components/canvas/editor/CanvasStage.vue'
import CanvasSyncBanner from '@/components/canvas/CanvasSyncBanner.vue'
import CanvasWorkspaceHeader from '@/components/canvas/CanvasWorkspaceHeader.vue'
import { useCanvasEditor } from '@/composables/useCanvasEditor'
import { useCanvasHistory } from '@/composables/useCanvasHistory'
import type { CanvasElement, CanvasSyncStatus, EditorState } from '@/types/canvas'
import type { CanvasUpdateEventData } from '@/types/event'

interface Props {
  sessionId: string
  projectId: string
  live: boolean
  refreshToken?: number
  latestUpdate?: CanvasUpdateEventData | null
  syncStatus?: CanvasSyncStatus
  pendingRemoteVersion?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  refreshToken: 0,
  latestUpdate: null,
  syncStatus: 'saved',
  pendingRemoteVersion: null,
})

const emit = defineEmits<{
  (e: 'apply-latest'): void
  (e: 'keep-draft'): void
}>()

const router = useRouter()
const stageRef = ref<InstanceType<typeof CanvasStage> | null>(null)

const {
  project,
  editorState,
  loading,
  activePage,
  elements,
  loadProject,
  updateElement,
  selectElement,
  clearSelection,
  setTool,
  setZoom,
  zoomIn,
  zoomOut,
  resetZoom,
  setPan,
} = useCanvasEditor()

const { pushState } = useCanvasHistory()

const error = ref<string | null>(null)

const elementCount = computed(() => elements.value.length)
const projectTitle = computed(() => props.latestUpdate?.project_name || project.value?.name || 'Canvas workspace')
const projectVersion = computed(() => props.latestUpdate?.version ?? project.value?.version ?? 0)
const headerElementCount = computed(() => props.latestUpdate?.element_count ?? elementCount.value)
const effectiveSyncStatus = computed<CanvasSyncStatus>(() => props.syncStatus)

const operationLabel = computed(() => {
  const rawOperation = props.latestUpdate?.operation || (props.live ? 'agent sketching' : 'manual review')
  return rawOperation.replace(/_/g, ' ')
})

const bannerState = computed(() => {
  if (props.syncStatus === 'conflict') {
    return {
      status: 'conflict' as const,
      title: 'Agent updated this canvas',
      description: props.pendingRemoteVersion !== null
        ? `A newer remote version (v${props.pendingRemoteVersion}) is ready to apply.`
        : 'A newer remote version is ready to apply.',
      primaryActionLabel: 'Apply latest',
      secondaryActionLabel: 'Keep my draft',
    }
  }

  if (props.syncStatus === 'stale') {
    return {
      status: 'stale' as const,
      title: 'Your draft is behind the latest agent canvas',
      description: props.pendingRemoteVersion !== null
        ? `Reload v${props.pendingRemoteVersion} when you are ready to pick up the agent changes.`
        : 'Reload the newer server version when you are ready to pick up the agent changes.',
      primaryActionLabel: 'Reload canvas',
      secondaryActionLabel: '',
    }
  }

  return null
})

// In live mode, force 'hand' tool and disable selection for read-only viewing
const effectiveEditorState = computed<EditorState>(() => {
  if (props.live) {
    return {
      ...editorState.value,
      activeTool: 'hand',
      selectedElementIds: [],
    }
  }
  return editorState.value
})

// Debounce refresh to avoid flooding API during rapid SSE events
let refreshTimer: ReturnType<typeof setTimeout> | null = null
const REFRESH_DEBOUNCE_MS = 500

function scheduleRefresh(options: { fitToView?: boolean } = {}) {
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => {
    void refresh(options)
  }, REFRESH_DEBOUNCE_MS)
}

async function refresh(options: { fitToView?: boolean } = {}) {
  if (!props.projectId) return
  try {
    error.value = null
    await loadProject(props.projectId)
    if (options.fitToView) {
      await nextTick()
      fitToView()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load canvas'
  }
}

// Auto-fit viewport to content bounds
function fitToView() {
  if (!project.value || !activePage.value || !stageRef.value) {
    resetZoom()
    return
  }

  const els = activePage.value.elements.filter((el) => el.visible)
  if (els.length === 0) {
    resetZoom()
    return
  }

  // Calculate bounding box of all elements
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const el of els) {
    minX = Math.min(minX, el.x)
    minY = Math.min(minY, el.y)
    maxX = Math.max(maxX, el.x + el.width)
    maxY = Math.max(maxY, el.y + el.height)
  }

  // Use page bounds as minimum
  minX = Math.min(minX, 0)
  minY = Math.min(minY, 0)
  maxX = Math.max(maxX, project.value.width)
  maxY = Math.max(maxY, project.value.height)

  const stage = stageRef.value.getStage?.()
  if (!stage) {
    resetZoom()
    return
  }

  const stageWidth = stage.width()
  const stageHeight = stage.height()
  const contentWidth = maxX - minX
  const contentHeight = maxY - minY

  const PADDING = 40
  const scaleX = (stageWidth - PADDING * 2) / contentWidth
  const scaleY = (stageHeight - PADDING * 2) / contentHeight
  const newZoom = Math.max(0.1, Math.min(Math.min(scaleX, scaleY), 2))

  setZoom(newZoom)
  setPan(
    -minX * newZoom + PADDING,
    -minY * newZoom + PADDING,
  )
}

// Element interaction handlers (only active when not in live mode)
function handleElementSelect(elementId: string, multi: boolean) {
  if (props.live) return
  selectElement(elementId, multi)
}

function handleElementMove(elementId: string, x: number, y: number) {
  if (props.live) return
  pushState(project.value!.pages)
  updateElement(elementId, { x, y })
}

function handleElementTransform(elementId: string, updates: Partial<CanvasElement>) {
  if (props.live) return
  pushState(project.value!.pages)
  updateElement(elementId, updates)
}

function handleStageClick() {
  if (props.live) return
  clearSelection()
}

function handleWheel(payload: {
  deltaY: number
  ctrl: boolean
  pointerX: number
  pointerY: number
  stageX: number
  stageY: number
}) {
  if (payload.ctrl) {
    // Pinch-zoom: zoom toward pointer position
    const scaleBy = 1.1
    const oldZoom = editorState.value.zoom
    const newZoom = payload.deltaY < 0 ? oldZoom * scaleBy : oldZoom / scaleBy
    const clampedZoom = Math.max(0.1, Math.min(newZoom, 5))

    const mousePointTo = {
      x: (payload.pointerX - payload.stageX) / oldZoom,
      y: (payload.pointerY - payload.stageY) / oldZoom,
    }

    setZoom(clampedZoom)
    setPan(
      payload.pointerX - mousePointTo.x * clampedZoom,
      payload.pointerY - mousePointTo.y * clampedZoom,
    )
  } else {
    // Scroll-pan
    setPan(
      editorState.value.panX - (payload.deltaY < 0 ? -30 : 30),
      editorState.value.panY,
    )
  }
}

function handlePanChange(x: number, y: number) {
  setPan(x, y)
}

function openFullEditor() {
  if (!props.projectId) return
  router.push({
    path: `/chat/canvas/${props.projectId}`,
    query: props.sessionId ? { sessionId: props.sessionId } : undefined,
  })
}

watch(
  [() => props.projectId, () => props.refreshToken ?? 0],
  ([newId], [previousId]) => {
    if (newId) {
      scheduleRefresh({ fitToView: newId !== previousId })
    }
  },
  { immediate: true },
)

// Watch live prop — when agent finishes (live → false), switch to select tool and fit view
watch(
  () => props.live,
  (isLive, wasLive) => {
    if (wasLive && !isLive) {
      // Agent finished — switch to interactive mode
      setTool('select')
      // Final refresh to get the complete state
      void refresh({ fitToView: true })
    }
  },
)

onUnmounted(() => {
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.canvas-live-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  gap: var(--space-3);
  padding: var(--space-3);
  background:
    radial-gradient(circle at top right, rgba(17, 24, 39, 0.04), transparent 28%),
    linear-gradient(180deg, rgba(17, 24, 39, 0.02), transparent 32%);
}

.canvas-live-header {
  flex-shrink: 0;
  min-height: 36px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
}

.canvas-live-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 0 var(--space-2);
}

.canvas-live-summary__status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.canvas-live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3b82f6;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}

.canvas-live-summary__eyebrow {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.canvas-live-summary__details {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
  font-size: 12px;
  color: var(--text-tertiary);
}

.canvas-live-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.canvas-tool-group {
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 2px;
  background: var(--fill-tsp-gray-main);
  border-radius: 6px;
}

.canvas-tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}

.canvas-tool-btn:hover {
  color: var(--text-primary);
  background: var(--background-white-main);
}

.canvas-tool-btn.active {
  color: var(--text-primary);
  background: var(--background-white-main);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.canvas-tool-spacer {
  flex: 1;
}

.canvas-open-editor-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.canvas-open-editor-btn:hover {
  color: var(--text-primary);
  background: var(--background-white-main);
  border-color: var(--border-main);
}

.canvas-live-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.03), rgba(17, 24, 39, 0.01)),
    #e8e6e1;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.canvas-live-loading,
.canvas-live-error,
.canvas-live-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  width: 100%;
}

.canvas-retry-btn {
  margin-top: 4px;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  cursor: pointer;
}

.canvas-retry-btn:hover {
  background: var(--background-white-main);
  border-color: var(--border-main);
}
</style>
