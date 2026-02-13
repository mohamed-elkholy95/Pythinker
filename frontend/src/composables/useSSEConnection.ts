import { ref } from 'vue'

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed'

export function useSSEConnection() {
  const connectionState = ref<ConnectionState>('disconnected')
  const lastEventTime = ref(0)
  const lastEventId = ref<string | undefined>(undefined)
  const retryCount = ref(0)

  function updateLastEventTime() {
    lastEventTime.value = Date.now()
  }

  function isConnectionStale(thresholdMs: number): boolean {
    if (lastEventTime.value === 0) return false
    return Date.now() - lastEventTime.value > thresholdMs
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
    sessionStorage.removeItem(`pythinker-stop-${sessionId}`)
  }

  function resetRetryCount() {
    retryCount.value = 0
  }

  return {
    connectionState,
    lastEventTime,
    lastEventId,
    retryCount,
    updateLastEventTime,
    isConnectionStale,
    persistEventId,
    getPersistedEventId,
    cleanupSessionStorage,
    resetRetryCount,
  }
}
