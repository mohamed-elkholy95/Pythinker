/**
 * @deprecated Stale detection and connection health monitoring have been
 * consolidated into `useConnectionStore` (Pinia). This composable remains
 * as a thin facade for backward compatibility but should not be used by
 * new consumers. Prefer `useConnectionStore` directly.
 */
import { ref, computed, onScopeDispose } from 'vue'

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed' | 'degraded'

const EVENT_CURSOR_STORAGE_PREFIX = 'pythinker-last-event-'
const EVENT_CURSOR_META_STORAGE_PREFIX = 'pythinker-last-event-meta-'
const EVENT_CURSOR_MAX_AGE_MS = 12 * 60 * 60 * 1000 // 12h

export interface SSEConnectionConfig {
  staleThresholdMs?: number
  degradedThresholdMs?: number // Time without real events before considering degraded
  onStaleDetected?: () => void
  onDegradedDetected?: () => void
}

export interface StreamHealthMetrics {
  /** Total events received (excluding heartbeats) */
  totalEvents: number
  /** Total heartbeats received */
  totalHeartbeats: number
  /** Events per second rate */
  eventRate: number
  /** Time since last real event in ms */
  timeSinceLastEvent: number
  /** Time since last heartbeat in ms */
  timeSinceLastHeartbeat: number
  /** Whether only receiving heartbeats */
  isHeartbeatOnly: boolean
  /** Connection duration in ms */
  connectionDuration: number
}

export function useSSEConnection(config: SSEConnectionConfig = {}) {
  const {
    staleThresholdMs = 120000, // 120 seconds (4× heartbeat interval) — no events at all
    degradedThresholdMs = 180000, // 180 seconds (6× heartbeat interval) — heartbeats only, no real events
    onStaleDetected,
    onDegradedDetected
  } = config

  const connectionState = ref<ConnectionState>('disconnected')
  const lastEventTime = ref(0)
  const lastRealEventTime = ref(0) // Track real events separately
  const lastHeartbeatTime = ref(0)
  const lastEventId = ref<string | undefined>(undefined)
  const retryCount = ref(0)

  // Enhanced tracking for stream health
  const totalEvents = ref(0)
  const totalHeartbeats = ref(0)
  const connectionStartTime = ref<number | null>(null)

  let staleCheckInterval: NodeJS.Timeout | null = null
  let heartbeatEventHandler: ((event: Event) => void) | null = null
  let degradedEmitted = false

  function updateLastEventTime() {
    lastEventTime.value = Date.now()
  }

  function updateLastRealEventTime() {
    lastRealEventTime.value = Date.now()
    lastEventTime.value = Date.now()
    totalEvents.value += 1
    // Reset degraded flag when we get a real event
    degradedEmitted = false
    if (connectionState.value === 'degraded') {
      connectionState.value = 'connected'
    }
  }

  function updateLastHeartbeatTime() {
    lastHeartbeatTime.value = Date.now()
    totalHeartbeats.value += 1
    // Heartbeat also counts as an event for general staleness
    updateLastEventTime()
  }

  function isConnectionStale(thresholdMs: number = staleThresholdMs): boolean {
    if (lastEventTime.value === 0) return false
    return Date.now() - lastEventTime.value > thresholdMs
  }

  function isHeartbeatStale(thresholdMs: number = staleThresholdMs): boolean {
    if (lastHeartbeatTime.value === 0) return false
    return Date.now() - lastHeartbeatTime.value > thresholdMs
  }

  /**
   * Check if we're only receiving heartbeats (no real events)
   * This indicates the backend may be stuck but connection is still alive
   */
  function isReceivingOnlyHeartbeats(thresholdMs: number = degradedThresholdMs): boolean {
    // If we've never received a real event, not degraded yet
    if (lastRealEventTime.value === 0) return false
    // If we've never received a heartbeat, can't determine
    if (lastHeartbeatTime.value === 0) return false
    // Degraded if heartbeats are recent but real events are old
    const heartbeatRecent = Date.now() - lastHeartbeatTime.value <= thresholdMs
    const realEventsStale = Date.now() - lastRealEventTime.value >= thresholdMs
    return heartbeatRecent && realEventsStale
  }

  /**
   * Calculate events per second rate
   */
  const eventRate = computed((): number => {
    if (connectionStartTime.value === null) return 0
    const durationMs = Date.now() - connectionStartTime.value
    if (durationMs === 0) return 0
    const durationSeconds = durationMs / 1000
    return totalEvents.value / durationSeconds
  })

  /**
   * Get comprehensive stream health metrics.
   * Returns a fresh snapshot each call (Date.now() is not reactive).
   */
  function getHealthMetrics(): StreamHealthMetrics {
    const now = Date.now()
    return {
      totalEvents: totalEvents.value,
      totalHeartbeats: totalHeartbeats.value,
      eventRate: eventRate.value,
      timeSinceLastEvent: lastEventTime.value ? now - lastEventTime.value : 0,
      timeSinceLastHeartbeat: lastHeartbeatTime.value ? now - lastHeartbeatTime.value : 0,
      isHeartbeatOnly: isReceivingOnlyHeartbeats(),
      connectionDuration: connectionStartTime.value !== null ? now - connectionStartTime.value : 0,
    }
  }

  function checkStaleConnection() {
    // Only check if connected and we've received at least one event
    if (connectionState.value !== 'connected' || lastEventTime.value === 0) {
      return
    }

    // Check for degraded state (heartbeats only)
    if (isReceivingOnlyHeartbeats() && !degradedEmitted) {
      connectionState.value = 'degraded'
      console.warn(`[SSE] Stream degraded - only receiving heartbeats, no real events for ${degradedThresholdMs}ms`)
      degradedEmitted = true
      if (onDegradedDetected) {
        onDegradedDetected()
      }
      return
    }

    // Check for fully stale connection
    if (isConnectionStale(staleThresholdMs)) {
      console.warn(`[SSE] Connection stale - no events for ${staleThresholdMs}ms`)
      if (onStaleDetected) {
        onStaleDetected()
      }
    }
  }

  function handleHeartbeatEvent(event: Event) {
    const customEvent = event as CustomEvent
    const { eventId } = customEvent.detail
    updateLastHeartbeatTime()
    if (eventId) {
      lastEventId.value = eventId
    }
  }

  function startStaleDetection() {
    if (staleCheckInterval) return

    connectionState.value = 'connected'

    // Track connection start time
    connectionStartTime.value = Date.now()

    // Reset counters
    totalEvents.value = 0
    totalHeartbeats.value = 0
    degradedEmitted = false

    // Set up heartbeat event listener if not already set
    if (!heartbeatEventHandler) {
      heartbeatEventHandler = handleHeartbeatEvent
      if (typeof window !== 'undefined') {
        window.addEventListener('sse:heartbeat', heartbeatEventHandler)
      }
    }

    // Check frequently enough to detect degraded mode before crossing stale thresholds.
    const checkIntervalMs = Math.max(
      1000,
      Math.min(10000, Math.floor(Math.min(staleThresholdMs, degradedThresholdMs) / 2)),
    )
    staleCheckInterval = setInterval(checkStaleConnection, checkIntervalMs)
  }

  function stopStaleDetection() {
    if (staleCheckInterval) {
      clearInterval(staleCheckInterval)
      staleCheckInterval = null
    }

    // Clean up heartbeat event listener
    if (heartbeatEventHandler) {
      if (typeof window !== 'undefined') {
        window.removeEventListener('sse:heartbeat', heartbeatEventHandler)
      }
      heartbeatEventHandler = null
    }
  }

  function eventCursorStorageKey(sessionId: string): string {
    return `${EVENT_CURSOR_STORAGE_PREFIX}${sessionId}`
  }

  function eventCursorMetaStorageKey(sessionId: string): string {
    return `${EVENT_CURSOR_META_STORAGE_PREFIX}${sessionId}`
  }

  function persistEventId(sessionId: string) {
    if (lastEventId.value && sessionId) {
      sessionStorage.setItem(eventCursorStorageKey(sessionId), lastEventId.value)
      sessionStorage.setItem(
        eventCursorMetaStorageKey(sessionId),
        JSON.stringify({ saved_at: Date.now() }),
      )
    }
  }

  function getPersistedEventId(sessionId: string): string | null {
    if (!sessionId) {
      return null
    }

    const eventId = sessionStorage.getItem(eventCursorStorageKey(sessionId))
    if (!eventId) {
      return null
    }

    // Defensive guard against corrupted oversized values.
    if (eventId.length > 2048) {
      cleanupSessionStorage(sessionId)
      return null
    }

    const metadataRaw = sessionStorage.getItem(eventCursorMetaStorageKey(sessionId))
    if (!metadataRaw) {
      // Backward-compatible support for legacy cursor-only entries.
      return eventId
    }

    try {
      const metadata = JSON.parse(metadataRaw) as { saved_at?: number }
      const savedAt = metadata.saved_at
      if (typeof savedAt !== 'number' || !Number.isFinite(savedAt)) {
        cleanupSessionStorage(sessionId)
        return null
      }

      if (Date.now() - savedAt > EVENT_CURSOR_MAX_AGE_MS) {
        cleanupSessionStorage(sessionId)
        return null
      }
    } catch {
      cleanupSessionStorage(sessionId)
      return null
    }

    return eventId
  }

  function cleanupSessionStorage(sessionId: string) {
    sessionStorage.removeItem(eventCursorStorageKey(sessionId))
    sessionStorage.removeItem(eventCursorMetaStorageKey(sessionId))
    sessionStorage.removeItem(`pythinker-stopped-${sessionId}`)
  }

  function resetRetryCount() {
    retryCount.value = 0
  }

  function reset() {
    connectionState.value = 'disconnected'
    lastEventTime.value = 0
    lastRealEventTime.value = 0
    lastHeartbeatTime.value = 0
    lastEventId.value = undefined
    retryCount.value = 0
    totalEvents.value = 0
    totalHeartbeats.value = 0
    connectionStartTime.value = null
    degradedEmitted = false
    stopStaleDetection()
  }

  // onScopeDispose runs in any reactive scope (component setup, effectScope,
  // Pinia store), so heartbeat listeners are always cleaned up regardless of
  // the call site (IMPORTANT-5). getCurrentInstance() guard is no longer needed.
  onScopeDispose(() => {
    stopStaleDetection()
  })

  return {
    connectionState,
    lastEventTime,
    lastRealEventTime,
    lastHeartbeatTime,
    lastEventId,
    retryCount,
    totalEvents,
    totalHeartbeats,
    connectionStartTime,
    eventRate,
    getHealthMetrics,
    updateLastEventTime,
    updateLastRealEventTime,
    updateLastHeartbeatTime,
    isConnectionStale,
    isHeartbeatStale,
    isReceivingOnlyHeartbeats,
    startStaleDetection,
    stopStaleDetection,
    persistEventId,
    getPersistedEventId,
    cleanupSessionStorage,
    resetRetryCount,
    reset,
  }
}
