/**
 * Agent Cursor Composable
 *
 * Renders a persistent macOS-style black arrow cursor on the Konva overlay
 * layer, tracking the agent's pointer position as it browses.
 *
 * - Creates Konva nodes imperatively (Group > two Paths for outline + fill)
 * - Time-based exponential smoothing (frame-rate independent)
 * - Click micro-interaction: scale 0.85x for 120ms
 * - Idle detection: opacity fades to 0.7 after 3s without events
 * - Only retargets on explicit coordinate_x/coordinate_y or x/y in event args
 */
import { shallowRef, onBeforeUnmount } from 'vue'
import Konva from 'konva'
import type { ToolEventData } from '@/types/event'
import type { CursorState } from '@/types/liveViewer'
import { FUNCTION_TO_ACTION_TYPE } from '@/types/liveViewer'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Exponential smoothing constant — higher = snappier (95% in ~250ms) */
const SMOOTH_K = 12

/** Duration of the click scale-down animation (ms) */
const CLICK_ANIM_MS = 120

/** Time before cursor is considered idle (ms) */
const IDLE_THRESHOLD_MS = 3000

/** Opacity when idle */
const IDLE_OPACITY = 0.7

/** Opacity when active */
const ACTIVE_OPACITY = 1.0

/** Normal cursor scale */
const SCALE_NORMAL = 1.3

/** Click-down scale (brief squish) */
const SCALE_CLICK = 1.3 * 0.85

// Cursor SVG path data (macOS-style black arrow pointer)
// Outer path: white stroke for visibility on dark backgrounds
const CURSOR_OUTLINE_PATH =
  'M 0,0 L 0,17 L 4.5,12.5 L 7.5,19 L 9.5,18 L 6.5,11.5 L 12,11.5 Z'
// Inner path: black fill
const CURSOR_FILL_PATH =
  'M 1,1.5 L 1,14.5 L 4,11.5 L 7,17 L 8.5,16.5 L 5.5,10.5 L 10.5,10.5 Z'

export function useAgentCursor() {
  // ---------------------------------------------------------------------------
  // State (reactive for external consumers)
  // ---------------------------------------------------------------------------

  const enabled = shallowRef(true)
  const isVisible = shallowRef(false)
  const cursorState = shallowRef<CursorState>('idle')

  // ---------------------------------------------------------------------------
  // Internal (non-reactive for perf in hot animation path)
  // ---------------------------------------------------------------------------

  let _layer: Konva.Layer | null = null
  let _group: Konva.Group | null = null

  // Position tracking
  let _targetX = 0
  let _targetY = 0
  let _currentX = 0
  let _currentY = 0

  // Animation loop
  let _rafId: number | null = null
  let _lastTickTime = 0
  let _animating = false

  // Click animation
  let _clickTimer: ReturnType<typeof setTimeout> | null = null

  // Idle detection
  let _lastEventTime = 0
  let _idleCheckTimer: ReturnType<typeof setTimeout> | null = null
  let _isIdle = false

  // Deduplicate CALLING/CALLED pairs with identical coordinates
  let _lastToolCallId: string | null = null
  let _lastX = 0
  let _lastY = 0

  // ---------------------------------------------------------------------------
  // Konva node creation
  // ---------------------------------------------------------------------------

  function _createCursorGroup(): Konva.Group {
    const group = new Konva.Group({
      x: 0,
      y: 0,
      scaleX: SCALE_NORMAL,
      scaleY: SCALE_NORMAL,
      visible: false,
      listening: false,
      shadowColor: 'rgba(0,0,0,0.3)',
      shadowBlur: 4,
      shadowOffsetX: 1,
      shadowOffsetY: 2,
      shadowEnabled: true,
    })

    // Outline path (white stroke for contrast on dark backgrounds)
    const outline = new Konva.Path({
      data: CURSOR_OUTLINE_PATH,
      fill: 'white',
      stroke: 'white',
      strokeWidth: 1.5,
      listening: false,
      perfectDrawEnabled: false,
    })

    // Fill path (black — the actual arrow)
    const fill = new Konva.Path({
      data: CURSOR_FILL_PATH,
      fill: 'black',
      listening: false,
      perfectDrawEnabled: false,
    })

    group.add(outline)
    group.add(fill)

    return group
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  function bindLayer(layer: Konva.Layer): void {
    // Guard against duplicate calls from mount retry loop
    if (_group) {
      _group.destroy()
      _group = null
    }

    _layer = layer

    // Create cursor nodes and add to layer
    _group = _createCursorGroup()
    _layer.add(_group)
    _group.moveToTop()
  }

  function unbindLayer(): void {
    _stopAnimationLoop()
    _clearTimers()

    if (_group) {
      _group.destroy()
      _group = null
    }
    _layer = null
    isVisible.value = false
    cursorState.value = 'idle'
  }

  function processToolEvent(event: ToolEventData): void {
    if (!enabled.value || !_group || !_layer) return

    // Process "calling" (direct coordinates) and "called" (resolved coordinates from index-based clicks)
    if (event.status !== 'calling' && event.status !== 'called') return

    // Must be a known browser action
    const functionName = event.function || event.name || ''
    const actionType = FUNCTION_TO_ACTION_TYPE[functionName]
    if (!actionType) return

    // Extract coordinates — strict gating, no center fallback
    const coords = _extractCoordinates(event)
    if (!coords) return

    if (
      event.tool_call_id
      && event.tool_call_id === _lastToolCallId
      && Math.abs(coords.x - _lastX) < 0.01
      && Math.abs(coords.y - _lastY) < 0.01
    ) {
      return
    }
    _lastToolCallId = event.tool_call_id
    _lastX = coords.x
    _lastY = coords.y

    _lastEventTime = Date.now()

    // If cursor was hidden, initialize position at target (no glide from 0,0)
    if (!isVisible.value) {
      _currentX = coords.x
      _currentY = coords.y
      _targetX = coords.x
      _targetY = coords.y

      _group.x(_currentX)
      _group.y(_currentY)
      _group.visible(true)
      _group.opacity(ACTIVE_OPACITY)
      isVisible.value = true
    } else {
      _targetX = coords.x
      _targetY = coords.y
    }

    // Reset idle state
    _isIdle = false
    _group.opacity(ACTIVE_OPACITY)
    _scheduleIdleCheck()

    // Click micro-interaction
    if (actionType === 'click') {
      _triggerClickAnimation()
    } else {
      cursorState.value = 'moving'
    }

    // Ensure cursor is on top of other overlay shapes
    _group.moveToTop()

    // Start animation loop if not running
    _startAnimationLoop()
  }

  function toggle(): void {
    enabled.value = !enabled.value
    if (!enabled.value) {
      hide()
    }
  }

  function hide(): void {
    if (_group) {
      _group.visible(false)
    }
    isVisible.value = false
    cursorState.value = 'idle'
    _stopAnimationLoop()
    _clearTimers()
    if (_layer) {
      _layer.batchDraw()
    }
  }

  // ---------------------------------------------------------------------------
  // Coordinate extraction (strict — no center fallback)
  // ---------------------------------------------------------------------------

  function _extractCoordinates(
    event: ToolEventData,
  ): { x: number; y: number } | null {
    const args = event.args || {}

    if (typeof args.coordinate_x === 'number' && typeof args.coordinate_y === 'number') {
      return { x: args.coordinate_x as number, y: args.coordinate_y as number }
    }
    if (typeof args.x === 'number' && typeof args.y === 'number') {
      return { x: args.x as number, y: args.y as number }
    }

    return null
  }

  // ---------------------------------------------------------------------------
  // Click animation
  // ---------------------------------------------------------------------------

  function _triggerClickAnimation(): void {
    if (!_group) return

    cursorState.value = 'clicking'

    // Scale down
    _group.scaleX(SCALE_CLICK)
    _group.scaleY(SCALE_CLICK)

    // Clear previous click timer if overlapping
    if (_clickTimer) {
      clearTimeout(_clickTimer)
    }

    // Snap back after CLICK_ANIM_MS
    _clickTimer = setTimeout(() => {
      _clickTimer = null
      if (_group) {
        _group.scaleX(SCALE_NORMAL)
        _group.scaleY(SCALE_NORMAL)
      }
      cursorState.value = _isIdle ? 'idle' : 'moving'
    }, CLICK_ANIM_MS)
  }

  // ---------------------------------------------------------------------------
  // Idle detection
  // ---------------------------------------------------------------------------

  function _scheduleIdleCheck(): void {
    if (_idleCheckTimer) {
      clearTimeout(_idleCheckTimer)
    }
    _idleCheckTimer = setTimeout(() => {
      _idleCheckTimer = null
      _checkIdle()
    }, IDLE_THRESHOLD_MS)
  }

  function _checkIdle(): void {
    if (!_group || !isVisible.value) return

    const elapsed = Date.now() - _lastEventTime
    if (elapsed >= IDLE_THRESHOLD_MS) {
      _isIdle = true
      cursorState.value = 'idle'
      _group.opacity(IDLE_OPACITY)
      if (_layer) {
        _layer.batchDraw()
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Animation loop (time-based exponential smoothing)
  // ---------------------------------------------------------------------------

  function _startAnimationLoop(): void {
    if (_animating) return
    _animating = true
    _lastTickTime = performance.now()
    _rafId = requestAnimationFrame(_tick)
  }

  function _stopAnimationLoop(): void {
    _animating = false
    if (_rafId !== null) {
      cancelAnimationFrame(_rafId)
      _rafId = null
    }
  }

  function _tick(now: number): void {
    if (!_animating || !_group || !_layer) return

    const dt = (now - _lastTickTime) / 1000 // seconds
    _lastTickTime = now

    // Clamp dt to prevent huge jumps after tab switch
    const clampedDt = Math.min(dt, 0.1)

    // Exponential decay smoothing (frame-rate independent)
    const alpha = 1 - Math.exp(-SMOOTH_K * clampedDt)
    _currentX += (_targetX - _currentX) * alpha
    _currentY += (_targetY - _currentY) * alpha

    _group.x(_currentX)
    _group.y(_currentY)
    _layer.batchDraw()

    // Check if cursor has settled (within 0.5px of target)
    const dx = Math.abs(_targetX - _currentX)
    const dy = Math.abs(_targetY - _currentY)
    const settled = dx < 0.5 && dy < 0.5

    if (settled) {
      // Snap to exact position
      _currentX = _targetX
      _currentY = _targetY
      _group.x(_currentX)
      _group.y(_currentY)
      _layer.batchDraw()

      // Stop the RAF loop — will restart on next event
      _animating = false
      _rafId = null

      if (cursorState.value === 'moving') {
        cursorState.value = 'idle'
      }
    } else {
      _rafId = requestAnimationFrame(_tick)
    }
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  function _clearTimers(): void {
    if (_clickTimer) {
      clearTimeout(_clickTimer)
      _clickTimer = null
    }
    if (_idleCheckTimer) {
      clearTimeout(_idleCheckTimer)
      _idleCheckTimer = null
    }
  }

  onBeforeUnmount(() => {
    _stopAnimationLoop()
    _clearTimers()
    unbindLayer()
  })

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    enabled,
    isVisible,
    cursorState,
    bindLayer,
    unbindLayer,
    processToolEvent,
    toggle,
    hide,
  }
}
