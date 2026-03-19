import { ref, computed, onUnmounted, type Ref } from 'vue'

export interface PanelSplitterOptions {
  chatSplitRef: Ref<HTMLElement | undefined>
  toolPanelSize: Ref<number>
  isMobileViewport: Ref<boolean>
  isToolPanelOpen: Ref<boolean>
}

/**
 * Composable that encapsulates the chat / tool-panel drag-splitter logic.
 */
export function usePanelSplitter(options: PanelSplitterOptions) {
  const { chatSplitRef, toolPanelSize, isMobileViewport, isToolPanelOpen } = options

  // ── Interaction state ──
  const isSplitDragging = ref(false)
  const isSplitHovering = ref(false)
  const isSplitFocused = ref(false)
  let splitPointerMoveHandler: ((event: PointerEvent) => void) | null = null
  let splitPointerUpHandler: ((event: PointerEvent) => void) | null = null

  // ── Constants ──
  const SPLIT_MIN_PANEL_WIDTH_PX = 340
  const SPLIT_MIN_CHAT_WIDTH_PX = 420
  const SPLIT_WHEEL_STEP_PX = 24

  // ── Computed styles ──
  const splitIsActive = computed(
    () => isSplitHovering.value || isSplitDragging.value || isSplitFocused.value,
  )

  const splitterTrackStyle = computed<Record<string, string>>(() => ({
    cursor: 'ew-resize',
    borderRadius: '9999px',
    backgroundColor: splitIsActive.value ? 'rgba(59, 130, 246, 0.12)' : 'transparent',
    transition: 'background-color 0.12s ease',
  }))

  const splitterHandleStyle = computed<Record<string, string>>(() => ({
    backgroundColor: splitIsActive.value
      ? 'var(--status-running, #3b82f6)'
      : 'var(--border-dark, rgba(17, 24, 39, 0.22))',
    opacity: splitIsActive.value ? '1' : '0.9',
    transform: splitIsActive.value ? 'scaleX(1.65)' : 'scaleX(1)',
    boxShadow: splitIsActive.value
      ? '0 0 0 1px rgba(59, 130, 246, 0.45), 0 0 10px rgba(59, 130, 246, 0.28)'
      : 'none',
    transition:
      'background-color 0.12s ease, opacity 0.12s ease, transform 0.12s ease, box-shadow 0.12s ease',
  }))

  // ── Helpers ──
  const getSplitContainerWidth = () => {
    return chatSplitRef.value?.clientWidth || window.innerWidth
  }

  const getPanelMaxWidth = () => {
    const containerWidth = getSplitContainerWidth()
    return Math.max(SPLIT_MIN_PANEL_WIDTH_PX, containerWidth - SPLIT_MIN_CHAT_WIDTH_PX)
  }

  const clampPanelWidth = (width: number) => {
    const maxWidth = getPanelMaxWidth()
    return Math.min(Math.max(width, SPLIT_MIN_PANEL_WIDTH_PX), maxWidth)
  }

  const getCurrentPanelWidth = () => {
    const containerWidth = getSplitContainerWidth()
    const defaultWidth = containerWidth / 2
    const requested = toolPanelSize.value > 0 ? toolPanelSize.value : defaultWidth
    return clampPanelWidth(requested)
  }

  const setPanelWidth = (width: number) => {
    if (isMobileViewport.value) return
    toolPanelSize.value = Math.round(clampPanelWidth(width))
  }

  const adjustPanelWidth = (delta: number) => {
    setPanelWidth(getCurrentPanelWidth() + delta)
  }

  const stopSplitterDrag = () => {
    if (splitPointerMoveHandler) {
      window.removeEventListener('pointermove', splitPointerMoveHandler)
      splitPointerMoveHandler = null
    }
    if (splitPointerUpHandler) {
      window.removeEventListener('pointerup', splitPointerUpHandler)
      window.removeEventListener('pointercancel', splitPointerUpHandler)
      splitPointerUpHandler = null
    }
    isSplitDragging.value = false
    isSplitHovering.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  const resetToolPanelWidth = () => {
    toolPanelSize.value = 0
  }

  // ── Event handlers ──
  const handleSplitterPointerDown = (event: PointerEvent) => {
    if (isMobileViewport.value || !isToolPanelOpen.value) return

    const startX = event.clientX
    const startWidth = getCurrentPanelWidth()

    isSplitDragging.value = true
    document.body.style.cursor = 'ew-resize'
    document.body.style.userSelect = 'none'

    splitPointerMoveHandler = (moveEvent: PointerEvent) => {
      const deltaX = moveEvent.clientX - startX
      setPanelWidth(startWidth - deltaX)
    }

    splitPointerUpHandler = () => {
      stopSplitterDrag()
    }

    window.addEventListener('pointermove', splitPointerMoveHandler)
    window.addEventListener('pointerup', splitPointerUpHandler)
    window.addEventListener('pointercancel', splitPointerUpHandler)
  }

  const handleSplitterWheel = (event: WheelEvent) => {
    if (isMobileViewport.value || !isToolPanelOpen.value) return
    const direction = event.deltaY < 0 ? 1 : -1
    adjustPanelWidth(direction * SPLIT_WHEEL_STEP_PX)
  }

  const handleSplitterKeydown = (event: KeyboardEvent) => {
    if (isMobileViewport.value || !isToolPanelOpen.value) return

    const KEYBOARD_STEP_PX = 40 // Larger step for keyboard (feels more responsive)

    switch (event.key) {
      case 'ArrowLeft':
        event.preventDefault()
        adjustPanelWidth(KEYBOARD_STEP_PX) // Expand panel (decrease chat width)
        break
      case 'ArrowRight':
        event.preventDefault()
        adjustPanelWidth(-KEYBOARD_STEP_PX) // Shrink panel (increase chat width)
        break
      case 'Home':
        event.preventDefault()
        setPanelWidth(getPanelMaxWidth())
        break
      case 'End':
        event.preventDefault()
        setPanelWidth(SPLIT_MIN_PANEL_WIDTH_PX)
        break
      case 'Enter':
      case ' ':
        event.preventDefault()
        resetToolPanelWidth()
        break
    }
  }

  onUnmounted(stopSplitterDrag)

  return {
    // State
    isSplitDragging,
    isSplitHovering,
    isSplitFocused,

    // Constants (exposed for template aria attrs)
    SPLIT_MIN_PANEL_WIDTH_PX,

    // Computed
    splitIsActive,
    splitterTrackStyle,
    splitterHandleStyle,

    // Helpers
    getPanelMaxWidth,
    stopSplitterDrag,
    resetToolPanelWidth,
    reclampPanelWidth: () => {
      if (toolPanelSize.value > 0) {
        toolPanelSize.value = Math.round(clampPanelWidth(toolPanelSize.value))
      }
    },

    // Handlers
    handleSplitterPointerDown,
    handleSplitterWheel,
    handleSplitterKeydown,
  }
}
