/**
 * Sandbox Input Composable
 *
 * Handles input forwarding from the frontend to the sandbox for interactive
 * takeover functionality. Captures mouse and keyboard events on the sandbox
 * viewer canvas and forwards them to the sandbox API.
 */
import { ref, onUnmounted } from 'vue'

// Input event types for the sandbox API
interface MouseInput {
  type: 'mousedown' | 'mouseup' | 'mousemove' | 'click' | 'dblclick'
  x: number
  y: number
  button: 'left' | 'right' | 'middle'
}

interface KeyboardInput {
  type: 'keydown' | 'keyup' | 'keypress'
  key: string
  code: string
  modifiers: {
    ctrl: boolean
    alt: boolean
    shift: boolean
    meta: boolean
  }
}

interface ScrollInput {
  type: 'scroll'
  x: number
  y: number
  deltaX: number
  deltaY: number
}

type SandboxInput = MouseInput | KeyboardInput | ScrollInput

// Sandbox viewport dimensions (should match sandbox browser settings)
const SANDBOX_WIDTH = 1280
const SANDBOX_HEIGHT = 1024

// State
const isForwarding = ref(false)
const lastError = ref<string | null>(null)

// WebSocket connection for real-time input
let inputWs: WebSocket | null = null
let inputQueue: SandboxInput[] = []
let flushInterval: number | null = null

/**
 * Start input forwarding to the sandbox
 * @param inputWsUrl - Full WebSocket URL for input stream (proxied through backend)
 */
function startForwarding(inputWsUrl: string): void {
  if (isForwarding.value) {
    return
  }

  const wsUrl = inputWsUrl

  try {
    inputWs = new WebSocket(wsUrl)

    inputWs.onopen = () => {
      isForwarding.value = true
      lastError.value = null
      console.info('[SandboxInput] Connected to input stream')

      // Start flushing queued inputs
      flushInterval = window.setInterval(flushInputQueue, 16) // ~60fps
    }

    inputWs.onerror = (e) => {
      console.error('[SandboxInput] WebSocket error:', e)
      lastError.value = 'Input connection error'
    }

    inputWs.onclose = () => {
      isForwarding.value = false
      stopFlushInterval()
      console.info('[SandboxInput] Disconnected from input stream')
    }
  } catch (err) {
    lastError.value = err instanceof Error ? err.message : 'Failed to connect'
    console.error('[SandboxInput] Connection failed:', err)
  }
}

/**
 * Stop input forwarding
 */
function stopForwarding(): void {
  stopFlushInterval()

  if (inputWs) {
    try {
      inputWs.close()
    } catch {
      // Ignore
    }
    inputWs = null
  }

  isForwarding.value = false
  inputQueue = []
}

function stopFlushInterval(): void {
  if (flushInterval) {
    clearInterval(flushInterval)
    flushInterval = null
  }
}

/**
 * Flush queued inputs to the sandbox
 */
function flushInputQueue(): void {
  if (!inputWs || inputWs.readyState !== WebSocket.OPEN || inputQueue.length === 0) {
    return
  }

  // Send all queued inputs
  const inputs = inputQueue.splice(0, inputQueue.length)
  inputWs.send(JSON.stringify({ inputs }))
}

/**
 * Queue an input event
 */
function queueInput(input: SandboxInput): void {
  if (!isForwarding.value) {
    return
  }
  inputQueue.push(input)
}

/**
 * Convert browser mouse button to sandbox button name
 */
function mouseButtonToName(button: number): 'left' | 'right' | 'middle' {
  switch (button) {
    case 0:
      return 'left'
    case 1:
      return 'middle'
    case 2:
      return 'right'
    default:
      return 'left'
  }
}

/**
 * Calculate scaled coordinates for the sandbox viewport
 * @param clientX - Mouse X position relative to the element
 * @param clientY - Mouse Y position relative to the element
 * @param elementWidth - Width of the container element
 * @param elementHeight - Height of the container element
 */
function scaleCoordinates(
  clientX: number,
  clientY: number,
  elementWidth: number,
  elementHeight: number
): { x: number; y: number } {
  // Calculate the aspect ratios
  const elementAspect = elementWidth / elementHeight
  const sandboxAspect = SANDBOX_WIDTH / SANDBOX_HEIGHT

  let offsetX = 0
  let offsetY = 0
  let scaledWidth = elementWidth
  let scaledHeight = elementHeight

  // Determine how the content is letterboxed/pillarboxed
  if (elementAspect > sandboxAspect) {
    // Element is wider - content is centered horizontally (pillarboxed)
    scaledWidth = elementHeight * sandboxAspect
    offsetX = (elementWidth - scaledWidth) / 2
  } else {
    // Element is taller - content is centered vertically (letterboxed)
    scaledHeight = elementWidth / sandboxAspect
    offsetY = (elementHeight - scaledHeight) / 2
  }

  // Calculate position relative to the scaled content area
  const relativeX = clientX - offsetX
  const relativeY = clientY - offsetY

  // Scale to sandbox coordinates
  const x = Math.round((relativeX / scaledWidth) * SANDBOX_WIDTH)
  const y = Math.round((relativeY / scaledHeight) * SANDBOX_HEIGHT)

  // Clamp to valid range
  return {
    x: Math.max(0, Math.min(SANDBOX_WIDTH, x)),
    y: Math.max(0, Math.min(SANDBOX_HEIGHT, y))
  }
}

/**
 * Handle mouse event and forward to sandbox
 */
function handleMouseEvent(
  event: MouseEvent,
  type: MouseInput['type'],
  elementWidth: number,
  elementHeight: number
): void {
  if (!isForwarding.value) return

  // Get coordinates relative to the element
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const clientX = event.clientX - rect.left
  const clientY = event.clientY - rect.top

  const { x, y } = scaleCoordinates(clientX, clientY, elementWidth, elementHeight)

  queueInput({
    type,
    x,
    y,
    button: mouseButtonToName(event.button)
  })
}

/**
 * Handle keyboard event and forward to sandbox
 */
function handleKeyboardEvent(event: KeyboardEvent, type: KeyboardInput['type']): void {
  if (!isForwarding.value) return

  // Prevent default browser behavior for forwarded keys
  event.preventDefault()

  queueInput({
    type,
    key: event.key,
    code: event.code,
    modifiers: {
      ctrl: event.ctrlKey,
      alt: event.altKey,
      shift: event.shiftKey,
      meta: event.metaKey
    }
  })
}

/**
 * Handle scroll event and forward to sandbox
 */
function handleScrollEvent(
  event: WheelEvent,
  elementWidth: number,
  elementHeight: number
): void {
  if (!isForwarding.value) return

  event.preventDefault()

  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const clientX = event.clientX - rect.left
  const clientY = event.clientY - rect.top

  const { x, y } = scaleCoordinates(clientX, clientY, elementWidth, elementHeight)

  queueInput({
    type: 'scroll',
    x,
    y,
    deltaX: event.deltaX,
    deltaY: event.deltaY
  })
}

/**
 * Attach event listeners to a container element for input forwarding
 * @param element - The container element (usually the canvas wrapper)
 * @returns Cleanup function to remove listeners
 */
function attachInputListeners(element: HTMLElement): () => void {
  const getElementSize = () => ({
    width: element.offsetWidth,
    height: element.offsetHeight
  })

  // Mouse event handlers
  const onMouseDown = (e: MouseEvent) => {
    const size = getElementSize()
    handleMouseEvent(e, 'mousedown', size.width, size.height)
  }

  const onMouseUp = (e: MouseEvent) => {
    const size = getElementSize()
    handleMouseEvent(e, 'mouseup', size.width, size.height)
  }

  const onMouseMove = (e: MouseEvent) => {
    const size = getElementSize()
    handleMouseEvent(e, 'mousemove', size.width, size.height)
  }

  const onClick = (e: MouseEvent) => {
    const size = getElementSize()
    handleMouseEvent(e, 'click', size.width, size.height)
  }

  const onDblClick = (e: MouseEvent) => {
    const size = getElementSize()
    handleMouseEvent(e, 'dblclick', size.width, size.height)
  }

  const onWheel = (e: WheelEvent) => {
    const size = getElementSize()
    handleScrollEvent(e, size.width, size.height)
  }

  // Keyboard event handlers (require focus)
  const onKeyDown = (e: KeyboardEvent) => handleKeyboardEvent(e, 'keydown')
  const onKeyUp = (e: KeyboardEvent) => handleKeyboardEvent(e, 'keyup')

  // Prevent context menu
  const onContextMenu = (e: MouseEvent) => {
    if (isForwarding.value) {
      e.preventDefault()
    }
  }

  // Attach listeners
  element.addEventListener('mousedown', onMouseDown)
  element.addEventListener('mouseup', onMouseUp)
  element.addEventListener('mousemove', onMouseMove)
  element.addEventListener('click', onClick)
  element.addEventListener('dblclick', onDblClick)
  element.addEventListener('wheel', onWheel, { passive: false })
  element.addEventListener('keydown', onKeyDown)
  element.addEventListener('keyup', onKeyUp)
  element.addEventListener('contextmenu', onContextMenu)

  // Make element focusable for keyboard events
  if (!element.hasAttribute('tabindex')) {
    element.setAttribute('tabindex', '0')
  }

  // Return cleanup function
  return () => {
    element.removeEventListener('mousedown', onMouseDown)
    element.removeEventListener('mouseup', onMouseUp)
    element.removeEventListener('mousemove', onMouseMove)
    element.removeEventListener('click', onClick)
    element.removeEventListener('dblclick', onDblClick)
    element.removeEventListener('wheel', onWheel)
    element.removeEventListener('keydown', onKeyDown)
    element.removeEventListener('keyup', onKeyUp)
    element.removeEventListener('contextmenu', onContextMenu)
  }
}

/**
 * Main composable export
 */
export function useSandboxInput() {
  // Cleanup on unmount
  onUnmounted(() => {
    stopForwarding()
  })

  return {
    // State
    isForwarding,
    lastError,

    // Methods
    startForwarding,
    stopForwarding,
    attachInputListeners,

    // Utilities (exposed for testing)
    scaleCoordinates
  }
}
