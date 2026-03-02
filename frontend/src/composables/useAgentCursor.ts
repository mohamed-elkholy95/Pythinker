/**
 * Agent Cursor Composable
 *
 * Renders a persistent macOS-style black arrow cursor on the Konva overlay
 * layer, tracking the agent's pointer position as it browses.
 *
 * Motion behavior:
 * - Adaptive smoothing (far jumps move faster, short hops stay precise)
 * - Max-speed clamp to avoid sudden teleports
 * - Jitter filtering for tiny coordinate noise
 * - Click pulse + ripple feedback
 * - Reduced-motion fallback (snap movement, no tween-heavy effects)
 */
import { shallowRef, onBeforeUnmount } from 'vue'
import Konva from 'konva'
import type { ToolEventData } from '@/types/event'
import type { CursorState } from '@/types/liveViewer'
import { FUNCTION_TO_ACTION_TYPE } from '@/types/liveViewer'
import {
  isJitterMove,
  stepTowards,
  type CursorMotionConfig,
} from '@/utils/agentCursorMotion'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Duration of click state in ms (visual pulse settles before reset) */
const CLICK_STATE_MS = 220

/** Time before cursor is considered idle (ms) */
const IDLE_THRESHOLD_MS = 3000

/** Opacity when idle */
const IDLE_OPACITY = 0.7

/** Opacity when active */
const ACTIVE_OPACITY = 1.0

/** Normal cursor scale */
const SCALE_NORMAL = 1.3

/** Click-down scale (brief squish) */
const SCALE_CLICK = 1.3 * 0.86

/** Cursor idle/active opacity tween duration (seconds) */
const OPACITY_TWEEN_SEC = 0.16

/** Click ripple animation duration (seconds) */
const CLICK_RIPPLE_SEC = 0.24

/** Click ripple base radius */
const CLICK_RIPPLE_RADIUS = 12

/** Click ripple expansion scale */
const CLICK_RIPPLE_SCALE = 2.2

const MOTION_CONFIG: CursorMotionConfig = {
  baseSmoothing: 12,
  minSmoothing: 10,
  maxSmoothing: 26,
  distanceBoost: 0.035,
  maxSpeedPxPerSec: 2200,
  settleThresholdPx: 0.5,
  jitterThresholdPx: 0.75,
}

const REDUCED_MOTION = typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches

// ── Apple Cursor SVG paths ────────────────────────────────────────────
// Sourced from ful1e5/apple_cursor (GPL-3.0) — pixel-perfect macOS arrow.
// Original viewBox 256×256; scaled to ~12×20px via CURSOR_INNER_SCALE.
// Color mapping: fill → black, stroke → white (standard macOS theme).

/** Inner arrow body (black fill) */
const CURSOR_FILL_PATH =
  'M84.1001 48.5601V173.06L110.8 146.56L136.3 207.56L158.3 197.06L133.8 139.06H172.8L84.1001 48.5601Z'

/** Outer border contour (white stroke, original stroke-width 11) */
const CURSOR_STROKE_PATH =
  'M88.0281 44.7102L78.6001 35.0909V48.5601V173.06V186.268L87.9746 176.964L108.876 156.218L131.225 209.681L133.454 215.013L138.669 212.524L160.669 202.024L165.411 199.76L163.366 194.92L142.094 144.56H172.8H185.892L176.728 135.21L88.0281 44.7102Z'

/** Scale mapping 256-space paths to ~12px base width */
const CURSOR_INNER_SCALE = 0.112

/** Arrow tip coordinates in 256-space (used as transform offset) */
const CURSOR_TIP_X = 78.6
const CURSOR_TIP_Y = 35.09

interface CursorNodes {
  group: Konva.Group
  clickRing: Konva.Circle
}

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
  let _clickRing: Konva.Circle | null = null

  // Position tracking
  let _targetX = 0
  let _targetY = 0
  let _currentX = 0
  let _currentY = 0

  // Animation loop
  let _rafId: number | null = null
  let _lastTickTime = 0
  let _animating = false

  // Click state reset timer
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

  function _createCursorNodes(): CursorNodes {
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
      opacity: ACTIVE_OPACITY,
    })

    const clickRing = new Konva.Circle({
      x: 1.5,
      y: 1.5,
      radius: CLICK_RIPPLE_RADIUS,
      stroke: '#60a5fa',
      strokeWidth: 1.6,
      opacity: 0,
      visible: false,
      listening: false,
      perfectDrawEnabled: false,
    })

    // Inner group transforms 256-space SVG paths so the arrow tip
    // sits at the outer group's origin at ~12px base width.
    const cursorShape = new Konva.Group({
      scaleX: CURSOR_INNER_SCALE,
      scaleY: CURSOR_INNER_SCALE,
      offsetX: CURSOR_TIP_X,
      offsetY: CURSOR_TIP_Y,
      listening: false,
    })

    // White border (stroke-only, renders behind the black fill)
    const outline = new Konva.Path({
      data: CURSOR_STROKE_PATH,
      stroke: 'white',
      strokeWidth: 11,
      listening: false,
      perfectDrawEnabled: false,
    })

    // Black arrow body (fill-only, renders on top)
    const fill = new Konva.Path({
      data: CURSOR_FILL_PATH,
      fill: 'black',
      listening: false,
      perfectDrawEnabled: false,
    })

    cursorShape.add(outline)
    cursorShape.add(fill)

    // Click ripple behind cursor, cursor shape on top.
    group.add(clickRing)
    group.add(cursorShape)

    return { group, clickRing }
  }

  function _setCursorOpacity(opacity: number): void {
    if (!_group) return

    if (REDUCED_MOTION) {
      _group.opacity(opacity)
    } else {
      _group.to({
        opacity,
        duration: OPACITY_TWEEN_SEC,
        easing: Konva.Easings.EaseOut,
      })
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  function bindLayer(layer: Konva.Layer): void {
    if (_group) {
      _group.destroy()
      _group = null
      _clickRing = null
    }

    _layer = layer

    const nodes = _createCursorNodes()
    _group = nodes.group
    _clickRing = nodes.clickRing
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
    _clickRing = null
    _layer = null
    isVisible.value = false
    cursorState.value = 'idle'
  }

  function processToolEvent(event: ToolEventData): void {
    if (!enabled.value || !_group || !_layer) return

    if (event.status !== 'calling' && event.status !== 'called') return

    const functionName = event.function || event.name || ''
    const actionType = FUNCTION_TO_ACTION_TYPE[functionName]
    if (!actionType) return

    const coords = _extractCoordinates(event)
    if (!coords) return

    if (isVisible.value && isJitterMove(_targetX, _targetY, coords.x, coords.y, MOTION_CONFIG)) {
      return
    }

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

    if (!isVisible.value) {
      _currentX = coords.x
      _currentY = coords.y
      _targetX = coords.x
      _targetY = coords.y

      _group.x(_currentX)
      _group.y(_currentY)
      _group.visible(true)
      _setCursorOpacity(ACTIVE_OPACITY)
      isVisible.value = true
    } else {
      _targetX = coords.x
      _targetY = coords.y
    }

    _isIdle = false
    _setCursorOpacity(ACTIVE_OPACITY)
    _scheduleIdleCheck()

    if (actionType === 'click') {
      _triggerClickAnimation()
    } else {
      cursorState.value = 'moving'
    }

    _group.moveToTop()
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

    if (_clickTimer) {
      clearTimeout(_clickTimer)
    }

    if (REDUCED_MOTION) {
      _group.scaleX(SCALE_CLICK)
      _group.scaleY(SCALE_CLICK)
      _group.scaleX(SCALE_NORMAL)
      _group.scaleY(SCALE_NORMAL)
    } else {
      _group.to({
        scaleX: SCALE_CLICK,
        scaleY: SCALE_CLICK,
        duration: 0.05,
        easing: Konva.Easings.EaseOut,
        onFinish: () => {
          if (!_group) return
          _group.to({
            scaleX: SCALE_NORMAL,
            scaleY: SCALE_NORMAL,
            duration: 0.14,
            easing: Konva.Easings.BackEaseOut,
          })
        },
      })

      if (_clickRing) {
        _clickRing.visible(true)
        _clickRing.opacity(0.9)
        _clickRing.scaleX(0.65)
        _clickRing.scaleY(0.65)
        _clickRing.to({
          scaleX: CLICK_RIPPLE_SCALE,
          scaleY: CLICK_RIPPLE_SCALE,
          opacity: 0,
          duration: CLICK_RIPPLE_SEC,
          easing: Konva.Easings.EaseOut,
          onFinish: () => {
            if (!_clickRing) return
            _clickRing.visible(false)
            _clickRing.scaleX(1)
            _clickRing.scaleY(1)
          },
        })
      }
    }

    _clickTimer = setTimeout(() => {
      _clickTimer = null
      cursorState.value = _isIdle ? 'idle' : 'moving'
    }, CLICK_STATE_MS)
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
      _setCursorOpacity(IDLE_OPACITY)
      if (_layer) {
        _layer.batchDraw()
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Animation loop (adaptive smoothing + speed clamp)
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

    const dt = (now - _lastTickTime) / 1000
    _lastTickTime = now

    // Clamp dt to prevent huge jumps after tab switch.
    const clampedDt = Math.min(dt, 0.1)
    const next = stepTowards(
      _currentX,
      _currentY,
      _targetX,
      _targetY,
      clampedDt,
      MOTION_CONFIG,
      REDUCED_MOTION,
    )

    _currentX = next.x
    _currentY = next.y

    _group.x(_currentX)
    _group.y(_currentY)
    _layer.batchDraw()

    if (next.settled) {
      _currentX = _targetX
      _currentY = _targetY
      _group.x(_currentX)
      _group.y(_currentY)
      _layer.batchDraw()

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
