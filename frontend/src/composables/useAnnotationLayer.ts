/**
 * Annotation Layer Composable
 *
 * Manages user-drawn annotations on the live viewer.
 * Supports pen (freehand), rectangle, ellipse, arrow, text, and eraser tools.
 * Provides undo/redo, clear all, and coordinate transformation
 * from screen space to Konva stage space.
 */
import { ref, shallowRef, triggerRef, computed, onBeforeUnmount } from 'vue'
import type Konva from 'konva'
import type {
  AnnotationElement,
  AnnotationToolType,
  AnnotationStyle,
} from '@/types/liveViewer'
import { DEFAULT_ANNOTATION_STYLE } from '@/types/liveViewer'

/** Max undo history depth */
const MAX_HISTORY = 50

export function useAnnotationLayer() {
  /** Instance-scoped counter to prevent ID collisions across instances */
  let _annotationIdCounter = 0
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  /** All committed annotation elements */
  const annotations = ref<AnnotationElement[]>([])

  /** Whether annotation mode is active */
  const isActive = ref(false)

  /** Current drawing tool */
  const activeTool = ref<AnnotationToolType>('pen')

  /** Current style settings */
  const style = ref<AnnotationStyle>({ ...DEFAULT_ANNOTATION_STYLE })

  /** Element currently being drawn (null when idle) — shallowRef for perf during pen drawing */
  const drawingElement = shallowRef<AnnotationElement | null>(null)

  // Undo/redo stacks (JSON snapshots)
  const undoStack = ref<string[]>([])
  const redoStack = ref<string[]>([])
  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  const annotationCount = computed(() => annotations.value.length)

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------

  let _layer: Konva.Layer | null = null
  /** Start position for shape drawing (rect/ellipse) */
  let _drawStartX = 0
  let _drawStartY = 0

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Bind the annotation layer and stage (called once on mount).
   */
  function bind(layer: Konva.Layer, _stage: Konva.Stage): void {
    _layer = layer
  }

  /**
   * Unbind on teardown.
   */
  function unbind(): void {
    _layer = null
  }

  /**
   * Toggle annotation mode on/off.
   */
  function toggleActive(): void {
    isActive.value = !isActive.value
    if (!isActive.value) {
      _finishDrawing()
    }
  }

  /**
   * Set the active drawing tool.
   */
  function setTool(tool: AnnotationToolType): void {
    _finishDrawing()
    activeTool.value = tool
  }

  /**
   * Update style properties.
   */
  function setStyle(updates: Partial<AnnotationStyle>): void {
    style.value = { ...style.value, ...updates }
  }

  // ---------------------------------------------------------------------------
  // Drawing lifecycle (called from KonvaLiveStage event handlers)
  // ---------------------------------------------------------------------------

  /**
   * Start drawing at the given stage-space position.
   */
  function startDrawing(stageX: number, stageY: number): void {
    if (!isActive.value) return

    _drawStartX = stageX
    _drawStartY = stageY

    const id = `ann-${++_annotationIdCounter}`
    const currentStyle = { ...style.value }

    switch (activeTool.value) {
      case 'pen':
        drawingElement.value = {
          id,
          type: 'pen',
          points: [stageX, stageY],
          style: currentStyle,
          timestamp: Date.now(),
        }
        break

      case 'rectangle':
        drawingElement.value = {
          id,
          type: 'rectangle',
          x: stageX,
          y: stageY,
          width: 0,
          height: 0,
          style: currentStyle,
          timestamp: Date.now(),
        }
        break

      case 'ellipse':
        drawingElement.value = {
          id,
          type: 'ellipse',
          x: stageX,
          y: stageY,
          width: 0,
          height: 0,
          style: currentStyle,
          timestamp: Date.now(),
        }
        break

      case 'arrow':
        drawingElement.value = {
          id,
          type: 'arrow',
          points: [stageX, stageY, stageX, stageY],
          style: currentStyle,
          timestamp: Date.now(),
        }
        break

      case 'text':
        // Text is placed on click (no drag)
        _pushUndo()
        annotations.value = [
          ...annotations.value,
          {
            id,
            type: 'text',
            x: stageX,
            y: stageY,
            text: 'Text',
            style: currentStyle,
            timestamp: Date.now(),
          },
        ]
        redoStack.value = []
        break

      case 'eraser':
        // Eraser: check if any annotation is under this point
        _eraseAt(stageX, stageY)
        break
    }
  }

  /**
   * Continue drawing (mousemove/touchmove in stage space).
   * Mutates in-place + triggerRef to avoid allocating new objects every mousemove.
   */
  function continueDrawing(stageX: number, stageY: number): void {
    if (!drawingElement.value) return

    const el = drawingElement.value

    switch (el.type) {
      case 'pen':
        // Push points in-place (avoids spreading the full array every move)
        if (!el.points) el.points = []
        el.points.push(stageX, stageY)
        break

      case 'rectangle':
        el.width = stageX - _drawStartX
        el.height = stageY - _drawStartY
        break

      case 'ellipse':
        el.width = Math.abs(stageX - _drawStartX) * 2
        el.height = Math.abs(stageY - _drawStartY) * 2
        el.x = _drawStartX
        el.y = _drawStartY
        break

      case 'arrow':
        el.points = [_drawStartX, _drawStartY, stageX, stageY]
        break
    }

    // Notify Vue of in-place mutation without allocating a new object
    triggerRef(drawingElement)
    _layer?.batchDraw()
  }

  /**
   * Finish drawing (mouseup/touchend).
   */
  function finishDrawing(): void {
    _finishDrawing()
  }

  // ---------------------------------------------------------------------------
  // Undo / Redo
  // ---------------------------------------------------------------------------

  function undo(): void {
    if (undoStack.value.length === 0) return
    const current = JSON.stringify(annotations.value)
    redoStack.value = [...redoStack.value, current]
    const previous = undoStack.value[undoStack.value.length - 1]
    undoStack.value = undoStack.value.slice(0, -1)
    annotations.value = JSON.parse(previous) as AnnotationElement[]
    _layer?.batchDraw()
  }

  function redo(): void {
    if (redoStack.value.length === 0) return
    const current = JSON.stringify(annotations.value)
    undoStack.value = [...undoStack.value, current]
    const next = redoStack.value[redoStack.value.length - 1]
    redoStack.value = redoStack.value.slice(0, -1)
    annotations.value = JSON.parse(next) as AnnotationElement[]
    _layer?.batchDraw()
  }

  /**
   * Clear all annotations.
   */
  function clearAll(): void {
    if (annotations.value.length === 0) return
    _pushUndo()
    annotations.value = []
    redoStack.value = []
    _layer?.batchDraw()
  }

  // ---------------------------------------------------------------------------
  // Konva config generators (used by template)
  // ---------------------------------------------------------------------------

  /**
   * Generate Konva configs for all committed annotations + the in-progress drawing.
   */
  function getAnnotationConfigs(): AnnotationElement[] {
    const all = [...annotations.value]
    if (drawingElement.value) {
      all.push(drawingElement.value)
    }
    return all
  }

  // ---------------------------------------------------------------------------
  // Coordinate helpers
  // ---------------------------------------------------------------------------

  /**
   * Convert screen (pointer) coordinates to Konva stage space.
   * Accounts for zoom and pan.
   */
  function screenToStage(
    clientX: number,
    clientY: number,
    containerRect: DOMRect,
    zoom: number,
    panX: number,
    panY: number,
  ): { x: number; y: number } {
    const localX = clientX - containerRect.left
    const localY = clientY - containerRect.top
    return {
      x: (localX - panX) / zoom,
      y: (localY - panY) / zoom,
    }
  }

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------

  function _finishDrawing(): void {
    if (!drawingElement.value) return

    const el = drawingElement.value

    // Validate: skip degenerate shapes
    const isValid = _validateElement(el)
    if (isValid) {
      _pushUndo()
      annotations.value = [...annotations.value, el]
      redoStack.value = []
    }

    drawingElement.value = null
    _layer?.batchDraw()
  }

  function _validateElement(el: AnnotationElement): boolean {
    switch (el.type) {
      case 'pen':
        return (el.points?.length ?? 0) >= 4 // at least 2 points
      case 'rectangle':
      case 'ellipse':
        return Math.abs(el.width ?? 0) > 2 && Math.abs(el.height ?? 0) > 2
      case 'arrow':
        if (!el.points || el.points.length < 4) return false
        return (
          Math.abs(el.points[0] - el.points[2]) > 2 ||
          Math.abs(el.points[1] - el.points[3]) > 2
        )
      case 'text':
        return true
      default:
        return false
    }
  }

  function _pushUndo(): void {
    const snapshot = JSON.stringify(annotations.value)
    undoStack.value = [...undoStack.value.slice(-(MAX_HISTORY - 1)), snapshot]
  }

  function _eraseAt(x: number, y: number): void {
    const hitRadius = 15
    const remaining = annotations.value.filter((ann) => {
      switch (ann.type) {
        case 'pen': {
          if (!ann.points) return true
          for (let i = 0; i < ann.points.length - 1; i += 2) {
            const dx = ann.points[i] - x
            const dy = ann.points[i + 1] - y
            if (Math.sqrt(dx * dx + dy * dy) < hitRadius) return false
          }
          return true
        }
        case 'rectangle': {
          const ax = ann.x ?? 0
          const ay = ann.y ?? 0
          const aw = ann.width ?? 0
          const ah = ann.height ?? 0
          const left = Math.min(ax, ax + aw)
          const right = Math.max(ax, ax + aw)
          const top = Math.min(ay, ay + ah)
          const bottom = Math.max(ay, ay + ah)
          return !(x >= left - hitRadius && x <= right + hitRadius && y >= top - hitRadius && y <= bottom + hitRadius)
        }
        case 'ellipse': {
          const cx = ann.x ?? 0
          const cy = ann.y ?? 0
          const rx = Math.abs(ann.width ?? 0) / 2 + hitRadius
          const ry = Math.abs(ann.height ?? 0) / 2 + hitRadius
          if (rx === 0 || ry === 0) return true
          const dx = (x - cx) / rx
          const dy = (y - cy) / ry
          return dx * dx + dy * dy > 1
        }
        case 'arrow': {
          if (!ann.points || ann.points.length < 4) return true
          const dx = ann.points[0] - x
          const dy = ann.points[1] - y
          const dx2 = ann.points[2] - x
          const dy2 = ann.points[3] - y
          return (
            Math.sqrt(dx * dx + dy * dy) >= hitRadius &&
            Math.sqrt(dx2 * dx2 + dy2 * dy2) >= hitRadius
          )
        }
        case 'text': {
          const tx = ann.x ?? 0
          const ty = ann.y ?? 0
          return !(x >= tx - hitRadius && x <= tx + 100 + hitRadius && y >= ty - hitRadius && y <= ty + 30 + hitRadius)
        }
        default:
          return true
      }
    })

    if (remaining.length !== annotations.value.length) {
      _pushUndo()
      annotations.value = remaining
      redoStack.value = []
      _layer?.batchDraw()
    }
  }

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  onBeforeUnmount(() => {
    unbind()
  })

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // State
    annotations,
    isActive,
    activeTool,
    style,
    drawingElement,
    canUndo,
    canRedo,
    annotationCount,

    // Methods
    bind,
    unbind,
    toggleActive,
    setTool,
    setStyle,

    // Drawing lifecycle
    startDrawing,
    continueDrawing,
    finishDrawing,

    // Undo/redo
    undo,
    redo,
    clearAll,

    // Config generators
    getAnnotationConfigs,

    // Coordinate helpers
    screenToStage,
  }
}
