<template>
  <div
    ref="containerRef"
    class="konva-live-stage"
    :class="{
      'annotation-mode': annotationLayer.isActive.value,
      'panning': zoomCtrl.isPanning.value,
    }"
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
              }"
            />
            <v-text
              :config="{
                x: 12,
                y: -8,
                text: action.label,
                fontSize: 11,
                fontFamily: 'system-ui, sans-serif',
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
            }"
          />
          <!-- Navigate: flash bar at top -->
          <v-rect
            v-else-if="action.type === 'navigate'"
            :config="{
              x: 0,
              y: 0,
              width: frameDimensions.width || 1280,
              height: 4,
              fill: action.color,
              opacity: action.opacity,
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
              }"
            />
            <v-circle
              :config="{
                x: 0,
                y: 0,
                radius: action.radius * 0.4,
                fill: action.color,
                opacity: action.opacity,
              }"
            />
            <v-text
              :config="{
                x: action.radius + 6,
                y: -8,
                text: action.label,
                fontSize: 11,
                fontFamily: 'system-ui, sans-serif',
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
              fontFamily: 'system-ui, sans-serif',
              fill: ann.style.color,
              opacity: ann.style.opacity,
              listening: false,
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
  }>(),
  {
    showStats: false,
    showAgentActions: true,
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
  width: frameDimensions.value.width || 1280,
  height: frameDimensions.value.height || 1024,
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

function handleWheel(e: WheelEvent): void {
  if (e.ctrlKey || e.metaKey) {
    // Ctrl+scroll = zoom to point
    const rect = containerRef.value?.getBoundingClientRect()
    if (!rect) return
    const pointerX = e.clientX - rect.left
    const pointerY = e.clientY - rect.top
    zoomCtrl.zoomToPoint(pointerX, pointerY, e.deltaY)
  }
  // Note: regular scroll is not intercepted (allows page scroll)
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
    const stage = stageRef.value?.getNode()
    if (!stage) return
    const pos = stage.getPointerPosition()
    if (!pos) return
    // Convert to stage space (undo zoom/pan)
    const stageX = (pos.x - zoomCtrl.panX.value) / zoomCtrl.zoom.value
    const stageY = (pos.y - zoomCtrl.panY.value) / zoomCtrl.zoom.value
    annotationLayer.startDrawing(stageX, stageY)
  }
}

function handleStageMouseMove(e: Konva.KonvaEventObject<MouseEvent>): void {
  // Pan drag
  if (_isPanDrag) {
    zoomCtrl.setPan(
      e.evt.clientX - _panStartX,
      e.evt.clientY - _panStartY,
    )
    return
  }

  // Annotation drawing
  if (annotationLayer.drawingElement.value) {
    const stage = stageRef.value?.getNode()
    if (!stage) return
    const pos = stage.getPointerPosition()
    if (!pos) return
    const stageX = (pos.x - zoomCtrl.panX.value) / zoomCtrl.zoom.value
    const stageY = (pos.y - zoomCtrl.panY.value) / zoomCtrl.zoom.value
    annotationLayer.continueDrawing(stageX, stageY)
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
    const stage = stageRef.value?.getNode()
    if (!stage) return
    const pos = stage.getPointerPosition()
    if (!pos) return
    const stageX = (pos.x - zoomCtrl.panX.value) / zoomCtrl.zoom.value
    const stageY = (pos.y - zoomCtrl.panY.value) / zoomCtrl.zoom.value
    annotationLayer.startDrawing(stageX, stageY)
    e.evt.preventDefault()
  }
}

function handleStageTouchMove(e: Konva.KonvaEventObject<TouchEvent>): void {
  if (annotationLayer.drawingElement.value) {
    const stage = stageRef.value?.getNode()
    if (!stage) return
    const pos = stage.getPointerPosition()
    if (!pos) return
    const stageX = (pos.x - zoomCtrl.panX.value) / zoomCtrl.zoom.value
    const stageY = (pos.y - zoomCtrl.panY.value) / zoomCtrl.zoom.value
    annotationLayer.continueDrawing(stageX, stageY)
    e.evt.preventDefault()
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
 */
function fitToScreen(): void {
  zoomCtrl.fitToScreen(
    containerWidth.value,
    containerHeight.value,
    frameDimensions.value,
  )
}

/**
 * Reset screencast state (e.g., on reconnect).
 */
function resetScreencast(): void {
  screencast.reset()
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
  const rect = containerRef.value.getBoundingClientRect()
  const w = Math.floor(rect.width)
  const h = Math.floor(rect.height)
  if (w !== containerWidth.value || h !== containerHeight.value) {
    containerWidth.value = w
    containerHeight.value = h
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  // Setup resize observer
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => updateContainerSize())
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

    // Retry if critical nodes not ready
    if ((!imageNode || !screencastLayer) && attempt < 3) {
      setTimeout(() => bindKonvaNodes(attempt + 1), 50)
    }
  }
  nextTick(() => bindKonvaNodes())
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  screencast.unbindImageNode()
  agentOverlay.unbindLayer()
  annotationLayer.unbind()
})

// Auto-fit on first frame
watch(
  () => screencast.hasFrame.value,
  (hasFrame) => {
    if (hasFrame && zoomCtrl.zoom.value === 1 && zoomCtrl.panX.value === 0) {
      nextTick(() => fitToScreen())
    }
  },
)

// ---------------------------------------------------------------------------
// Expose
// ---------------------------------------------------------------------------

defineExpose({
  // Frame management
  pushFrame,
  resetScreencast,
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
</style>
