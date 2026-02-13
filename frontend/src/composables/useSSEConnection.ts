import { ref } from 'vue'

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed'

export interface SSEConnectionConfig {
  staleThresholdMs?: number
  onStaleDetected?: () => void
}

export function useSSEConnection(config: SSEConnectionConfig = {}) {
  const {
    staleThresholdMs = 60000, // 60 seconds default
    onStaleDetected
  } = config

  const connectionState = ref<ConnectionState>('disconnected')
  const lastEventTime = ref(0)
  const lastHeartbeatTime = ref(0)
  const lastEventId = ref<string | undefined>(undefined)
  const retryCount = ref(0)

  let staleCheckInterval: NodeJS.Timeout | null = null
  let heartbeatEventHandler: ((event: Event) => void) | null = null

  function updateLastEventTime() {
    lastEventTime.value = Date.now()
  }

  function updateLastHeartbeatTime() {
    lastHeartbeatTime.value = Date.now()
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

  function checkStaleConnection() {
    // Only check if connected and we've received at least one event
    if (connectionState.value !== 'connected' || lastEventTime.value === 0) {
      return
    }

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

    // Set up heartbeat event listener if not already set
    if (!heartbeatEventHandler) {
      heartbeatEventHandler = handleHeartbeatEvent
      if (typeof window !== 'undefined') {
        window.addEventListener('sse:heartbeat', heartbeatEventHandler)
      }
    }

    // Check every 10 seconds for stale connection
    staleCheckInterval = setInterval(checkStaleConnection, 10000)
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

  function persistEventId(sessionId: string) {
    if (lastEventId.value && sessionId) {
      sessionStorage.setItem(`pythinker-last-event-${sessionId}`, lastEventId.value)
    }
  }

  function getPersistedEventId(sessionId: string): string | null {
    return sessionStorage.getItem(`pythinker-last-event-${sessionId}`)
  }

  function cleanupSessionStorage(sessionId: string) {
    sessionStorage.removeItem(`pythinker-last-event-${sessionId}`)
    sessionStorage.removeItem(`pythinker-stopped-${sessionId}`)
  }

  function resetRetryCount() {
    retryCount.value = 0
  }

  return {
    connectionState,
    lastEventTime,
    lastHeartbeatTime,
    lastEventId,
    retryCount,
    updateLastEventTime,
    updateLastHeartbeatTime,
    isConnectionStale,
    isHeartbeatStale,
    startStaleDetection,
    stopStaleDetection,
    persistEventId,
    getPersistedEventId,
    cleanupSessionStorage,
    resetRetryCount,
  }
}
