import { ref, computed } from 'vue'

export type ResponsePhase = 'idle' | 'connecting' | 'streaming' | 'completing' | 'settled' | 'error' | 'timed_out' | 'stopped' | 'degraded' | 'reconnecting'

export function useResponsePhase() {
  const phase = ref<ResponsePhase>('idle')
  let settleTimer: ReturnType<typeof setTimeout> | null = null

  const isLoading = computed(() =>
    ['connecting', 'streaming', 'completing', 'reconnecting'].includes(phase.value)
  )

  const isThinking = computed(() => phase.value === 'connecting')

  const isStreaming = computed(() => phase.value === 'streaming')

  const isSettled = computed(() => phase.value === 'settled')

  const isError = computed(() => phase.value === 'error')

  const isTimedOut = computed(() => phase.value === 'timed_out')

  const isStopped = computed(() => phase.value === 'stopped')

  const isDegraded = computed(() => phase.value === 'degraded')

  const isReconnecting = computed(() => phase.value === 'reconnecting')

  /**
   * Get a human-readable status message
   */
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
    // Clear any pending settle timer
    if (settleTimer) {
      clearTimeout(settleTimer)
      settleTimer = null
    }

    phase.value = newPhase

    // Auto-settle from completing after 300ms
    if (newPhase === 'completing') {
      settleTimer = setTimeout(() => {
        if (phase.value === 'completing') {
          phase.value = 'settled'
        }
      }, 300)
    }
  }

  function reset() {
    if (settleTimer) {
      clearTimeout(settleTimer)
      settleTimer = null
    }
    phase.value = 'idle'
  }

  return {
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
    reset,
  }
}
