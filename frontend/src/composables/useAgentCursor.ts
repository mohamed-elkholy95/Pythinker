/**
 * Agent Cursor Composable
 *
 * Renders a persistent cursor on the Konva overlay layer using Apple cursor
 * SVG assets copied from `assets/cursors/apple_cursor-main`.
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
import type { AgentActionType, CursorState } from '@/types/liveViewer'
import { FUNCTION_TO_ACTION_TYPE, SANDBOX_HEIGHT, SANDBOX_WIDTH } from '@/types/liveViewer'
import {
  isJitterMove,
  stepTowards,
  type CursorMotionConfig,
} from '@/utils/agentCursorMotion'
import {
  getCursorAssetForAction,
  getWaitCursorFrameUrl,
} from '@/utils/agentCursorAssets'

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

/** Cursor icon render size in stage pixels */
const CURSOR_RENDER_SIZE = 24

/** Approximate hotspot for left_ptr.svg scaled to CURSOR_RENDER_SIZE */
const CURSOR_HOTSPOT_X = 8
const CURSOR_HOTSPOT_Y = 5

/** Wait cursor frame step interval */
const WAIT_FRAME_INTERVAL_MS = 80

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

interface CursorNodes {
  group: Konva.Group
  clickRing: Konva.Circle
  cursorImage: Konva.Image
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
  let _cursorImage: Konva.Image | null = null

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

  // Wait cursor animation
  let _waitAnimTimer: ReturnType<typeof setInterval> | null = null
  let _waitFrameIndex = 0

  // Deduplicate CALLING/CALLED pairs with identical coordinates
  let _lastToolCallId: string | null = null
  let _lastX = 0
  let _lastY = 0

  // Image loading cache
  const _imageCache = new Map<string, HTMLImageElement>()
  let _cursorLoadToken = 0

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

    const cursorImage = new Konva.Image({
      x: -CURSOR_HOTSPOT_X,
      y: -CURSOR_HOTSPOT_Y,
      width: CURSOR_RENDER_SIZE,
      height: CURSOR_RENDER_SIZE,
      image: undefined,
      listening: false,
      perfectDrawEnabled: false,
    })

    // Keep ripple behind cursor image.
    group.add(clickRing)
    group.add(cursorImage)

    return { group, clickRing, cursorImage }
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

  function _createImageElement(url: string): Promise<HTMLImageElement | null> {
    if (typeof window === 'undefined') return Promise.resolve(null)

    return new Promise((resolve) => {
      const image = new window.Image()
      image.decoding = 'async'
      image.onload = () => resolve(image)
      image.onerror = () => resolve(null)
      image.src = url
    })
  }

  async function _setCursorImageUrl(url: string): Promise<void> {
    if (!_cursorImage || !url) return

    const token = ++_cursorLoadToken
    let image = _imageCache.get(url)
    if (!image) {
      image = await _createImageElement(url) ?? undefined
      if (image) {
        _imageCache.set(url, image)
      }
    }

    if (!image) return
    if (!_cursorImage) return
    if (token !== _cursorLoadToken) return

    _cursorImage.image(image)
    if (_layer) {
      _layer.batchDraw()
    }
  }

  function _startWaitCursorAnimation(): void {
    if (_waitAnimTimer) return

    _waitFrameIndex = 0
    void _setCursorImageUrl(getWaitCursorFrameUrl(_waitFrameIndex))

    _waitAnimTimer = setInterval(() => {
      _waitFrameIndex += 1
      void _setCursorImageUrl(getWaitCursorFrameUrl(_waitFrameIndex))
    }, WAIT_FRAME_INTERVAL_MS)
  }

  function _stopWaitCursorAnimation(): void {
    if (_waitAnimTimer) {
      clearInterval(_waitAnimTimer)
      _waitAnimTimer = null
    }
  }

  function _applyCursorVisualForAction(actionType: AgentActionType): void {
    if (actionType === 'wait') {
      _startWaitCursorAnimation()
      return
    }

    _stopWaitCursorAnimation()
    void _setCursorImageUrl(getCursorAssetForAction(actionType))
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  function bindLayer(layer: Konva.Layer): void {
    if (_group) {
      _group.destroy()
      _group = null
      _clickRing = null
      _cursorImage = null
    }

    _layer = layer

    const nodes = _createCursorNodes()
    _group = nodes.group
    _clickRing = nodes.clickRing
    _cursorImage = nodes.cursorImage
    _layer.add(_group)
    _group.moveToTop()

    void _setCursorImageUrl(getCursorAssetForAction('move'))
  }

  function unbindLayer(): void {
    _stopAnimationLoop()
    _clearTimers()

    if (_group) {
      _group.destroy()
      _group = null
    }
    _clickRing = null
    _cursorImage = null
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

    _applyCursorVisualForAction(actionType)

    const coords = _extractCoordinates(event, actionType)
    if (!coords) {
      if (_layer) {
        _layer.batchDraw()
      }
      return
    }

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
    actionType: AgentActionType,
  ): { x: number; y: number } | null {
    const args = event.args || {}

    if (typeof args.coordinate_x === 'number' && typeof args.coordinate_y === 'number') {
      return { x: args.coordinate_x as number, y: args.coordinate_y as number }
    }
    if (typeof args.x === 'number' && typeof args.y === 'number') {
      return { x: args.x as number, y: args.y as number }
    }

    if (actionType === 'navigate') {
      return { x: SANDBOX_WIDTH / 2, y: 40 }
    }

    if (actionType === 'scroll') {
      const direction = event.function?.includes('down') || event.function?.includes('Down') ? 1 : -1
      return {
        x: SANDBOX_WIDTH / 2,
        y: SANDBOX_HEIGHT / 2 + direction * 100,
      }
    }

    if (isVisible.value) {
      return { x: _targetX, y: _targetY }
    }

    return { x: SANDBOX_WIDTH / 2, y: SANDBOX_HEIGHT / 2 }
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
    _stopWaitCursorAnimation()
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
