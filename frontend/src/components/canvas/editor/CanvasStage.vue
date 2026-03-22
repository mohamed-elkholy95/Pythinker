<template>
  <div ref="containerRef" class="canvas-stage-container">
    <v-stage
      ref="stageRef"
      :config="stageConfig"
      @mousedown="handleStageMouseDown"
      @dragmove="handleStageDragMove"
      @dragend="handleStageDragEnd"
      @wheel="handleWheel"
    >
      <!-- Background layer (non-interactive) -->
      <v-layer :config="{ listening: false }">
        <v-rect :config="backgroundConfig" />
      </v-layer>

      <!-- Objects layer (interactive) -->
      <v-layer ref="objectLayerRef">
        <template v-for="element in sortedElements" :key="element.id">
          <v-rect
            v-if="element.type === 'rectangle'"
            :config="getRectConfig(element)"
            @click="handleElementClick($event, element)"
            @dragend="handleDragEnd($event, element)"
            @transformend="handleTransformEnd($event, element)"
          />
          <v-ellipse
            v-else-if="element.type === 'ellipse'"
            :config="getEllipseConfig(element)"
            @click="handleElementClick($event, element)"
            @dragend="handleDragEnd($event, element)"
            @transformend="handleTransformEnd($event, element)"
          />
          <v-text
            v-else-if="element.type === 'text'"
            :config="getTextConfig(element)"
            @click="handleElementClick($event, element)"
            @dragend="handleDragEnd($event, element)"
            @transformend="handleTransformEnd($event, element)"
          />
          <v-image
            v-else-if="element.type === 'image'"
            :config="getImageConfig(element)"
            @click="handleElementClick($event, element)"
            @dragend="handleDragEnd($event, element)"
            @transformend="handleTransformEnd($event, element)"
          />
          <v-line
            v-else-if="element.type === 'line' || element.type === 'path'"
            :config="getLineConfig(element)"
            @click="handleElementClick($event, element)"
            @dragend="handleDragEnd($event, element)"
            @transformend="handleTransformEnd($event, element)"
          />
        </template>
      </v-layer>

      <!-- Highlight layer (non-interactive) -->
      <v-layer ref="highlightLayerRef" :config="{ listening: false }">
        <template v-for="element in highlightedElements" :key="`highlight-${element.id}`">
          <v-rect :config="getHighlightConfig(element)" />
        </template>
      </v-layer>

      <!-- Selection / transformer layer -->
      <v-layer>
        <v-transformer
          ref="transformerRef"
          :config="transformerConfig"
        />
      </v-layer>
    </v-stage>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import type Konva from 'konva'
import type { CanvasElement, EditorState, Fill, Stroke } from '@/types/canvas'

interface Props {
  elements: CanvasElement[]
  selectedElementIds: string[]
  highlightedElementIds?: string[]
  editorState: EditorState
  pageWidth: number
  pageHeight: number
  pageBackground: string
}

interface WheelPayload {
  deltaY: number
  ctrl: boolean
  pointerX: number
  pointerY: number
  stageX: number
  stageY: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'element-select', elementId: string, multi: boolean): void
  (e: 'element-move', elementId: string, x: number, y: number): void
  (e: 'element-transform', elementId: string, updates: Partial<CanvasElement>): void
  (e: 'stage-click'): void
  (e: 'wheel', payload: WheelPayload): void
  (e: 'pan-change', x: number, y: number): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const stageRef = ref<{ getNode: () => Konva.Stage } | null>(null)
const objectLayerRef = ref<{ getNode: () => Konva.Layer } | null>(null)
const highlightLayerRef = ref<{ getNode: () => Konva.Layer } | null>(null)
const transformerRef = ref<{ getNode: () => Konva.Transformer } | null>(null)

const containerWidth = ref(800)
const containerHeight = ref(600)

let resizeObserver: ResizeObserver | null = null

// Image cache for v-image elements (LRU-like with max size)
const IMAGE_CACHE_MAX = 50
const imageCache = ref<Record<string, HTMLImageElement>>({})
const imageCacheOrder: string[] = []

function loadImage(src: string): HTMLImageElement | undefined {
  if (imageCache.value[src]) return imageCache.value[src]

  const img = new Image()
  img.onload = () => {
    // Evict oldest entry if cache is full
    if (imageCacheOrder.length >= IMAGE_CACHE_MAX) {
      const evictKey = imageCacheOrder.shift()!
      const { [evictKey]: _evicted, ...rest } = imageCache.value
      imageCache.value = { ...rest, [src]: img }
    } else {
      imageCache.value = { ...imageCache.value, [src]: img }
    }
    imageCacheOrder.push(src)
    objectLayerRef.value?.getNode()?.batchDraw()
  }
  img.onerror = () => {
    // Silently handle broken image URLs — don't pollute cache
  }
  img.src = src
  return undefined
}

function clearImageCache() {
  imageCache.value = {}
  imageCacheOrder.length = 0
}

const sortedElements = computed(() =>
  [...props.elements]
    .filter((el) => el.visible)
    .sort((a, b) => a.z_index - b.z_index)
)

const highlightedIdSet = computed(() => new Set(props.highlightedElementIds ?? []))
const highlightedElements = computed(() =>
  sortedElements.value.filter((element) => highlightedIdSet.value.has(element.id))
)

const stageConfig = computed(() => ({
  width: containerWidth.value,
  height: containerHeight.value,
  scaleX: props.editorState.zoom,
  scaleY: props.editorState.zoom,
  x: props.editorState.panX,
  y: props.editorState.panY,
  draggable: props.editorState.activeTool === 'hand',
}))

const backgroundConfig = computed(() => ({
  x: 0,
  y: 0,
  width: props.pageWidth,
  height: props.pageHeight,
  fill: props.pageBackground || '#ffffff',
}))

const transformerConfig = computed(() => ({
  rotateEnabled: true,
  enabledAnchors: [
    'top-left', 'top-center', 'top-right',
    'middle-left', 'middle-right',
    'bottom-left', 'bottom-center', 'bottom-right',
  ],
  boundBoxFunc: (oldBox: Konva.Box, newBox: Konva.Box) => {
    if (newBox.width < 5 || newBox.height < 5) return oldBox
    return newBox
  },
}))

function isElementDraggable(element: CanvasElement): boolean {
  return props.editorState.activeTool === 'select' && !element.locked
}

function extractFillColor(fill?: Fill): string {
  if (!fill) return 'transparent'
  if (fill.type === 'solid') return fill.color
  return 'transparent'
}

function extractStroke(stroke?: Stroke): { stroke: string; strokeWidth: number } {
  if (!stroke) return { stroke: '', strokeWidth: 0 }
  return {
    stroke: stroke.color || '',
    strokeWidth: stroke.width || 0,
  }
}

function getBaseConfig(element: CanvasElement): Record<string, unknown> {
  const { stroke, strokeWidth } = extractStroke(element.stroke)
  return {
    id: element.id,
    name: element.id,
    x: element.x,
    y: element.y,
    rotation: element.rotation,
    scaleX: element.scale_x,
    scaleY: element.scale_y,
    opacity: element.opacity,
    draggable: isElementDraggable(element),
    stroke,
    strokeWidth,
    perfectDrawEnabled: false,
  }
}

function getRectConfig(element: CanvasElement): Record<string, unknown> {
  return {
    ...getBaseConfig(element),
    width: element.width,
    height: element.height,
    fill: extractFillColor(element.fill),
    cornerRadius: element.corner_radius,
  }
}

function getEllipseConfig(element: CanvasElement): Record<string, unknown> {
  return {
    ...getBaseConfig(element),
    radiusX: element.width / 2,
    radiusY: element.height / 2,
    fill: extractFillColor(element.fill),
    offsetX: 0,
    offsetY: 0,
  }
}

function getTextConfig(element: CanvasElement): Record<string, unknown> {
  const ts = element.text_style
  return {
    ...getBaseConfig(element),
    width: element.width,
    height: element.height,
    text: element.text || '',
    fontSize: ts?.font_size ?? 16,
    fontFamily: ts?.font_family ?? 'Libre Baskerville',
    fontStyle: ts?.font_style ?? 'normal',
    fontVariant: undefined,
    align: ts?.text_align ?? 'left',
    verticalAlign: ts?.vertical_align ?? 'top',
    lineHeight: ts?.line_height ?? 1.2,
    letterSpacing: ts?.letter_spacing ?? 0,
    fill: extractFillColor(element.fill),
    wrap: 'word',
  }
}

function getImageConfig(element: CanvasElement): Record<string, unknown> {
  const img = element.src ? loadImage(element.src) : undefined
  return {
    ...getBaseConfig(element),
    width: element.width,
    height: element.height,
    image: img,
  }
}

function getLineConfig(element: CanvasElement): Record<string, unknown> {
  return {
    ...getBaseConfig(element),
    points: element.points || [],
    fill: extractFillColor(element.fill),
    closed: element.type === 'path',
    tension: element.type === 'path' ? 0.5 : 0,
  }
}

function getHighlightBounds(element: CanvasElement): {
  x: number
  y: number
  width: number
  height: number
} {
  if ((element.type === 'line' || element.type === 'path') && Array.isArray(element.points) && element.points.length >= 2) {
    let minX = Number.POSITIVE_INFINITY
    let minY = Number.POSITIVE_INFINITY
    let maxX = Number.NEGATIVE_INFINITY
    let maxY = Number.NEGATIVE_INFINITY

    for (let index = 0; index < element.points.length - 1; index += 2) {
      const px = element.points[index]
      const py = element.points[index + 1]
      if (!Number.isFinite(px) || !Number.isFinite(py)) continue
      minX = Math.min(minX, px)
      minY = Math.min(minY, py)
      maxX = Math.max(maxX, px)
      maxY = Math.max(maxY, py)
    }

    if (Number.isFinite(minX) && Number.isFinite(minY) && Number.isFinite(maxX) && Number.isFinite(maxY)) {
      return {
        x: element.x + minX,
        y: element.y + minY,
        width: Math.max(12, maxX - minX),
        height: Math.max(12, maxY - minY),
      }
    }
  }

  return {
    x: element.x,
    y: element.y,
    width: Math.max(12, Math.abs(element.width * element.scale_x)),
    height: Math.max(12, Math.abs(element.height * element.scale_y)),
  }
}

function getHighlightConfig(element: CanvasElement): Record<string, unknown> {
  const bounds = getHighlightBounds(element)
  return {
    x: bounds.x - 6,
    y: bounds.y - 6,
    width: bounds.width + 12,
    height: bounds.height + 12,
    stroke: 'rgba(59, 130, 246, 0.72)',
    strokeWidth: 2,
    dash: [8, 6],
    cornerRadius: Math.min(18, element.corner_radius + 8),
    shadowColor: 'rgba(59, 130, 246, 0.25)',
    shadowBlur: 16,
    listening: false,
    perfectDrawEnabled: false,
  }
}

function handleStageMouseDown(e: Konva.KonvaEventObject<MouseEvent>) {
  // If the click is on the stage background (not on any shape), deselect
  const clickedOnEmpty = e.target === e.target.getStage()
  if (clickedOnEmpty) {
    emit('stage-click')
  }
}

function handleStageDragMove(e: Konva.KonvaEventObject<DragEvent>) {
  const stage = e.target.getStage()
  if (!stage) return
  emit('pan-change', stage.x(), stage.y())
}

function handleStageDragEnd(e: Konva.KonvaEventObject<DragEvent>) {
  const stage = e.target.getStage()
  if (!stage) return
  emit('pan-change', stage.x(), stage.y())
}

function handleElementClick(e: Konva.KonvaEventObject<MouseEvent>, element: CanvasElement) {
  if (props.editorState.activeTool !== 'select') return
  e.cancelBubble = true
  const multi = e.evt.shiftKey || e.evt.metaKey || e.evt.ctrlKey
  emit('element-select', element.id, multi)
}

function handleDragEnd(e: Konva.KonvaEventObject<MouseEvent>, element: CanvasElement) {
  const node = e.target
  emit('element-move', element.id, node.x(), node.y())
}

function handleTransformEnd(e: Konva.KonvaEventObject<Event>, element: CanvasElement) {
  const node = e.target
  emit('element-transform', element.id, {
    x: node.x(),
    y: node.y(),
    width: Math.max(5, node.width() * node.scaleX()),
    height: Math.max(5, node.height() * node.scaleY()),
    rotation: node.rotation(),
    scale_x: 1,
    scale_y: 1,
  })
  // Reset scale after applying to width/height
  node.scaleX(1)
  node.scaleY(1)
}

function handleWheel(e: Konva.KonvaEventObject<WheelEvent>) {
  e.evt.preventDefault()
  const ctrl = e.evt.ctrlKey || e.evt.metaKey
  const stage = stageRef.value?.getNode()
  const pointer = stage?.getPointerPosition()
  emit('wheel', {
    deltaY: e.evt.deltaY,
    ctrl,
    pointerX: pointer?.x ?? containerWidth.value / 2,
    pointerY: pointer?.y ?? containerHeight.value / 2,
    stageX: stage?.x() ?? props.editorState.panX,
    stageY: stage?.y() ?? props.editorState.panY,
  })
}

function updateTransformer() {
  if (!transformerRef.value || !objectLayerRef.value) return
  const transformer = transformerRef.value.getNode()
  const layer = objectLayerRef.value.getNode()
  const selectedIds = new Set(props.selectedElementIds)

  const selectedNodes = layer.getChildren((node: Konva.Node) =>
    selectedIds.has(node.name())
  )

  transformer.nodes(selectedNodes)
  transformer.getLayer()?.batchDraw()
  highlightLayerRef.value?.getNode()?.batchDraw()
}

watch(
  () => props.selectedElementIds,
  () => nextTick(updateTransformer),
  { deep: true }
)

watch(
  () => props.elements,
  () => nextTick(updateTransformer),
  { deep: true }
)

watch(
  () => props.highlightedElementIds,
  () => nextTick(() => {
    highlightLayerRef.value?.getNode()?.batchDraw()
  }),
  { deep: true }
)

onMounted(() => {
  if (containerRef.value) {
    const rect = containerRef.value.getBoundingClientRect()
    containerWidth.value = Math.floor(rect.width)
    containerHeight.value = Math.floor(rect.height)

    resizeObserver = new ResizeObserver(() => {
      if (!containerRef.value) return
      const r = containerRef.value.getBoundingClientRect()
      containerWidth.value = Math.floor(r.width)
      containerHeight.value = Math.floor(r.height)
    })
    resizeObserver.observe(containerRef.value)
  }
  nextTick(updateTransformer)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  clearImageCache()
})

defineExpose({
  getStage: () => stageRef.value?.getNode(),
})
</script>

<style scoped>
.canvas-stage-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--fill-tsp-gray-main, #f5f5f5);
  cursor: v-bind("props.editorState.activeTool === 'hand' ? 'grab' : 'default'");
}
</style>
