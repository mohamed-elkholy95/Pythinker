/**
 * Connection store — manages SSE connection health and response phase.
 *
 * Consolidates state from useSSEConnection and useResponsePhase composables
 * into a single Pinia store for connection lifecycle management.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// ── Response Phase Types ────────────────────────────────────────────
export type ResponsePhase =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'completing'
  | 'settled'
  | 'error'
  | 'timed_out'
  | 'stopped'
  | 'degraded'
  | 'reconnecting'

export type ConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'failed'
  | 'degraded'

// ── Constants ───────────────────────────────────────────────────────
const EVENT_CURSOR_MAX_AGE_MS = 12 * 60 * 60 * 1000 // 12 hours

export const useConnectionStore = defineStore('connection', () => {
  // ── Response Phase State ──────────────────────────────────────────
  const phase = ref<ResponsePhase>('idle')
  let _settleTimer: ReturnType<typeof setTimeout> | null = null

  const isLoading = computed(() =>
    ['connecting', 'streaming', 'completing', 'reconnecting', 'degraded'].includes(phase.value),
  )
  const isThinking = computed(() => phase.value === 'connecting')
  const isStreaming = computed(() => phase.value === 'streaming')
  const isSettled = computed(() => phase.value === 'settled')
  const isError = computed(() => phase.value === 'error')
  const isTimedOut = computed(() => phase.value === 'timed_out')
  const isStopped = computed(() => phase.value === 'stopped')
  const isDegraded = computed(() => phase.value === 'degraded')
  const isReconnecting = computed(() => phase.value === 'reconnecting')

  const statusMessage = computed(() => {
    switch (phase.value) {
      case 'idle':
        return ''
      case 'connecting':
        return 'Thinking...'
      case 'streaming':
        return 'Working...'
      case 'completing':
        return 'Finishing up...'
      case 'settled':
        return ''
      case 'error':
        return 'An error occurred'
      case 'timed_out':
        return 'Request timed out'
      case 'stopped':
        return 'Stopped'
      case 'degraded':
        return 'Stream is slow, waiting...'
      case 'reconnecting':
        return 'Reconnecting...'
      default:
        return ''
    }
  })

  function transitionTo(newPhase: ResponsePhase) {
    if (_settleTimer) {
      clearTimeout(_settleTimer)
      _settleTimer = null
    }
    phase.value = newPhase

    if (newPhase === 'completing') {
      _settleTimer = setTimeout(() => {
        if (phase.value === 'completing') {
          phase.value = 'settled'
        }
      }, 300)
    }
  }

  function resetPhase() {
    if (_settleTimer) {
      clearTimeout(_settleTimer)
      _settleTimer = null
    }
    phase.value = 'idle'
  }

  // ── SSE Connection Health State ───────────────────────────────────
  const connectionState = ref<ConnectionState>('disconnected')
  const lastEventTime = ref(0)
  const lastRealEventTime = ref(0)
  const lastHeartbeatTime = ref(0)
  const lastEventId = ref<string | undefined>(undefined)
  const retryCount = ref(0)
  const totalEvents = ref(0)
  const totalHeartbeats = ref(0)
  const connectionStartTime = ref<number | null>(null)
  const autoRetryCount = ref(0)

  // Error state
  const lastError = ref<{
    message: string
    type: string | null
    recoverable: boolean
    hint: string | null
  } | null>(null)

  const eventRate = computed(() => {
    if (!connectionStartTime.value || totalEvents.value === 0) return 0
    const durationSec = (Date.now() - connectionStartTime.value) / 1000
    return durationSec > 0 ? totalEvents.value / durationSec : 0
  })

  function updateLastEventTime() {
    lastEventTime.value = Date.now()
  }

  function updateLastRealEventTime() {
    lastRealEventTime.value = Date.now()
    lastEventTime.value = Date.now()
    totalEvents.value++
  }

  function updateLastHeartbeatTime() {
    lastHeartbeatTime.value = Date.now()
    lastEventTime.value = Date.now()
    totalHeartbeats.value++
  }

  function setConnectionState(state: ConnectionState) {
    connectionState.value = state
    if (state === 'connected' && !connectionStartTime.value) {
      connectionStartTime.value = Date.now()
    }
  }

  function setLastEventId(id: string) {
    lastEventId.value = id
  }

  function setLastError(error: typeof lastError.value) {
    lastError.value = error
  }

  function clearLastError() {
    lastError.value = null
  }

  function incrementRetryCount() {
    retryCount.value++
  }

  function resetRetryCount() {
    retryCount.value = 0
  }

  function incrementAutoRetryCount() {
    autoRetryCount.value++
  }

  function resetAutoRetryCount() {
    autoRetryCount.value = 0
  }

  // ── Event Cursor Persistence (sessionStorage) ────────────────────
  function persistEventId(sessionId: string) {
    if (!lastEventId.value) return
    try {
      sessionStorage.setItem(
        `pythinker-last-event-${sessionId}`,
        lastEventId.value,
      )
      sessionStorage.setItem(
        `pythinker-last-event-meta-${sessionId}`,
        JSON.stringify({ saved_at: Date.now() }),
      )
    } catch {
      // Silently ignore storage errors
    }
  }

  function getPersistedEventId(sessionId: string): string | undefined {
    try {
      const metaRaw = sessionStorage.getItem(`pythinker-last-event-meta-${sessionId}`)
      if (metaRaw) {
        const meta = JSON.parse(metaRaw)
        if (Date.now() - meta.saved_at > EVENT_CURSOR_MAX_AGE_MS) {
          cleanupSessionStorage(sessionId)
          return undefined
        }
      }
      return sessionStorage.getItem(`pythinker-last-event-${sessionId}`) ?? undefined
    } catch {
      return undefined
    }
  }

  function cleanupSessionStorage(sessionId: string) {
    try {
      sessionStorage.removeItem(`pythinker-last-event-${sessionId}`)
      sessionStorage.removeItem(`pythinker-last-event-meta-${sessionId}`)
    } catch {
      // Silently ignore
    }
  }

  // ── Stale Detection ──────────────────────────────────────────────
  // Backend heartbeat interval is 30s. Thresholds are multiples of this:
  //   Liveness: 1.5× (45s) — tolerates one delayed heartbeat
  //   Stale:    4× (120s) — requires 4 missed heartbeats before declaring stale
  const HEARTBEAT_LIVENESS_MS = 45_000
  const STALE_TIMEOUT_MS = 120_000
  const STALE_CHECK_INTERVAL_MS = 5_000

  const isStale = ref(false)
  let _staleCheckInterval: ReturnType<typeof setInterval> | null = null
  let _heartbeatBridgeHandler: ((event: Event) => void) | null = null

  /** True when heartbeats are arriving within liveness threshold. */
  const isReceivingHeartbeats = computed(() => {
    if (lastHeartbeatTime.value === 0) return false
    return (Date.now() - lastHeartbeatTime.value) < HEARTBEAT_LIVENESS_MS
  })

  function checkStaleConnection() {
    if (!isLoading.value) {
      isStale.value = false
      return
    }
    const timeSinceLastEvent = Date.now() - lastRealEventTime.value
    const timeSinceHeartbeat = lastHeartbeatTime.value > 0
      ? Date.now() - lastHeartbeatTime.value
      : Infinity

    if (
      timeSinceLastEvent > STALE_TIMEOUT_MS
      && timeSinceHeartbeat > STALE_TIMEOUT_MS
      && lastRealEventTime.value > 0
    ) {
      isStale.value = true
    } else if (isStale.value && timeSinceHeartbeat < HEARTBEAT_LIVENESS_MS) {
      // Heartbeat arrived while stale — connection recovered
      isStale.value = false
    }
  }

  function startStaleDetection() {
    // Reset stale state
    isStale.value = false
    updateLastRealEventTime()

    // Start heartbeat bridge (listens for sse:heartbeat custom events from client.ts)
    if (!_heartbeatBridgeHandler) {
      _heartbeatBridgeHandler = () => {
        updateLastHeartbeatTime()
        if (isStale.value) {
          isStale.value = false
        }
      }
      window.addEventListener('sse:heartbeat', _heartbeatBridgeHandler)
    }

    // Start periodic stale check
    if (!_staleCheckInterval) {
      _staleCheckInterval = setInterval(checkStaleConnection, STALE_CHECK_INTERVAL_MS)
    }
  }

  function stopStaleDetection() {
    isStale.value = false

    if (_heartbeatBridgeHandler) {
      window.removeEventListener('sse:heartbeat', _heartbeatBridgeHandler)
      _heartbeatBridgeHandler = null
    }
    if (_staleCheckInterval) {
      clearInterval(_staleCheckInterval)
      _staleCheckInterval = null
    }
  }

  // ── Full Reset ───────────────────────────────────────────────────
  function resetConnection() {
    connectionState.value = 'disconnected'
    lastEventTime.value = 0
    lastRealEventTime.value = 0
    lastHeartbeatTime.value = 0
    lastEventId.value = undefined
    retryCount.value = 0
    totalEvents.value = 0
    totalHeartbeats.value = 0
    connectionStartTime.value = null
    autoRetryCount.value = 0
    lastError.value = null
  }

  function resetAll() {
    resetPhase()
    resetConnection()
  }

  return {
    // Response phase
    phase,
    isLoading,
    isThinking,
    isStreaming,
    isSettled,
    isError,
    isTimedOut,
    isStopped,
    isDegraded,
    isReconnecting,
    statusMessage,
    transitionTo,
    resetPhase,
    // Connection health
    connectionState,
    lastEventTime,
    lastRealEventTime,
    lastHeartbeatTime,
    lastEventId,
    retryCount,
    totalEvents,
    totalHeartbeats,
    connectionStartTime,
    autoRetryCount,
    lastError,
    eventRate,
    updateLastEventTime,
    updateLastRealEventTime,
    updateLastHeartbeatTime,
    setConnectionState,
    setLastEventId,
    setLastError,
    clearLastError,
    incrementRetryCount,
    resetRetryCount,
    incrementAutoRetryCount,
    resetAutoRetryCount,
    persistEventId,
    getPersistedEventId,
    cleanupSessionStorage,
    resetConnection,
    resetAll,
    // Stale detection
    isStale,
    isReceivingHeartbeats,
    checkStaleConnection,
    startStaleDetection,
    stopStaleDetection,
  }
})
