/**
 * Live Viewer Zoom & Pan Composable
 *
 * Manages zoom and pan state for the Konva-powered live viewer.
 * Supports zoom-to-point (cursor-centric), fit-to-screen,
 * keyboard/wheel controls, and smooth transitions.
 *
 * Reuses patterns from useCanvasEditor.ts zoom logic.
 */
import { ref, computed } from 'vue'
import type { ZoomState, FrameDimensions } from '@/types/liveViewer'
import { ZOOM_DEFAULTS, ZOOM_MIN, ZOOM_MAX, ZOOM_STEP } from '@/types/liveViewer'

export function useLiveViewerZoom() {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const zoom = ref(ZOOM_DEFAULTS.zoom)
  const panX = ref(ZOOM_DEFAULTS.panX)
  const panY = ref(ZOOM_DEFAULTS.panY)

  /** Whether the user is currently panning (space+drag or middle mouse) */
  const isPanning = ref(false)

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const zoomState = computed<ZoomState>(() => ({
    zoom: zoom.value,
    panX: panX.value,
    panY: panY.value,
  }))

  const zoomPercent = computed(() => Math.round(zoom.value * 100))

  const canZoomIn = computed(() => zoom.value < ZOOM_MAX)
  const canZoomOut = computed(() => zoom.value > ZOOM_MIN)

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  /**
   * Set zoom to an exact level, clamped to [ZOOM_MIN, ZOOM_MAX].
   */
  function setZoom(level: number): void {
    zoom.value = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, level))
  }

  /**
   * Zoom in by ZOOM_STEP.
   */
  function zoomIn(): void {
    setZoom(zoom.value + ZOOM_STEP)
  }

  /**
   * Zoom out by ZOOM_STEP.
   */
  function zoomOut(): void {
    setZoom(zoom.value - ZOOM_STEP)
  }

  /**
   * Reset to 100% zoom, centered.
   */
  function resetZoom(): void {
    zoom.value = 1
    panX.value = 0
    panY.value = 0
  }

  /**
   * Zoom to fit the frame within the given container dimensions.
   * Centers the frame with padding.
   *
   * Guards against zero or degenerate dimensions — returns false if
   * fitting was not possible (caller should retry when dimensions settle).
   */
  function fitToScreen(
    containerWidth: number,
    containerHeight: number,
    frame: FrameDimensions,
  ): boolean {
    // Guard: both container and frame must have valid positive dimensions
    if (frame.width <= 0 || frame.height <= 0) return false
    if (containerWidth <= 0 || containerHeight <= 0) return false

    const padding = 4 // px padding on each side
    const availableW = Math.max(containerWidth - padding * 2, 1)
    const availableH = Math.max(containerHeight - padding * 2, 1)

    const scaleX = availableW / frame.width
    const scaleY = availableH / frame.height
    const fitZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.min(scaleX, scaleY)))

    zoom.value = fitZoom

    // Center the frame
    const scaledW = frame.width * fitZoom
    const scaledH = frame.height * fitZoom
    panX.value = (containerWidth - scaledW) / 2
    panY.value = (containerHeight - scaledH) / 2
    return true
  }

  /**
   * Zoom to a specific point (cursor-centric zoom).
   * The point under the cursor stays fixed while zooming.
   *
   * @param pointerX - Cursor X in container space
   * @param pointerY - Cursor Y in container space
   * @param delta - Positive = zoom in, negative = zoom out
   */
  function zoomToPoint(pointerX: number, pointerY: number, delta: number): void {
    const oldZoom = zoom.value
    const direction = delta > 0 ? -1 : 1
    const newZoom = Math.max(
      ZOOM_MIN,
      Math.min(ZOOM_MAX, oldZoom + direction * ZOOM_STEP * 0.5),
    )

    if (newZoom === oldZoom) return

    // Calculate the point in stage space before zoom
    const stageX = (pointerX - panX.value) / oldZoom
    const stageY = (pointerY - panY.value) / oldZoom

    // Adjust pan so the same stage point stays under the cursor
    panX.value = pointerX - stageX * newZoom
    panY.value = pointerY - stageY * newZoom
    zoom.value = newZoom
  }

  /**
   * Update pan offset (e.g., during drag).
   */
  function setPan(x: number, y: number): void {
    panX.value = x
    panY.value = y
  }

  /**
   * Apply a pan delta (e.g., from drag movement).
   */
  function applyPanDelta(dx: number, dy: number): void {
    panX.value += dx
    panY.value += dy
  }

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // State
    zoom,
    panX,
    panY,
    isPanning,

    // Computed
    zoomState,
    zoomPercent,
    canZoomIn,
    canZoomOut,

    // Actions
    setZoom,
    zoomIn,
    zoomOut,
    resetZoom,
    fitToScreen,
    zoomToPoint,
    setPan,
    applyPanDelta,
  }
}
