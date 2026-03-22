<template>
  <div
    ref="containerRef"
    class="sandbox-viewer-wrapper"
    :class="{ 'interactive': isInteractive }"
  >
    <!-- Placeholder for loading/text-only operations -->
    <LoadingState
      v-if="showPlaceholder"
      :label="placeholderLabel || 'Loading'"
      :detail="placeholderDetail"
      :is-active="isActive"
      :animation="placeholderAnimation || 'globe'"
    />

    <!-- Session complete: freeze on the replay screenshot instead of live stream -->
    <div v-else-if="isSessionComplete && replayScreenshotUrl" class="sandbox-content-inner">
      <img
        :src="replayScreenshotUrl"
        class="sandbox-frozen-screenshot"
        alt="Session complete — final state"
      />
    </div>

    <!-- CDP Screencast View (Konva-powered) -->
    <div
      v-else-if="enabled"
      ref="viewerContentRef"
      class="sandbox-content-inner"
      :style="liveStreamCursorStyle"
    >
      <!-- Loading overlay -->
      <div v-if="isLoading" class="sandbox-loading">
        <LoadingState
          label="Connecting to screen"
          :detail="statusText"
          :is-active="true"
          animation="globe"
        />
      </div>

      <!-- Error state -->
      <div v-if="error" class="sandbox-error">
        <span class="sandbox-error-icon">!</span>
        <span class="sandbox-error-text">{{ error }}</span>
        <button @click="reconnect" class="sandbox-retry-btn">Retry</button>
      </div>

      <!-- Konva Live Stage (replaces raw <canvas>) -->
      <KonvaLiveStage
        ref="liveStageRef"
        :enabled="enabled"
        :show-stats="showStats"
        :show-agent-actions="showAgentActions"
        :show-agent-cursor="showAgentCursor"
        @frame-received="onFrameReceived"
      />

      <!-- Browser Interaction Overlay (positioned over KonvaLiveStage) -->
      <BrowserInteractionOverlay
        :last-action="lastBrowserAction"
        :container-width="1280"
        :container-height="1024"
        :scale-x="overlayScaleX"
        :scale-y="overlayScaleY"
      />

      <!-- Interactive mode indicator -->
      <div v-if="isInteractive" class="sandbox-interactive-indicator">
        <span class="indicator-dot"></span>
        <span>Interactive Mode</span>
      </div>
    </div>

    <!-- Inactive state when no session -->
    <InactiveState
      v-else
      :message="inactiveMessage"
    />

    <!-- Wide Research Overlay - Shows when wide_research is active -->
    <WideResearchOverlay
      v-if="showWideResearchOverlay"
      :state="wideResearchState"
    />

    <!-- Take over button slot -->
    <slot name="takeover"></slot>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import LoadingState from '@/components/toolViews/shared/LoadingState.vue'
import InactiveState from '@/components/toolViews/shared/InactiveState.vue'
import WideResearchOverlay from '@/components/WideResearchOverlay.vue'
import KonvaLiveStage from '@/components/KonvaLiveStage.vue'
import BrowserInteractionOverlay from './BrowserInteractionOverlay.vue'
import { useSandboxInput } from '@/composables/useSandboxInput'
import { useWideResearchGlobal } from '@/composables/useWideResearch'
import { useSkillEvents } from '@/composables/useSkillEvents'
import { getScreencastUrl, getInputStreamUrl } from '@/api/agent'
import { calculateReconnectDelay } from '@/utils/reconnectBackoff'
import { SANDBOX_WIDTH, SANDBOX_HEIGHT } from '@/types/liveViewer'
import { getApplePointerCursorCss } from '@/utils/appleCursorStyle'
import type { ToolEventData } from '@/types/event'
import type { SkillEventData } from '@/composables/useSkillEvents'

const props = withDefaults(
  defineProps<{
    sessionId: string
    enabled: boolean
    viewOnly?: boolean
    showPlaceholder?: boolean
    placeholderLabel?: string
    placeholderDetail?: string
    placeholderAnimation?: 'globe' | 'search' | 'file' | 'terminal' | 'code' | 'spinner' | 'check'
    isActive?: boolean
    inactiveMessage?: string
    quality?: number
    maxFps?: number
    showStats?: boolean
    /** When true, disconnects the live stream and shows replayScreenshotUrl as a frozen frame. */
    isSessionComplete?: boolean
    /** URL of the final screenshot to display when the session is complete. */
    replayScreenshotUrl?: string
  }>(),
  {
    viewOnly: true,
    inactiveMessage: "Pythinker's computer is inactive",
    quality: 70,
    maxFps: 15,
    showStats: false,
    isSessionComplete: false,
    replayScreenshotUrl: '',
  }
)

const emit = defineEmits<{
  connected: []
  disconnected: [reason?: string]
  error: [error: string]
}>()

// DOM Refs
const containerRef = ref<HTMLDivElement | null>(null)
const liveStageRef = ref<InstanceType<typeof KonvaLiveStage> | null>(null)
const viewerContentRef = ref<HTMLDivElement | null>(null)

// State
const isLoading = ref(false)
const statusText = ref('Connecting...')
const error = ref<string | null>(null)
const screencastWsUrl = ref<string | null>(null)
const showAgentActions = ref(true)
const showAgentCursor = ref(true)

const liveStreamCursorStyle = { cursor: getApplePointerCursorCss() }

// Input forwarding
const { isForwarding, startForwarding, stopForwarding, attachInputListeners } = useSandboxInput()
let cleanupInputListeners: (() => void) | null = null

// Wide research state
const { overlayState: wideResearchState, isActive: wideResearchActive } = useWideResearchGlobal()
const showWideResearchOverlay = computed(() => wideResearchActive.value && wideResearchState.value !== null)

// Agent UX v2 state
const { activeSkillList: _activeSkillList, handleSkillEvent, reset: resetSkills } = useSkillEvents()
const currentPhase = ref('idle')
const currentToolName = ref<string | undefined>()
const currentToolDetail = ref<string | undefined>()
const stepProgress = ref<string | undefined>()

const lastBrowserAction = ref<{
  type: 'navigate' | 'click' | 'scroll_up' | 'scroll_down' | 'type'
  url?: string
  x?: number
  y?: number
  text?: string
}>()

// Scale factors for overlay coordinate mapping (based on KonvaLiveStage dimensions)
const overlayScaleX = ref(1)
const overlayScaleY = ref(1)
let overlayResizeObserver: ResizeObserver | null = null

/** Compute overlay scale from the actual rendered container size.
 *  Uses offsetWidth/offsetHeight to get layout dimensions before ancestor
 *  CSS transforms (avoids double-scaling inside mini preview). */
function updateOverlayScale() {
  if (!viewerContentRef.value) return
  const w = viewerContentRef.value.offsetWidth
  const h = viewerContentRef.value.offsetHeight
  if (w > 0 && h > 0) {
    overlayScaleX.value = w / SANDBOX_WIDTH
    overlayScaleY.value = h / SANDBOX_HEIGHT
  }
}

// Interactive mode computed
const isInteractive = computed(() => !props.viewOnly && isForwarding.value)

// WebSocket connection
let ws: WebSocket | null = null
let reconnectTimeout: number | null = null
let connectionAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 5
const NON_RETRYABLE_WS_CODES = new Set([1002, 1003, 1007, 1008])
let intentionalClose = false

// Connection liveness watchdog — detects dead streams
// (e.g., Chrome hung, proxy died, backend crashed)
// NOTE: Chrome's Page.startScreencast only sends frames when the compositor
// produces new content. On static pages, no frames are sent after the
// initial capture. The sandbox sends "ping" every 5s — as long as pings
// flow, the connection chain is alive and we should NOT reconnect.
// The watchdog therefore tracks ANY message (frames + pings) for liveness.
const CONNECTION_STALL_TIMEOUT_MS = 120_000 // 120s with no messages at all → dead connection
const FIRST_FRAME_GRACE_MS = 30_000 // 30s grace for initial frame (slow page loads)
let lastMessageReceivedAt = 0 // Any WebSocket message (frame, ping, JSON)
let lastFrameReceivedAt = 0 // Binary frames only — for first-frame tracking
let hasReceivedFirstFrame = false
let frameWatchdogInterval: number | null = null

// Page Visibility API — pause reconnects when tab is hidden
let isTabVisible = true

// Fetch screencast URL (proxied through backend) and connect
async function initConnection(): Promise<void> {
  if (!props.enabled || !props.sessionId) {
    return
  }

  isLoading.value = true
  statusText.value = 'Connecting...'
  error.value = null

  try {
    screencastWsUrl.value = await getScreencastUrl(props.sessionId, props.quality, props.maxFps)
    if (screencastWsUrl.value) {
      await connect()
    } else {
      handleError('Failed to get screencast URL')
    }
  } catch (e) {
    handleError(`Failed to initialize: ${formatError(e)}`)
  }
}

// Connect to WebSocket stream (proxied through backend)
async function connect(): Promise<void> {
  if (ws) {
    disconnect()
  }

  if (!props.enabled || !screencastWsUrl.value) {
    return
  }

  const wsUrl = screencastWsUrl.value

  isLoading.value = true
  statusText.value = 'Connecting...'
  error.value = null

  try {
    intentionalClose = false
    ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      isLoading.value = false
      connectionAttempts = 0
      lastMessageReceivedAt = Date.now()
      lastFrameReceivedAt = Date.now()
      emit('connected')
      startFrameWatchdog()

      // Start Konva stats tracking
      liveStageRef.value?.startStats()
      // Reset screencast on reconnect — force backend viewport dimensions
      // so auto-fit recalculates correctly (prevents "zoomed in" after crash)
      liveStageRef.value?.resetScreencast()
      liveStageRef.value?.forceDimensionReset(1280, 1024)

      // Setup input forwarding if not view-only
      if (!props.viewOnly && props.sessionId) {
        getInputStreamUrl(props.sessionId).then((inputUrl) => {
          startForwarding(inputUrl)
          setupInputListeners()
        }).catch((e) => {
          console.warn('Failed to setup input forwarding:', e)
        })
      }
    }

    ws.onmessage = (event) => {
      // Track ANY message for connection liveness (frames, pings, JSON)
      lastMessageReceivedAt = Date.now()

      if (event.data instanceof ArrayBuffer) {
        // Binary frame data
        lastFrameReceivedAt = Date.now()
        hasReceivedFirstFrame = true
        // Push frame to Konva renderer
        try {
          liveStageRef.value?.pushFrame(event.data)
        } catch (e) {
          console.warn('[SandboxViewer] Frame push failed:', e)
        }
      } else if (typeof event.data === 'string') {
        // Text message: JSON control or server ping
        if (event.data === 'ping') {
          // Respond to server-side ping with pong
          try {
            ws?.send('pong')
          } catch {
            // WebSocket may be closing
          }
          return
        }
        try {
          const msg = JSON.parse(event.data)
          if (msg.error) {
            handleError(msg.error)
          }
        } catch {
          // Not JSON, ignore
        }
      }
    }

    ws.onerror = () => {
      handleError('Connection error')
    }

    ws.onclose = (e) => {
      ws = null
      stopFrameWatchdog()
      cleanupInput()

      // Stop Konva stats tracking
      liveStageRef.value?.stopStats()

      if (intentionalClose) {
        return
      }

      const closeReason = e.reason || `WebSocket closed (code ${e.code})`
      emit('disconnected', closeReason)

      const nonRetryableByCode = NON_RETRYABLE_WS_CODES.has(e.code)
      const normalizedReason = closeReason.toLowerCase()
      const nonRetryableByReason =
        normalizedReason.includes('session or sandbox not found') ||
        normalizedReason.includes('sandbox not found') ||
        normalizedReason.includes('session not found') ||
        normalizedReason.includes('invalid signature') ||
        normalizedReason.includes('expired')
      const shouldRetry = !nonRetryableByCode && !nonRetryableByReason

      if (props.enabled && shouldRetry && connectionAttempts < MAX_RECONNECT_ATTEMPTS) {
        // Don't attempt reconnect while tab is hidden — save resources
        // and avoid thundering herd on tab refocus. The visibility handler
        // will trigger a fresh reconnect when the tab becomes visible.
        if (!isTabVisible) {
          statusText.value = 'Paused (tab hidden)'
          isLoading.value = true
          return
        }

        const delay = calculateReconnectDelay(connectionAttempts)
        connectionAttempts++
        statusText.value = `Reconnecting in ${(delay / 1000).toFixed(1)}s...`
        isLoading.value = true

        reconnectTimeout = window.setTimeout(() => {
          // Refresh signed URL for each reconnect attempt to avoid stale links.
          screencastWsUrl.value = null
          initConnection()
        }, delay)
      } else {
        emit('error', closeReason)
      }
    }
  } catch (e) {
    handleError(`Failed to connect: ${formatError(e)}`)
  }
}

function disconnect(): void {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
    reconnectTimeout = null
  }

  stopFrameWatchdog()

  if (ws) {
    try {
      intentionalClose = true
      ws.close()
    } catch {
      // Ignore
    }
    ws = null
  }

  liveStageRef.value?.stopStats()
  cleanupInput()
  isLoading.value = false
}

function reconnect(): void {
  connectionAttempts = 0
  error.value = null
  initConnection()
}

function handleError(msg: string): void {
  error.value = msg
  isLoading.value = false
  emit('error', msg)
}

function formatError(err: unknown): string {
  if (typeof err === 'string') return err
  if (err && typeof err === 'object') {
    const maybeErr = err as { code?: number; message?: string; details?: unknown }
    const parts: string[] = []
    if (typeof maybeErr.code === 'number') parts.push(String(maybeErr.code))
    if (typeof maybeErr.message === 'string' && maybeErr.message.trim()) parts.push(maybeErr.message)
    if (parts.length > 0) return parts.join(' ')

    if (maybeErr.details && typeof maybeErr.details === 'object') {
      const details = maybeErr.details as { detail?: string; msg?: string; message?: string }
      if (typeof details.detail === 'string' && details.detail.trim()) return details.detail
      if (typeof details.msg === 'string' && details.msg.trim()) return details.msg
      if (typeof details.message === 'string' && details.message.trim()) return details.message
    }
  }
  return 'Unknown error'
}

// Frame received callback (from KonvaLiveStage)
function onFrameReceived(): void {
  // Update overlay scale on each frame in case the container resized
  updateOverlayScale()
}

// Input forwarding setup
function setupInputListeners(): void {
  if (!containerRef.value || props.viewOnly) return

  cleanupInputListeners = attachInputListeners(containerRef.value)
}

function cleanupInput(): void {
  stopForwarding()
  if (cleanupInputListeners) {
    cleanupInputListeners()
    cleanupInputListeners = null
  }
}

// ---------------------------------------------------------------------------
// Connection liveness watchdog
// Detects dead streams: WebSocket is OPEN but no messages at all (not even
// server pings) arrive within CONNECTION_STALL_TIMEOUT_MS. Before the first
// frame, uses FIRST_FRAME_GRACE_MS to allow slow page loads. After the first
// frame, pings count as proof of life (Chrome sends no frames on static pages).
// ---------------------------------------------------------------------------

function startFrameWatchdog(): void {
  stopFrameWatchdog()
  hasReceivedFirstFrame = false
  frameWatchdogInterval = window.setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    if (!isTabVisible) return // Don't trigger while tab is hidden

    const now = Date.now()

    // Before the first binary frame: use generous grace period.
    // Even if pings arrive, we want at least one frame before relaxing.
    if (!hasReceivedFirstFrame) {
      const frameElapsed = now - lastFrameReceivedAt
      if (frameElapsed >= FIRST_FRAME_GRACE_MS) {
        console.warn(
          `[SandboxViewer] No initial frame in ${(frameElapsed / 1000).toFixed(1)}s — ` +
          `triggering reconnect`
        )
        stopFrameWatchdog()
        try { ws?.close(4000, 'First frame timeout') } catch { /* noop */ }
      }
      return
    }

    // After first frame: check connection liveness via ANY message (including pings).
    // Chrome only sends screencast frames when the compositor produces new content.
    // On static pages, pings (every 5s) are the only proof of life — that's fine.
    const messageElapsed = now - lastMessageReceivedAt
    if (messageElapsed >= CONNECTION_STALL_TIMEOUT_MS) {
      console.warn(
        `[SandboxViewer] No message received in ${(messageElapsed / 1000).toFixed(1)}s ` +
        `(threshold: ${(CONNECTION_STALL_TIMEOUT_MS / 1000).toFixed(0)}s) — ` +
        `connection appears dead, triggering reconnect`
      )
      stopFrameWatchdog()
      try { ws?.close(4000, 'Connection stall timeout') } catch { /* noop */ }
    }
  }, 3000) // Check every 3s
}

function stopFrameWatchdog(): void {
  if (frameWatchdogInterval) {
    clearInterval(frameWatchdogInterval)
    frameWatchdogInterval = null
  }
}

// ---------------------------------------------------------------------------
// Page Visibility API
// Pauses reconnection attempts when the tab is hidden to prevent wasted
// cycles and thundering herd on tab refocus. On visibility restore, triggers
// a fresh reconnect if the connection was lost while hidden.
// ---------------------------------------------------------------------------

function handleVisibilityChange(): void {
  isTabVisible = !document.hidden

  if (isTabVisible) {
    // Tab became visible — check if we need to reconnect
    if (props.enabled && !ws && !reconnectTimeout) {
      // Connection was lost while tab was hidden, reconnect now
      connectionAttempts = 0
      initConnection()
    } else if (ws && ws.readyState === WebSocket.OPEN) {
      // Connection still alive — reset watchdog baseline
      lastMessageReceivedAt = Date.now()
      lastFrameReceivedAt = Date.now()
    }
  } else {
    // Tab is hidden — cancel pending reconnect timers to save resources
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }
  }
}

// Start ResizeObserver when the viewer content container becomes available
watch(viewerContentRef, (el) => {
  if (overlayResizeObserver) {
    overlayResizeObserver.disconnect()
    overlayResizeObserver = null
  }
  if (el) {
    overlayResizeObserver = new ResizeObserver(() => {
      updateOverlayScale()
    })
    overlayResizeObserver.observe(el)
    updateOverlayScale()
  }
})

// When session completes, disconnect the live stream — the frozen screenshot takes over.
watch(
  () => props.isSessionComplete,
  (complete) => {
    if (complete) {
      disconnect()
    }
  }
)

// Watch enabled prop
watch(
  () => props.enabled,
  (enabled) => {
    if (enabled) {
      // Don't reconnect if session is already complete
      if (!props.isSessionComplete) {
        initConnection()
      }
    } else {
      disconnect()
    }
  }
)

// Watch viewOnly prop
watch(
  () => props.viewOnly,
  (viewOnly) => {
    if (viewOnly) {
      cleanupInput()
    } else if (ws && ws.readyState === WebSocket.OPEN && props.sessionId) {
      getInputStreamUrl(props.sessionId).then((inputUrl) => {
        startForwarding(inputUrl)
        setupInputListeners()
      }).catch((e) => {
        console.warn('Failed to setup input forwarding:', e)
      })
    }
  }
)

// Watch sessionId prop
watch(
  () => props.sessionId,
  () => {
    // Reset Agent UX v2 state on session change
    resetSkills()
    currentPhase.value = 'idle'
    currentToolName.value = undefined
    currentToolDetail.value = undefined
    stepProgress.value = undefined
    lastBrowserAction.value = undefined

    if (props.enabled) {
      disconnect()
      nextTick(() => {
        initConnection()
      })
    }
  }
)

// Lifecycle
onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  isTabVisible = !document.hidden

  // Observe the viewer content container for resize to keep overlay scale accurate
  if (viewerContentRef.value) {
    overlayResizeObserver = new ResizeObserver(() => {
      updateOverlayScale()
    })
    overlayResizeObserver.observe(viewerContentRef.value)
  }

  if (props.enabled) {
    initConnection()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  if (overlayResizeObserver) {
    overlayResizeObserver.disconnect()
    overlayResizeObserver = null
  }
  disconnect()
})

/**
 * Forward an agent tool event to the overlay layer.
 * Called by parent components (e.g., ChatPage) when tool events arrive via SSE.
 */
function processToolEvent(event: ToolEventData): void {
  try {
    liveStageRef.value?.processToolEvent(event)
    updateBrowserAction(event)
  } catch (e) {
    console.warn('[SandboxViewer] Failed to process tool event:', e)
  }
}

/**
 * Update browser interaction overlay state from tool events.
 * Maps tool function names to visual actions (navigate, click, scroll).
 */
function updateBrowserAction(event: ToolEventData): void {
  if (!event.function) return

  const action = event.function
  if (action === 'navigate' || action === 'browser_navigate') {
    lastBrowserAction.value = {
      type: 'navigate',
      url: (event.args?.url as string) || (event.args?.goal as string) || '',
    }
  } else if (action === 'click' || action === 'browser_click') {
    lastBrowserAction.value = {
      type: 'click',
      x: (event.args?.x ?? event.args?.coordinate_x) as number | undefined,
      y: (event.args?.y ?? event.args?.coordinate_y) as number | undefined,
    }
  } else if (action === 'scroll_up') {
    lastBrowserAction.value = { type: 'scroll_up' }
  } else if (action === 'scroll_down') {
    lastBrowserAction.value = { type: 'scroll_down' }
  }

  // Update current tool display
  currentToolName.value = event.name || event.function
  currentToolDetail.value = (event.args?.url as string) || (event.args?.goal as string) || undefined
}

/**
 * Handle SkillEvent SSE data to update the activity bar.
 */
function handleSkillSSEEvent(data: SkillEventData): void {
  handleSkillEvent(data)
}

// Expose methods
defineExpose({
  connect: initConnection,
  disconnect,
  reconnect,
  processToolEvent,
  handleSkillSSEEvent,
  liveStage: liveStageRef,
})
</script>

<style scoped>
.sandbox-viewer-wrapper {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--background-gray-main);
  overflow: hidden;
}

.sandbox-content-inner {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}

.sandbox-frozen-screenshot {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: var(--background-gray-main);
}

.sandbox-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10;
}

.sandbox-error {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--background-gray-main);
  z-index: 10;
}

.sandbox-error-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--function-error);
  color: var(--text-white);
  border-radius: 50%;
  font-weight: bold;
  font-size: 18px;
}

.sandbox-error-text {
  color: var(--function-error);
  font-size: 13px;
  max-width: 300px;
  text-align: center;
}

.sandbox-retry-btn {
  padding: 6px 16px;
  background: var(--background-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.sandbox-retry-btn:hover {
  background: var(--background-hover);
  border-color: var(--border-hover);
}

.sandbox-interactive-indicator {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: var(--function-success-tsp);
  border: 1px solid var(--function-success-border);
  border-radius: 4px;
  font-size: 11px;
  color: var(--function-success);
  z-index: 20;
}

.indicator-dot {
  width: 6px;
  height: 6px;
  background: var(--function-success);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>
