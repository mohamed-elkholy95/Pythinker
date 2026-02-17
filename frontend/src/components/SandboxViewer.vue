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

    <!-- CDP Screencast View (Konva-powered) -->
    <div v-else-if="enabled" class="sandbox-content-inner">
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
        @frame-received="onFrameReceived"
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
import { useSandboxInput } from '@/composables/useSandboxInput'
import { useWideResearchGlobal } from '@/composables/useWideResearch'
import { getScreencastUrl, getInputStreamUrl } from '@/api/agent'
import { calculateReconnectDelay } from '@/utils/reconnectBackoff'
import type { ToolEventData } from '@/types/event'

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
  }>(),
  {
    viewOnly: true,
    inactiveMessage: "Pythinker's computer is inactive",
    quality: 70,
    maxFps: 15,
    showStats: false,
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

// State
const isLoading = ref(false)
const statusText = ref('Connecting...')
const error = ref<string | null>(null)
const screencastWsUrl = ref<string | null>(null)
const showAgentActions = ref(true)

// Input forwarding
const { isForwarding, startForwarding, stopForwarding, attachInputListeners } = useSandboxInput()
let cleanupInputListeners: (() => void) | null = null

// Wide research state
const { overlayState: wideResearchState, isActive: wideResearchActive } = useWideResearchGlobal()
const showWideResearchOverlay = computed(() => wideResearchActive.value && wideResearchState.value !== null)

// Interactive mode computed
const isInteractive = computed(() => !props.viewOnly && isForwarding.value)

// WebSocket connection
let ws: WebSocket | null = null
let reconnectTimeout: number | null = null
let connectionAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 5
const NON_RETRYABLE_WS_CODES = new Set([1002, 1003, 1007, 1008])
let intentionalClose = false

// Frame heartbeat watchdog — detects connected-but-dead streams
// (e.g., Chrome hung, proxy connected but no frames flowing)
const FRAME_STALL_TIMEOUT_MS = 15_000 // 15s with no frames → stale
const FIRST_FRAME_GRACE_MS = 30_000 // 30s grace for initial page load
let lastFrameReceivedAt = 0
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
      lastFrameReceivedAt = Date.now()
      emit('connected')
      startFrameWatchdog()

      // Start Konva stats tracking
      liveStageRef.value?.startStats()
      // Reset screencast on reconnect
      liveStageRef.value?.resetScreencast()

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
      if (event.data instanceof ArrayBuffer) {
        // Binary frame data — update heartbeat timestamp
        lastFrameReceivedAt = Date.now()
        hasReceivedFirstFrame = true
        // Push frame to Konva renderer
        liveStageRef.value?.pushFrame(event.data)
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
  // Can be used for external hooks or tracking
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
// Frame heartbeat watchdog
// Detects connected-but-dead streams: WebSocket is OPEN but no binary frames
// arrive within FRAME_STALL_TIMEOUT_MS. Triggers proactive reconnect.
// ---------------------------------------------------------------------------

function startFrameWatchdog(): void {
  stopFrameWatchdog()
  hasReceivedFirstFrame = false
  frameWatchdogInterval = window.setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    if (!isTabVisible) return // Don't trigger while tab is hidden

    const elapsed = Date.now() - lastFrameReceivedAt
    // Use longer grace period before the first frame arrives (slow page loads)
    const threshold = hasReceivedFirstFrame ? FRAME_STALL_TIMEOUT_MS : FIRST_FRAME_GRACE_MS

    if (elapsed >= threshold) {
      console.warn(
        `[SandboxViewer] No frame received in ${(elapsed / 1000).toFixed(1)}s ` +
        `(threshold: ${(threshold / 1000).toFixed(0)}s) — stream appears stale, triggering reconnect`
      )
      // Close the zombie connection — onclose handler will trigger reconnect
      stopFrameWatchdog()
      if (ws) {
        try {
          ws.close(4000, 'Frame stall timeout')
        } catch {
          // Ignore
        }
      }
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

// Watch enabled prop
watch(
  () => props.enabled,
  (enabled) => {
    if (enabled) {
      initConnection()
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

  if (props.enabled) {
    initConnection()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  disconnect()
})

/**
 * Forward an agent tool event to the overlay layer.
 * Called by parent components (e.g., ChatPage) when tool events arrive via SSE.
 */
function processToolEvent(event: ToolEventData): void {
  try {
    liveStageRef.value?.processToolEvent(event)
  } catch (e) {
    console.warn('[SandboxViewer] Failed to process tool event:', e)
  }
}

// Expose methods
defineExpose({
  connect: initConnection,
  disconnect,
  reconnect,
  processToolEvent,
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

.sandbox-viewer-wrapper.interactive {
  cursor: crosshair;
}

.sandbox-content-inner {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
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
