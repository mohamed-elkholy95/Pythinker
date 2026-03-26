<template>
  <div
    ref="containerRef"
    class="konva-live-stage"
    :class="{
      'annotation-mode': annotationLayer.isActive.value,
      'panning': zoomCtrl.isPanning.value,
    }"
    :style="streamCursorStyle"
    @wheel.prevent="handleWheel"
  >
    <v-stage
      ref="stageRef"
      :config="stageConfig"
      @mousedown="handleStageMouseDown"
      @mousemove="handleStageMouseMove"
      @mouseup="handleStageMouseUp"
      @touchstart="handleStageTouchStart"
      @touchmove="handleStageTouchMove"
      @touchend="handleStageTouchEnd"
    >
      <!-- Layer 1: CDP Screencast frame (non-interactive, high perf) -->
      <v-layer ref="screencastLayerRef" :config="{ listening: false }">
        <v-image ref="screencastImageRef" :config="screencastImageConfig" />
      </v-layer>

      <!-- Layer 2: Agent action overlay (non-interactive, animated) -->
      <v-layer ref="overlayLayerRef" :config="{ listening: false }">
        <template v-for="action in overlayConfigs" :key="action.id">
          <!-- Click: expanding ring -->
          <v-circle
            v-if="action.type === 'click'"
            :config="{
              x: action.x,
              y: action.y,
              radius: action.radius,
              stroke: action.color,
              strokeWidth: 2.5,
              opacity: action.opacity,
              perfectDrawEnabled: false,
            }"
          />
          <!-- Type: pulsing dot with label -->
          <v-group
            v-else-if="action.type === 'type'"
            :config="{ x: action.x, y: action.y }"
          >
            <v-circle
              :config="{
                x: 0,
                y: 0,
                radius: 6,
                fill: action.color,
                opacity: action.opacity,
                perfectDrawEnabled: false,
              }"
            />
            <v-text
              :config="{
                x: 12,
                y: -8,
                text: action.label,
                fontSize: 11,
                fontFamily: 'Arial, sans-serif',
                fill: action.color,
                opacity: action.opacity,
              }"
            />
          </v-group>
          <!-- Scroll: directional arrow -->
          <v-arrow
            v-else-if="action.type === 'scroll'"
            :config="{
              x: action.x,
              y: action.y - 20,
              points: [0, 0, 0, 40],
              stroke: action.color,
              strokeWidth: 3,
              pointerLength: 10,
              pointerWidth: 8,
              opacity: action.opacity,
              perfectDrawEnabled: false,
            }"
          />
          <!-- Navigate: flash bar at top -->
          <v-rect
            v-else-if="action.type === 'navigate'"
            :config="{
              x: 0,
              y: 0,
              width: frameDimensions.width || SANDBOX_WIDTH,
              height: 4,
              fill: action.color,
              opacity: action.opacity,
              perfectDrawEnabled: false,
            }"
          />
          <!-- Default: dot + label -->
          <v-group v-else :config="{ x: action.x, y: action.y }">
            <v-circle
              :config="{
                x: 0,
                y: 0,
                radius: action.radius,
                fill: action.color,
                opacity: action.opacity * 0.4,
                perfectDrawEnabled: false,
              }"
            />
            <v-circle
              :config="{
                x: 0,
                y: 0,
                radius: action.radius * 0.4,
                fill: action.color,
                opacity: action.opacity,
                perfectDrawEnabled: false,
              }"
            />
            <v-text
              :config="{
                x: action.radius + 6,
                y: -8,
                text: action.label,
                fontSize: 11,
                fontFamily: 'Arial, sans-serif',
                fill: action.color,
                opacity: action.opacity,
              }"
            />
          </v-group>
        </template>
      </v-layer>

      <!-- Layer 3: User annotations (interactive when drawing) -->
      <v-layer
        ref="annotationLayerRef"
        :config="{ listening: annotationLayer.isActive.value }"
      >
        <template v-for="ann in annotationConfigs" :key="ann.id">
          <!-- Pen: freehand line -->
          <v-line
            v-if="ann.type === 'pen'"
            :config="{
              points: ann.points || [],
              stroke: ann.style.color,
              strokeWidth: ann.style.strokeWidth,
              opacity: ann.style.opacity,
              lineCap: 'round',
              lineJoin: 'round',
              tension: 0.3,
              listening: false,
              perfectDrawEnabled: false,
            }"
          />
          <!-- Rectangle -->
          <v-rect
            v-else-if="ann.type === 'rectangle'"
            :config="{
              x: ann.x ?? 0,
              y: ann.y ?? 0,
              width: ann.width ?? 0,
              height: ann.height ?? 0,
              stroke: ann.style.color,
              strokeWidth: ann.style.strokeWidth,
              opacity: ann.style.opacity,
              listening: false,
              perfectDrawEnabled: false,
            }"
          />
          <!-- Ellipse -->
          <v-ellipse
            v-else-if="ann.type === 'ellipse'"
            :config="{
              x: ann.x ?? 0,
              y: ann.y ?? 0,
              radiusX: Math.abs(ann.width ?? 0) / 2,
              radiusY: Math.abs(ann.height ?? 0) / 2,
              stroke: ann.style.color,
              strokeWidth: ann.style.strokeWidth,
              opacity: ann.style.opacity,
              listening: false,
              perfectDrawEnabled: false,
            }"
          />
          <!-- Arrow -->
          <v-arrow
            v-else-if="ann.type === 'arrow'"
            :config="{
              points: ann.points || [],
              stroke: ann.style.color,
              strokeWidth: ann.style.strokeWidth,
              opacity: ann.style.opacity,
              pointerLength: 12,
              pointerWidth: 10,
              fill: ann.style.color,
              listening: false,
              perfectDrawEnabled: false,
            }"
          />
          <!-- Text -->
          <v-text
            v-else-if="ann.type === 'text'"
            :config="{
              x: ann.x ?? 0,
              y: ann.y ?? 0,
              text: ann.text || 'Text',
              fontSize: ann.style.fontSize ?? 16,
              fontFamily: 'Arial, sans-serif',
              fill: ann.style.color,
              opacity: ann.style.opacity,
              listening: false,
              perfectDrawEnabled: false,
            }"
          />
        </template>
      </v-layer>
    </v-stage>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import type Konva from 'konva'
import { useKonvaScreencast } from '@/composables/useKonvaScreencast'
import { useLiveViewerZoom } from '@/composables/useLiveViewerZoom'
import { useAgentActionOverlay } from '@/composables/useAgentActionOverlay'
import { useAnnotationLayer } from '@/composables/useAnnotationLayer'
import type { ToolEventData } from '@/types/event'
import { SANDBOX_WIDTH, SANDBOX_HEIGHT } from '@/types/liveViewer'
import { getApplePointerCursorCss } from '@/utils/appleCursorStyle'

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

const props = withDefaults(
  defineProps<{
    /** Whether the stage is active and should render */
    enabled: boolean
    /** Show debug stats */
    showStats?: boolean
    /** Show agent action overlay */
    showAgentActions?: boolean
    /** Hide the local browser cursor over the stage in passive viewing mode */
    hideLocalCursor?: boolean
  }>(),
  {
    showStats: false,
    showAgentActions: true,
    hideLocalCursor: false,
  },
)

const emit = defineEmits<{
  (e: 'frame-received'): void
}>()

// ---------------------------------------------------------------------------
// Refs
// ---------------------------------------------------------------------------

const containerRef = ref<HTMLElement | null>(null)
const stageRef = ref<{ getNode: () => Konva.Stage } | null>(null)
const screencastLayerRef = ref<{ getNode: () => Konva.Layer } | null>(null)
const screencastImageRef = ref<{ getNode: () => Konva.Image } | null>(null)
const overlayLayerRef = ref<{ getNode: () => Konva.Layer } | null>(null)
const annotationLayerRef = ref<{ getNode: () => Konva.Layer } | null>(null)

// Container dimensions (responsive)
const containerWidth = ref(800)
const containerHeight = ref(600)
let resizeObserver: ResizeObserver | null = null
let resizeFrame: number | null = null

// ---------------------------------------------------------------------------
// Composables
// ---------------------------------------------------------------------------

const screencast = useKonvaScreencast()
const zoomCtrl = useLiveViewerZoom()
const agentOverlay = useAgentActionOverlay()
const annotationLayer = useAnnotationLayer()

// Expose frame dimensions from screencast
const frameDimensions = screencast.frameDimensions

// ---------------------------------------------------------------------------
// Konva Stage Config
// ---------------------------------------------------------------------------

/** OS cursor over stream matches Apple pointer (agent overlay + hover). */
const streamCursorStyle = computed(() => (
  props.hideLocalCursor
    ? { cursor: 'default' }
    : { cursor: getApplePointerCursorCss() }
))

const stageConfig = computed(() => ({
  width: containerWidth.value,
  height: containerHeight.value,
  scaleX: zoomCtrl.zoom.value,
  scaleY: zoomCtrl.zoom.value,
  x: zoomCtrl.panX.value,
  y: zoomCtrl.panY.value,
}))

const screencastImageConfig = computed(() => ({
  x: 0,
  y: 0,
  width: frameDimensions.value.width || SANDBOX_WIDTH,
  height: frameDimensions.value.height || SANDBOX_HEIGHT,
  // Image source is set imperatively via bindImageNode
}))

// Overlay action configs (reactive)
const overlayConfigs = computed(() => agentOverlay.getActionConfigs())

// Annotation configs (reactive)
const annotationConfigs = computed(() => annotationLayer.getAnnotationConfigs())

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

// Pan tracking
let _panStartX = 0
let _panStartY = 0
let _isPanDrag = false

/**
 * Convert Konva pointer position to stage-space coordinates
 * by undoing the current zoom and pan transform.
 * Returns null if stage or pointer is unavailable.
 */
function getStagePointer(): { x: number; y: number } | null {
  const stage = stageRef.value?.getNode()
  if (!stage) return null
  const pos = stage.getPointerPosition()
  if (!pos) return null
  return {
    x: (pos.x - zoomCtrl.panX.value) / zoomCtrl.zoom.value,
    y: (pos.y - zoomCtrl.panY.value) / zoomCtrl.zoom.value,
  }
}

function handleWheel(e: WheelEvent): void {
  if (e.ctrlKey || e.metaKey) {
    const rect = containerRef.value?.getBoundingClientRect()
    if (!rect) return
    const pointerX = e.clientX - rect.left
    const pointerY = e.clientY - rect.top
    zoomCtrl.zoomToPoint(pointerX, pointerY, e.deltaY)
  }
}

function handleStageMouseDown(e: Konva.KonvaEventObject<MouseEvent>): void {
  // Middle mouse button or space key → pan
  if (e.evt.button === 1 || zoomCtrl.isPanning.value) {
    _isPanDrag = true
    _panStartX = e.evt.clientX - zoomCtrl.panX.value
    _panStartY = e.evt.clientY - zoomCtrl.panY.value
    e.evt.preventDefault()
    return
  }

  // Annotation drawing
  if (annotationLayer.isActive.value && e.evt.button === 0) {
    const pt = getStagePointer()
    if (pt) annotationLayer.startDrawing(pt.x, pt.y)
  }
}

function handleStageMouseMove(e: Konva.KonvaEventObject<MouseEvent>): void {
  if (_isPanDrag) {
    zoomCtrl.setPan(
      e.evt.clientX - _panStartX,
      e.evt.clientY - _panStartY,
    )
    return
  }

  if (annotationLayer.drawingElement.value) {
    const pt = getStagePointer()
    if (pt) annotationLayer.continueDrawing(pt.x, pt.y)
  }
}

function handleStageMouseUp(_e: Konva.KonvaEventObject<MouseEvent>): void {
  if (_isPanDrag) {
    _isPanDrag = false
    return
  }

  if (annotationLayer.drawingElement.value) {
    annotationLayer.finishDrawing()
  }
}

// Touch event handlers
function handleStageTouchStart(e: Konva.KonvaEventObject<TouchEvent>): void {
  if (annotationLayer.isActive.value) {
    const pt = getStagePointer()
    if (pt) {
      annotationLayer.startDrawing(pt.x, pt.y)
      e.evt.preventDefault()
    }
  }
}

function handleStageTouchMove(e: Konva.KonvaEventObject<TouchEvent>): void {
  if (annotationLayer.drawingElement.value) {
    const pt = getStagePointer()
    if (pt) {
      annotationLayer.continueDrawing(pt.x, pt.y)
      e.evt.preventDefault()
    }
  }
}

function handleStageTouchEnd(_e: Konva.KonvaEventObject<TouchEvent>): void {
  if (annotationLayer.drawingElement.value) {
    annotationLayer.finishDrawing()
  }
}

// ---------------------------------------------------------------------------
// Public API (exposed to parent)
// ---------------------------------------------------------------------------

/**
 * Push a binary frame to the screencast renderer.
 * Called by SandboxViewer when a WebSocket message arrives.
 */
function pushFrame(data: ArrayBuffer): void {
  screencast.pushFrame(data)
  emit('frame-received')
}

/**
 * Process an agent tool event for overlay visualization.
 */
function processToolEvent(event: ToolEventData): void {
  if (props.showAgentActions) {
    agentOverlay.processToolEvent(event)
  }
}

/**
 * Fit the view to show the entire screencast frame.
 * Returns false if fitting was not possible (degenerate dimensions).
 */
function fitToScreen(): boolean {
  return zoomCtrl.fitToScreen(
    containerWidth.value,
    containerHeight.value,
    frameDimensions.value,
  )
}

/**
 * Reset screencast state (e.g., on reconnect).
 * Also resets zoom/pan so auto-fit triggers properly for the new stream.
 */
function resetScreencast(): void {
  screencast.reset()
  zoomCtrl.resetZoom()
  _userHasManuallyZoomed = false
}

/**
 * Force frame dimensions to known values after crash recovery.
 * Delegates to the screencast composable and triggers auto-fit.
 */
function forceDimensionReset(width: number, height: number): void {
  screencast.forceDimensionReset(width, height)
  zoomCtrl.resetZoom()
  _userHasManuallyZoomed = false
}

/**
 * Start stats tracking.
 */
function startStats(): void {
  screencast.startStats()
}

/**
 * Stop stats tracking.
 */
function stopStats(): void {
  screencast.stopStats()
}

// ---------------------------------------------------------------------------
// Resize observer
// ---------------------------------------------------------------------------

function updateContainerSize(): void {
  if (!containerRef.value) return
  // Use offsetWidth/offsetHeight instead of getBoundingClientRect() because
  // offset dimensions return the CSS layout size BEFORE ancestor transforms.
  // getBoundingClientRect() returns post-transform visual size, which causes
  // double-scaling when inside a CSS-transformed parent (e.g. mini preview).
  const w = containerRef.value.offsetWidth
  const h = containerRef.value.offsetHeight
  if (w !== containerWidth.value || h !== containerHeight.value) {
    containerWidth.value = w
    containerHeight.value = h
  }
}

function scheduleContainerSizeUpdate(): void {
  if (resizeFrame !== null) return
  resizeFrame = window.requestAnimationFrame(() => {
    resizeFrame = null
    updateContainerSize()
  })
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  // Setup resize observer
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => scheduleContainerSizeUpdate())
    resizeObserver.observe(containerRef.value)
    updateContainerSize()
  }

  // Bind Konva nodes to composables.
  // vue-konva may need more than one tick to create Konva nodes,
  // so retry up to 3 times with 50ms backoff.
  function bindKonvaNodes(attempt = 0): void {
    const imageNode = screencastImageRef.value?.getNode()
    const screencastLayer = screencastLayerRef.value?.getNode()
    const overlayLayer = overlayLayerRef.value?.getNode()
    const annotationLayerNode = annotationLayerRef.value?.getNode()
    const stage = stageRef.value?.getNode()

    if (imageNode && screencastLayer) {
      screencast.bindImageNode(imageNode, screencastLayer)
    }
    if (overlayLayer) {
      agentOverlay.bindLayer(overlayLayer)
    }
    if (annotationLayerNode && stage) {
      annotationLayer.bind(annotationLayerNode, stage)
    }

    // Retry if critical nodes not ready (10 attempts × 100ms = 1s total).
    // vue-konva can take multiple ticks to create Konva nodes, especially
    // on slower renders or when the component tree is deep.
    if ((!imageNode || !screencastLayer) && attempt < 10) {
      setTimeout(() => bindKonvaNodes(attempt + 1), 100)
    }
  }
  nextTick(() => bindKonvaNodes())
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  if (resizeFrame !== null) {
    window.cancelAnimationFrame(resizeFrame)
    resizeFrame = null
  }
  screencast.unbindImageNode()
  agentOverlay.unbindLayer()
  annotationLayer.unbind()
  if (_fitRetryTimer) clearTimeout(_fitRetryTimer)
  if (_resizeDebounce) clearTimeout(_resizeDebounce)

  // Clear and destroy the Konva stage to prevent ghost frames during route transitions.
  // Without this, the last rendered screencast frame (e.g. Chrome's Google new-tab page)
  // remains painted on the canvas during the brief DOM teardown between route swaps.
  const stage = stageRef.value?.getNode()
  if (stage) {
    stage.clear()
    stage.destroy()
  }
})

// ---------------------------------------------------------------------------
// Auto-fit logic — ensures the screencast image fills the container properly
// across all lifecycle states: initial load, reconnect, container resize,
// frame dimension changes, and panel layout changes during active sessions.
// ---------------------------------------------------------------------------

/** Whether the user has manually zoomed/panned (disables auto-fit) */
let _userHasManuallyZoomed = false

/** Retry handle for deferred auto-fit when container is zero-sized */
let _fitRetryTimer: ReturnType<typeof setTimeout> | null = null
const _FIT_RETRY_INTERVAL = 100 // ms
const _FIT_MAX_RETRIES = 20 // 2s total

// Track user-initiated zoom/pan (wheel zoom or drag) to suppress auto-fit.
// Only set by the event handlers — fitToScreen() changes don't count.
let _suppressAutoFitTracker = false
watch([zoomCtrl.zoom, zoomCtrl.panX, zoomCtrl.panY], () => {
  if (_suppressAutoFitTracker) return
  _userHasManuallyZoomed = true
})

// Wrap fitToScreen to prevent the zoom watcher from misinterpreting auto-fit
// changes as user-initiated.
function _autoFit(): boolean {
  _suppressAutoFitTracker = true
  const ok = fitToScreen()
  nextTick(() => { _suppressAutoFitTracker = false })
  return ok
}

function _autoFitWithRetry(retries = 0): void {
  if (_fitRetryTimer) {
    clearTimeout(_fitRetryTimer)
    _fitRetryTimer = null
  }
  _suppressAutoFitTracker = true
  const ok = fitToScreen()
  nextTick(() => { _suppressAutoFitTracker = false })
  if (!ok && retries < _FIT_MAX_RETRIES) {
    _fitRetryTimer = setTimeout(() => _autoFitWithRetry(retries + 1), _FIT_RETRY_INTERVAL)
  }
}

// 1. Auto-fit on first frame arrival
watch(screencast.hasFrame, (hasFrame) => {
  if (hasFrame) {
    _userHasManuallyZoomed = false
    nextTick(() => _autoFitWithRetry())
  }
})

// 2. Auto-fit on container resize (unless user has manually zoomed)
let _resizeDebounce: ReturnType<typeof setTimeout> | null = null
watch([containerWidth, containerHeight], () => {
  if (!screencast.hasFrame.value || _userHasManuallyZoomed) return
  if (_resizeDebounce) clearTimeout(_resizeDebounce)
  _resizeDebounce = setTimeout(() => {
    _autoFit()
  }, 50)
})

// 3. Auto-fit on frame dimension change (new resolution from CDP)
watch(frameDimensions, (newDims, oldDims) => {
  if (!screencast.hasFrame.value) return
  if (newDims.width === oldDims.width && newDims.height === oldDims.height) return
  if (_userHasManuallyZoomed) return
  nextTick(() => _autoFit())
})

// ---------------------------------------------------------------------------
// Expose
// ---------------------------------------------------------------------------

defineExpose({
  // Frame management
  pushFrame,
  resetScreencast,
  forceDimensionReset,
  startStats,
  stopStats,

  // Agent action overlay
  processToolEvent,

  // Zoom controls
  zoomCtrl,
  fitToScreen,

  // Annotation controls
  annotationLayer,

  // Agent overlay controls
  agentOverlay,

  // Stats
  stats: screencast.stats,
  hasFrame: screencast.hasFrame,
  frameDimensions: screencast.frameDimensions,
})
</script>

<style scoped>
.konva-live-stage {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  background: transparent;
}

.konva-live-stage.annotation-mode {
  cursor: crosshair;
}

.konva-live-stage.panning {
  cursor: grab;
}

.konva-live-stage.panning:active {
  cursor: grabbing;
}

/* Ensure Konva canvases fill the container */
.konva-live-stage :deep(.konvajs-content) {
  position: absolute !important;
  top: 0;
  left: 0;
}

/* Konva defaults to `default` on the hit canvas — inherit Apple pointer from parent */
.konva-live-stage:not(.annotation-mode):not(.panning) :deep(canvas) {
  cursor: inherit !important;
}
</style>
