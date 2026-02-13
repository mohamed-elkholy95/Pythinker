import { ref, computed } from 'vue'

export type ResponsePhase = 'idle' | 'connecting' | 'streaming' | 'completing' | 'settled' | 'error' | 'timed_out'

export function useResponsePhase() {
  const phase = ref<ResponsePhase>('idle')
  let settleTimer: ReturnType<typeof setTimeout> | null = null

  const isLoading = computed(() =>
    ['connecting', 'streaming', 'completing'].includes(phase.value)
  )

  const isThinking = computed(() => phase.value === 'connecting')

  const isSettled = computed(() => phase.value === 'settled')

  const isError = computed(() => phase.value === 'error')

  const isTimedOut = computed(() => phase.value === 'timed_out')

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
    isSettled,
    isError,
    isTimedOut,
    transitionTo,
    reset,
  }
}
