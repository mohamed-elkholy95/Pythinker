import { computed, ref } from 'vue'

import { createSSEConnection } from '@/api/client'
import { useConnectionStore } from '@/stores/connectionStore'

export interface FetchProgressEvent {
  event_id?: string
  phase: string
  url?: string
  mode?: string
  status?: string
  final_url?: string
  tier_used?: string
  from_cache?: boolean
  response_time_ms?: number
  content_length?: number
  error?: string | null
  suggested_mode?: string | null
}

export function useBrowserWorkflow() {
  const connectionStore = useConnectionStore()
  const events = ref<FetchProgressEvent[]>([])
  const isStreaming = ref(false)
  const lastError = ref<string | null>(null)
  let cancelStream: (() => void) | null = null
  let activeAttempt = 0

  const lastProgress = computed(() => {
    if (events.value.length === 0) {
      return null
    }
    return events.value[events.value.length - 1] ?? null
  })
  const hasError = computed(() => Boolean(lastError.value))

  async function fetchStream(url: string, mode: string = 'dynamic') {
    stopStreaming({ preservePhase: true })

    activeAttempt += 1
    const attemptId = activeAttempt
    events.value = []
    lastError.value = null
    isStreaming.value = true

    connectionStore.clearLastError()
    connectionStore.resetRetryCount()
    connectionStore.transitionTo('connecting')
    connectionStore.setConnectionState('connecting')
    connectionStore.startStaleDetection()

    const query = new URLSearchParams({ url, mode }).toString()
    cancelStream = await createSSEConnection<FetchProgressEvent>(
      `/browser-workflow/fetch/stream?${query}`,
      { method: 'GET' },
      {
        onOpen: () => {
          if (attemptId !== activeAttempt) return
          connectionStore.setConnectionState('connected')
        },
        onMessage: ({ event, data }) => {
          if (attemptId !== activeAttempt || event !== 'progress') return

          events.value.push(data)
          connectionStore.updateLastRealEventTime()

          if (data.event_id) {
            connectionStore.setLastEventId(data.event_id)
          }

          if (connectionStore.phase === 'connecting' || connectionStore.phase === 'reconnecting') {
            connectionStore.transitionTo('streaming')
          }

          if (data.phase === 'failed' && data.error) {
            lastError.value = data.error
            connectionStore.setLastError({
              message: data.error,
              type: 'browser_workflow',
              recoverable: Boolean(data.suggested_mode),
              hint: data.suggested_mode ? `Try ${data.suggested_mode} mode.` : null,
            })
            isStreaming.value = false
            connectionStore.stopStaleDetection()
            connectionStore.setConnectionState('failed')
            connectionStore.transitionTo('error')
            return
          }

          if (data.phase === 'completed') {
            isStreaming.value = false
            connectionStore.stopStaleDetection()
            connectionStore.setConnectionState('connected')
            connectionStore.transitionTo('settled')
          }
        },
        onRetry: () => {
          if (attemptId !== activeAttempt) return
          connectionStore.incrementRetryCount()
          connectionStore.setConnectionState('reconnecting')
          connectionStore.transitionTo('reconnecting')
        },
        onGapDetected: (info) => {
          if (attemptId !== activeAttempt) return
          if (info.checkpointEventId) {
            connectionStore.setLastEventId(info.checkpointEventId)
          }
        },
        onClose: (info) => {
          if (attemptId !== activeAttempt) return
          if (info.willRetry) {
            connectionStore.setConnectionState('reconnecting')
            connectionStore.transitionTo('reconnecting')
            return
          }

          isStreaming.value = false
          connectionStore.stopStaleDetection()

          if (info.reason === 'completed' || info.reason === 'no_events_after_message') {
            connectionStore.setConnectionState('connected')
            connectionStore.transitionTo('settled')
            return
          }

          if (info.reason === 'aborted') {
            connectionStore.setConnectionState('disconnected')
            connectionStore.transitionTo('stopped')
            return
          }

          connectionStore.setConnectionState('failed')
          connectionStore.transitionTo('timed_out')
        },
        onError: (error) => {
          if (attemptId !== activeAttempt) return
          lastError.value = error.message
          isStreaming.value = false
          connectionStore.stopStaleDetection()
          connectionStore.setConnectionState('failed')
          connectionStore.setLastError({
            message: error.message,
            type: 'browser_workflow',
            recoverable: true,
            hint: null,
          })
          connectionStore.transitionTo('error')
        },
      },
    )

    return cancelStream
  }

  function stopStreaming(options: { preservePhase?: boolean } = {}) {
    if (cancelStream) {
      const cancel = cancelStream
      cancelStream = null
      cancel()
    }

    isStreaming.value = false
    connectionStore.stopStaleDetection()
    connectionStore.setConnectionState('disconnected')

    if (!options.preservePhase) {
      connectionStore.transitionTo('stopped')
    }
  }

  function clearEvents() {
    events.value = []
    lastError.value = null
    connectionStore.clearLastError()
  }

  return {
    events,
    isStreaming,
    lastError,
    lastProgress,
    hasError,
    fetchStream,
    stopStreaming,
    clearEvents,
  }
}
