/**
 * Sandbox Input Composable
 *
 * Handles input forwarding from the frontend to the sandbox using CDP
 * (Chrome DevTools Protocol) for direct browser input injection.
 * Captures mouse and keyboard events on the sandbox viewer canvas
 * and forwards them as individual CDP events via WebSocket.
 */
import { shallowRef, onUnmounted } from 'vue'
import { SANDBOX_WIDTH, SANDBOX_HEIGHT } from '@/types/liveViewer'

// CDP Input Protocol - Chrome DevTools Protocol event types
// https://chromedevtools.github.io/devtools-protocol/tot/Input/

interface CDPMouseEvent {
  type: 'mouse'
  event_type: 'mousePressed' | 'mouseReleased' | 'mouseMoved'
  x: number
  y: number
  button: 'left' | 'right' | 'middle' | 'none'
  click_count?: number
  modifiers: number // Bitmask: Alt(1), Ctrl(2), Meta(4), Shift(8)
}

interface CDPKeyboardEvent {
  type: 'keyboard'
  event_type: 'keyDown' | 'keyUp' | 'char'
  key: string
  code: string
  text?: string
  modifiers: number
}

interface CDPWheelEvent {
  type: 'wheel'
  x: number
  y: number
  delta_x: number
  delta_y: number
}

interface CDPPingEvent {
  type: 'ping'
}

type CDPInputEvent = CDPMouseEvent | CDPKeyboardEvent | CDPWheelEvent | CDPPingEvent

// CDP modifiers bitmask
const enum Modifiers {
  None = 0,
  Alt = 1,
  Ctrl = 2,
  Meta = 4,
  Shift = 8
}

// Sandbox viewport dimensions imported from '@/types/liveViewer' at top of file
// to stay in sync with Playwright DEFAULT_VIEWPORT and CDP ScreencastConfig.

/**
 * Calculate CDP modifiers bitmask from keyboard/mouse event
 */
function calculateModifiers(event: KeyboardEvent | MouseEvent): number {
  let modifiers = Modifiers.None
  if (event.altKey) modifiers |= Modifiers.Alt
  if (event.ctrlKey) modifiers |= Modifiers.Ctrl
  if (event.metaKey) modifiers |= Modifiers.Meta
  if (event.shiftKey) modifiers |= Modifiers.Shift
  return modifiers
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
 * Convert browser mouse event type to CDP event type
 */
function browserMouseEventToCDP(
  type: 'mousedown' | 'mouseup' | 'mousemove' | 'click' | 'dblclick'
): 'mousePressed' | 'mouseReleased' | 'mouseMoved' | null {
  switch (type) {
    case 'mousedown':
      return 'mousePressed'
    case 'mouseup':
      return 'mouseReleased'
    case 'mousemove':
      return 'mouseMoved'
    case 'click':
      // CDP doesn't have click - uses pressed+released combination
      return null
    case 'dblclick':
      return 'mousePressed' // Will set click_count: 2
    default:
      return null
  }
}

/**
 * Convert browser keyboard event type to CDP event type
 */
function browserKeyboardEventToCDP(
  type: 'keydown' | 'keyup' | 'keypress'
): 'keyDown' | 'keyUp' | 'char' {
  switch (type) {
    case 'keydown':
      return 'keyDown'
    case 'keyup':
      return 'keyUp'
    case 'keypress':
      return 'char'
    default:
      return 'keyDown'
  }
}

/**
 * Queue size cap to prevent unbounded memory growth
 * when the network is slow or the sandbox is unresponsive.
 */
const MAX_INPUT_QUEUE_SIZE = 200

/**
 * Main composable export
 */
export function useSandboxInput() {
  // Per-instance state (using shallowRef for primitive values per Vue 3 best practices)
  const isForwarding = shallowRef(false)
  const lastError = shallowRef<string | null>(null)

  // Per-instance WebSocket connection and bookkeeping
  let inputWs: WebSocket | null = null
  let inputQueue: CDPInputEvent[] = []
  let flushInterval: number | null = null
  let pingInterval: number | null = null

  /**
   * Send ping message for keep-alive
   */
  function sendPing(): void {
    if (inputWs && inputWs.readyState === WebSocket.OPEN) {
      inputWs.send(JSON.stringify({ type: 'ping' }))
    }
  }

  function stopFlushInterval(): void {
    if (flushInterval) {
      clearInterval(flushInterval)
      flushInterval = null
    }
  }

  function stopPingInterval(): void {
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
  }

  /**
   * Flush queued CDP events to the sandbox
   *
   * CDP protocol expects individual events (one message per event)
   * for immediate processing with <10ms latency.
   */
  function flushInputQueue(): void {
    if (!inputWs || inputWs.readyState !== WebSocket.OPEN || inputQueue.length === 0) {
      return
    }

    // Send all queued events individually (CDP protocol requirement)
    const events = inputQueue.splice(0, inputQueue.length)
    for (const event of events) {
      inputWs.send(JSON.stringify(event))
    }
  }

  /**
   * Queue a CDP input event.
   */
  function queueInput(event: CDPInputEvent): void {
    if (!isForwarding.value) {
      return
    }
    if (inputQueue.length >= MAX_INPUT_QUEUE_SIZE) {
      // Drop oldest events to make room (keep most recent input responsive)
      inputQueue.splice(0, inputQueue.length - MAX_INPUT_QUEUE_SIZE + 1)
    }
    inputQueue.push(event)
  }

  /**
   * Start input forwarding to the sandbox via CDP protocol
   * @param inputWsUrl - Full WebSocket URL for input stream (proxied through backend)
   */
  function startForwarding(inputWsUrl: string): void {
    if (isForwarding.value) {
      return
    }

    try {
      inputWs = new WebSocket(inputWsUrl)

      inputWs.onopen = () => {
        isForwarding.value = true
        lastError.value = null

        // Start flushing queued inputs
        flushInterval = window.setInterval(flushInputQueue, 16) // ~60fps

        // Start ping/pong keep-alive (every 30 seconds)
        pingInterval = window.setInterval(sendPing, 30000)
      }

      inputWs.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)

          switch (msg.type) {
            case 'ready':
              break

            case 'pong':
              // Keep-alive acknowledged
              break

            case 'ack':
              // Input acknowledged
              break

            case 'error':
              console.error('[CDPInput] Server error:', msg.message)
              lastError.value = msg.message
              break

            default:
              console.warn('[CDPInput] Unknown message type:', msg.type)
          }
        } catch (err) {
          console.error('[CDPInput] Failed to parse server message:', err)
        }
      }

      inputWs.onerror = (e) => {
        console.error('[CDPInput] WebSocket error:', e)
        lastError.value = 'CDP input connection error'
      }

      inputWs.onclose = () => {
        isForwarding.value = false
        stopFlushInterval()
        stopPingInterval()
      }
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : 'Failed to connect'
      console.error('[CDPInput] Connection failed:', err)
    }
  }

  /**
   * Stop input forwarding
   */
  function stopForwarding(): void {
    stopFlushInterval()
    stopPingInterval()

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

  /**
   * Handle mouse event and forward to sandbox as CDP event
   */
  function handleMouseEvent(
    event: MouseEvent,
    type: 'mousedown' | 'mouseup' | 'mousemove' | 'click' | 'dblclick',
    elementWidth: number,
    elementHeight: number
  ): void {
    if (!isForwarding.value) return

    // Convert browser event type to CDP event type
    const cdpEventType = browserMouseEventToCDP(type)
    if (!cdpEventType) {
      // Skip unsupported events (e.g., 'click')
      return
    }

    // Get coordinates relative to the element
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
    const clientX = event.clientX - rect.left
    const clientY = event.clientY - rect.top

    const { x, y } = scaleCoordinates(clientX, clientY, elementWidth, elementHeight)

    // Create CDP mouse event
    const cdpEvent: CDPMouseEvent = {
      type: 'mouse',
      event_type: cdpEventType,
      x,
      y,
      button: mouseButtonToName(event.button),
      click_count: type === 'dblclick' ? 2 : 1,
      modifiers: calculateModifiers(event)
    }

    queueInput(cdpEvent)
  }

  /**
   * Handle keyboard event and forward to sandbox as CDP event
   */
  function handleKeyboardEvent(
    event: KeyboardEvent,
    type: 'keydown' | 'keyup' | 'keypress'
  ): void {
    if (!isForwarding.value) return

    // Prevent default browser behavior for forwarded keys
    event.preventDefault()

    // Create CDP keyboard event
    const cdpEvent: CDPKeyboardEvent = {
      type: 'keyboard',
      event_type: browserKeyboardEventToCDP(type),
      key: event.key,
      code: event.code,
      modifiers: calculateModifiers(event)
    }

    // Add text field for character input (single printable character)
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
      cdpEvent.text = event.key
    }

    queueInput(cdpEvent)
  }

  /**
   * Handle scroll event and forward to sandbox as CDP wheel event
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

    // Create CDP wheel event
    const cdpEvent: CDPWheelEvent = {
      type: 'wheel',
      x,
      y,
      delta_x: event.deltaX,
      delta_y: event.deltaY
    }

    queueInput(cdpEvent)
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
