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

    <!-- CDP Screencast View -->
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

      <!-- Canvas for frame rendering -->
      <canvas
        ref="canvasRef"
        class="sandbox-canvas"
        :class="{ 'view-only': viewOnly }"
        @click="handleCanvasClick"
      ></canvas>

      <!-- Stats overlay (debug mode) -->
      <div v-if="showStats && stats.frameCount > 0" class="sandbox-stats">
        <span>{{ stats.fps.toFixed(1) }} FPS</span>
        <span>{{ formatBytes(stats.bytesPerSec) }}/s</span>
        <span>{{ stats.frameCount }} frames</span>
      </div>

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
import { useSandboxInput } from '@/composables/useSandboxInput'
import { useWideResearchGlobal } from '@/composables/useWideResearch'
import { getScreencastUrl, getInputStreamUrl } from '@/api/agent'
import { calculateReconnectDelay } from '@/utils/reconnectBackoff'

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
    showStats: false
  }
)

const emit = defineEmits<{
  connected: []
  disconnected: [reason?: string]
  error: [error: string]
}>()

// DOM Refs
const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)

// State
const isLoading = ref(false)
const statusText = ref('Connecting...')
const error = ref<string | null>(null)
const screencastWsUrl = ref<string | null>(null)

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

// Canvas context for rendering
let ctx: CanvasRenderingContext2D | null = null

// Stats tracking
const stats = ref({
  frameCount: 0,
  bytesReceived: 0,
  fps: 0,
  bytesPerSec: 0,
  lastFrameTime: 0
})

let statsInterval: number | null = null
let lastStatsTime = Date.now()
let lastStatsFrameCount = 0
let lastStatsBytesReceived = 0

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
      emit('connected')
      startStatsTracking()
      setupCanvas()

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
        // Binary frame data
        displayFrame(event.data)
      } else {
        // JSON message (error or control)
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
      stopStatsTracking()
      cleanupInput()

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

  if (ws) {
    try {
      intentionalClose = true
      ws.close()
    } catch {
      // Ignore
    }
    ws = null
  }

  stopStatsTracking()
  cleanupInput()
  isLoading.value = false
}

function reconnect(): void {
  connectionAttempts = 0
  error.value = null
  initConnection()
}

// Setup canvas for rendering
function setupCanvas(): void {
  if (!canvasRef.value) return

  ctx = canvasRef.value.getContext('2d', {
    alpha: false,
    desynchronized: true // Better performance
  })
}

// Display a frame from binary data on canvas
function displayFrame(data: ArrayBuffer): void {
  if (!canvasRef.value || !ctx) return

  // Create image from blob
  const blob = new Blob([data], { type: 'image/jpeg' })
  const url = URL.createObjectURL(blob)
  const img = new Image()

  img.onload = () => {
    if (!canvasRef.value || !ctx) {
      URL.revokeObjectURL(url)
      return
    }

    // Resize canvas to match image dimensions
    if (canvasRef.value.width !== img.width || canvasRef.value.height !== img.height) {
      canvasRef.value.width = img.width
      canvasRef.value.height = img.height
    }

    // Draw frame
    ctx.drawImage(img, 0, 0)

    // Cleanup
    URL.revokeObjectURL(url)

    // Update stats
    stats.value.frameCount++
    stats.value.bytesReceived += data.byteLength
    stats.value.lastFrameTime = Date.now()
  }

  img.onerror = () => {
    URL.revokeObjectURL(url)
    // Frame decode error - skip frame
  }

  img.src = url
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

// Stats tracking
function startStatsTracking(): void {
  if (statsInterval) return

  lastStatsTime = Date.now()
  lastStatsFrameCount = 0
  lastStatsBytesReceived = 0

  statsInterval = window.setInterval(() => {
    const now = Date.now()
    const elapsed = (now - lastStatsTime) / 1000

    if (elapsed > 0) {
      const frames = stats.value.frameCount - lastStatsFrameCount
      const bytes = stats.value.bytesReceived - lastStatsBytesReceived

      stats.value.fps = frames / elapsed
      stats.value.bytesPerSec = bytes / elapsed

      lastStatsTime = now
      lastStatsFrameCount = stats.value.frameCount
      lastStatsBytesReceived = stats.value.bytesReceived
    }
  }, 1000)
}

function stopStatsTracking(): void {
  if (statsInterval) {
    clearInterval(statsInterval)
    statsInterval = null
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes.toFixed(0)} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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

// Handle canvas click for focus
function handleCanvasClick(): void {
  if (!props.viewOnly && containerRef.value) {
    containerRef.value.focus()
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
  if (props.enabled) {
    initConnection()
  }
})

onBeforeUnmount(() => {
  disconnect()
})

// Expose methods
defineExpose({
  connect: initConnection,
  disconnect,
  reconnect
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
  display: flex;
  align-items: center;
  justify-content: center;
}

.sandbox-canvas {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.sandbox-canvas.view-only {
  pointer-events: none;
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

.sandbox-stats {
  position: absolute;
  bottom: 8px;
  left: 8px;
  display: flex;
  gap: 12px;
  padding: 4px 8px;
  background: var(--background-mask);
  border-radius: 4px;
  font-size: 11px;
  color: var(--function-success);
  font-family: monospace;
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
}

.indicator-dot {
  width: 6px;
  height: 6px;
  background: var(--function-success);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
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
