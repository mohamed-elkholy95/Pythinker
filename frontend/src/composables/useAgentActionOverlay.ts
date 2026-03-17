/**
 * Agent Action Overlay Composable
 *
 * Manages animated Konva shapes that visualize agent browser actions
 * (clicks, typing, scrolling, navigation) on the live viewer overlay layer.
 *
 * Receives tool events from SSE, maps them to AgentAction objects,
 * runs entry/exit animations via requestAnimationFrame, and auto-removes
 * completed animations.
 */
import { shallowRef, triggerRef, onBeforeUnmount } from 'vue'
import type Konva from 'konva'
import type { AgentAction, AgentActionType } from '@/types/liveViewer'
import type { ToolEventData } from '@/types/event'
import {
  FUNCTION_TO_ACTION_TYPE,
  ACTION_ANIMATION_DURATION,
  ACTION_COLORS,
  SANDBOX_WIDTH,
  SANDBOX_HEIGHT,
} from '@/types/liveViewer'

export function useAgentActionOverlay() {
  /** Instance-scoped counter to prevent ID collisions across instances */
  let _actionIdCounter = 0
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  /** Currently active (animating) actions — shallowRef for perf in hot animation path */
  const actions = shallowRef<AgentAction[]>([])

  /** Whether the overlay is enabled */
  const enabled = shallowRef(true)

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------

  /** Direct reference to the overlay Konva.Layer */
  let _layer: Konva.Layer | null = null
  /** Animation frame ID for the render loop */
  let _rafId: number | null = null
  /** Whether the animation loop is running */
  let _animating = false

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Bind the overlay layer (called once when KonvaLiveStage mounts).
   */
  function bindLayer(layer: Konva.Layer): void {
    _layer = layer
  }

  /**
   * Unbind the layer on teardown.
   */
  function unbindLayer(): void {
    _layer = null
    _stopAnimationLoop()
  }

  /**
   * Process an incoming tool event and potentially create an overlay action.
   * Call this from the SSE event handler when a tool event arrives.
   */
  function processToolEvent(event: ToolEventData): void {
    if (!enabled.value) return

    // Only process "calling" status (start of tool execution)
    if (event.status !== 'calling') return

    const functionName = event.function || event.name || ''
    const actionType = FUNCTION_TO_ACTION_TYPE[functionName]
    if (!actionType) return

    const { x, y } = _extractCoordinates(event, actionType)
    const label = _buildLabel(actionType, event)

    const action: AgentAction = {
      id: `action-${++_actionIdCounter}`,
      type: actionType,
      x,
      y,
      timestamp: Date.now(),
      label,
      functionName,
      progress: 0,
      duration: ACTION_ANIMATION_DURATION[actionType],
      meta: event.args,
    }

    actions.value = [...actions.value, action]
    _startAnimationLoop()
  }

  /**
   * Toggle overlay visibility.
   */
  function toggle(): void {
    enabled.value = !enabled.value
    if (!enabled.value) {
      clearActions()
    }
  }

  /**
   * Remove all active actions.
   */
  function clearActions(): void {
    actions.value = []
    _stopAnimationLoop()
  }

  // ---------------------------------------------------------------------------
  // Coordinate extraction
  // ---------------------------------------------------------------------------

  /**
   * Extract x/y coordinates from a tool event's args.
   * Falls back to center-of-viewport when coords aren't available.
   */
  function _extractCoordinates(
    event: ToolEventData,
    actionType: AgentActionType,
  ): { x: number; y: number } {
    const args = event.args || {}

    // Direct coordinate fields
    if (typeof args.coordinate_x === 'number' && typeof args.coordinate_y === 'number') {
      return { x: args.coordinate_x as number, y: args.coordinate_y as number }
    }
    if (typeof args.x === 'number' && typeof args.y === 'number') {
      return { x: args.x as number, y: args.y as number }
    }

    // Scroll actions — show in the vertical center
    if (actionType === 'scroll') {
      const direction = event.function?.includes('down') || event.function?.includes('Down')
        ? 1
        : -1
      return {
        x: SANDBOX_WIDTH / 2,
        y: SANDBOX_HEIGHT / 2 + direction * 100,
      }
    }

    // Navigate actions — show at top (address bar area)
    if (actionType === 'navigate') {
      return { x: SANDBOX_WIDTH / 2, y: 40 }
    }

    // Default: center of viewport
    return { x: SANDBOX_WIDTH / 2, y: SANDBOX_HEIGHT / 2 }
  }

  /**
   * Build a human-readable label for the action.
   */
  function _buildLabel(actionType: AgentActionType, event: ToolEventData): string {
    const args = event.args || {}

    switch (actionType) {
      case 'click':
        return 'Click'
      case 'type': {
        const text = String(args.text ?? args.value ?? '')
        return text.length > 20 ? `Type: ${text.slice(0, 20)}...` : `Type: ${text}`
      }
      case 'scroll':
        return event.function?.includes('down') || event.function?.includes('Down')
          ? 'Scroll Down'
          : 'Scroll Up'
      case 'navigate': {
        const url = String(args.url ?? '')
        try {
          const hostname = new URL(url).hostname
          return `Navigate: ${hostname}`
        } catch {
          return 'Navigate'
        }
      }
      case 'move':
        return 'Move'
      case 'press_key':
        return `Key: ${String(args.key ?? args.keys ?? '?')}`
      case 'select':
        return `Select: ${String(args.option ?? args.value ?? '?')}`
      case 'extract':
        return 'Extract'
      case 'wait':
        return 'Waiting...'
      default:
        return actionType
    }
  }

  // ---------------------------------------------------------------------------
  // Animation loop
  // ---------------------------------------------------------------------------

  function _startAnimationLoop(): void {
    if (_animating) return
    _animating = true
    _rafId = requestAnimationFrame(_tick)
  }

  function _stopAnimationLoop(): void {
    _animating = false
    if (_rafId !== null) {
      cancelAnimationFrame(_rafId)
      _rafId = null
    }
  }

  function _tick(): void {
    if (!_animating || !_layer) return

    const now = Date.now()
    const items = actions.value
    let changed = false
    let removedCount = 0

    // Update progress in-place (avoids creating new objects per frame)
    for (let i = 0; i < items.length; i++) {
      const action = items[i]
      const elapsed = now - action.timestamp
      const progress = Math.min(1, elapsed / action.duration)
      if (progress !== action.progress) {
        action.progress = progress
        changed = true
      }
      if (progress >= 1) removedCount++
    }

    // Only allocate a new array when completed items need removal
    if (removedCount > 0) {
      actions.value = items.filter((a) => a.progress < 1)
    } else if (changed) {
      // Notify Vue of in-place mutation without allocating
      triggerRef(actions)
    }

    // Redraw the overlay layer
    if (changed) {
      _layer.batchDraw()
    }

    // Continue or stop
    if (actions.value.length > 0) {
      _rafId = requestAnimationFrame(_tick)
    } else {
      _animating = false
      _rafId = null
    }
  }

  // ---------------------------------------------------------------------------
  // Konva shape config generators (used by template)
  // ---------------------------------------------------------------------------

  /**
   * Generate Konva shape configs for all active actions.
   * Returns an array of config objects for v-circle / v-text / v-arrow.
   */
  function getActionConfigs(): Array<{
    id: string
    type: AgentActionType
    x: number
    y: number
    progress: number
    color: string
    label: string
    opacity: number
    radius: number
  }> {
    return actions.value.map((action) => {
      const color = ACTION_COLORS[action.type]
      // Ease-out: fast start, slow finish
      const eased = 1 - Math.pow(1 - action.progress, 3)
      // Fade out in the last 30% of animation
      const fadeStart = 0.7
      const opacity =
        action.progress < fadeStart
          ? 0.8
          : 0.8 * (1 - (action.progress - fadeStart) / (1 - fadeStart))

      let radius: number
      switch (action.type) {
        case 'click':
          // Expanding ring
          radius = 8 + eased * 30
          break
        case 'scroll':
          radius = 20
          break
        case 'navigate':
          radius = 12
          break
        default:
          radius = 10 + eased * 10
      }

      return {
        id: action.id,
        type: action.type,
        x: action.x,
        y: action.y,
        progress: action.progress,
        color,
        label: action.label,
        opacity: Math.max(0, opacity),
        radius,
      }
    })
  }

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  onBeforeUnmount(() => {
    _stopAnimationLoop()
    unbindLayer()
  })

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // State
    actions,
    enabled,

    // Methods
    bindLayer,
    unbindLayer,
    processToolEvent,
    toggle,
    clearActions,
    getActionConfigs,
  }
}
