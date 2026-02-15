import type { Ref } from 'vue'

import type { SSECallbacks, SSECloseInfo, SSEGapInfo } from '@/api/client'
import type { AgentSSEEvent } from '@/types/event'

import type { ResponsePhase } from './useResponsePhase'

export type TransportScope = 'transport' | 'transport_retry'

type EventProcessor = (event: AgentSSEEvent) => void

type FrameHandle = number | ReturnType<typeof setTimeout>

interface RetryBannerState {
  retryAttempt?: number
  maxRetries?: number
  retryDelayMs?: number
}

interface UseSessionStreamControllerOptions {
  responsePhase: Ref<ResponsePhase>
  receivedDoneEvent: Ref<boolean>
  seenEventIds: Ref<Map<string, number>>
  transitionTo: (phase: ResponsePhase) => void
  startStaleDetection: () => void
  stopStaleDetection: () => void
  cleanupStreamingState: () => void
  dismissRetryBanner: () => void
  setRetryBannerState: (state: RetryBannerState) => void
  setLastErrorFromTransportError: (error: Error) => void
  handleStreamGapDetected: (scope: TransportScope, info: SSEGapInfo) => void
  log: (message: string, details?: Record<string, unknown>) => void
}

const MAX_SEEN_EVENT_IDS = 1000

const hasBrowserRaf = (): boolean => {
  return typeof requestAnimationFrame === 'function' && typeof cancelAnimationFrame === 'function'
}

const scheduleFrame = (callback: () => void): FrameHandle => {
  if (hasBrowserRaf()) {
    return requestAnimationFrame(() => callback())
  }
  return setTimeout(callback, 16)
}

const cancelFrame = (handle: FrameHandle): void => {
  if (hasBrowserRaf() && typeof handle === 'number') {
    cancelAnimationFrame(handle)
    return
  }
  clearTimeout(handle as ReturnType<typeof setTimeout>)
}

export function useSessionStreamController(options: UseSessionStreamControllerOptions) {
  const {
    responsePhase,
    receivedDoneEvent,
    seenEventIds,
    transitionTo,
    startStaleDetection,
    stopStaleDetection,
    cleanupStreamingState,
    dismissRetryBanner,
    setRetryBannerState,
    setLastErrorFromTransportError,
    handleStreamGapDetected,
    log,
  } = options

  let eventProcessor: EventProcessor | null = null
  let eventBatchQueue: AgentSSEEvent[] = []
  let batchFrameHandle: FrameHandle | null = null

  const isTerminalPhase = (): boolean => {
    return responsePhase.value === 'settled' || responsePhase.value === 'error' || responsePhase.value === 'stopped'
  }

  const setEventProcessor = (processor: EventProcessor): void => {
    eventProcessor = processor
  }

  const getPendingEventCount = (): number => {
    return eventBatchQueue.length
  }

  const flushPendingEvents = (): void => {
    if (batchFrameHandle !== null) {
      cancelFrame(batchFrameHandle)
      batchFrameHandle = null
    }

    if (eventBatchQueue.length === 0) {
      return
    }

    const eventsToProcess = eventBatchQueue
    eventBatchQueue = []

    log('batch:flush', {
      eventCount: eventsToProcess.length,
    })

    if (!eventProcessor) {
      return
    }

    for (const event of eventsToProcess) {
      eventProcessor(event)
    }
  }

  const clearPendingEvents = (): void => {
    if (batchFrameHandle !== null) {
      cancelFrame(batchFrameHandle)
      batchFrameHandle = null
    }
    eventBatchQueue = []
  }

  const enqueueEvent = (event: AgentSSEEvent): void => {
    log('batch:queue', {
      event: event.event,
      eventId: event.data?.event_id ?? null,
      queueSize: eventBatchQueue.length + 1,
      frameScheduled: batchFrameHandle !== null,
    })

    eventBatchQueue.push(event)

    if (batchFrameHandle === null) {
      batchFrameHandle = scheduleFrame(() => {
        batchFrameHandle = null
        flushPendingEvents()
      })
    }
  }

  const trackSeenEventId = (eventId: string | undefined): void => {
    if (!eventId) {
      return
    }

    // Refresh recency for known ids.
    if (seenEventIds.value.has(eventId)) {
      seenEventIds.value.delete(eventId)
    }

    seenEventIds.value.set(eventId, Date.now())

    if (seenEventIds.value.size > MAX_SEEN_EVENT_IDS) {
      const oldestKey = seenEventIds.value.keys().next().value
      if (oldestKey !== undefined) {
        seenEventIds.value.delete(oldestKey)
      }
    }
  }

  const isDuplicateEvent = (eventId: string | undefined): boolean => {
    if (!eventId) {
      return false
    }
    return seenEventIds.value.has(eventId)
  }

  const handleTransportClose = (scope: TransportScope, closeInfo: SSECloseInfo): void => {
    stopStaleDetection()
    flushPendingEvents()

    if (closeInfo.willRetry) {
      setRetryBannerState({
        retryAttempt: closeInfo.retryAttempt ?? undefined,
        maxRetries: closeInfo.maxRetries,
        retryDelayMs: closeInfo.retryDelayMs ?? undefined,
      })
    } else {
      dismissRetryBanner()
    }

    log(`${scope}:onClose`, {
      reason: closeInfo.reason,
      willRetry: closeInfo.willRetry,
      retryAttempt: closeInfo.retryAttempt,
      maxRetries: closeInfo.maxRetries,
      streamCompleted: closeInfo.streamCompleted,
      receivedAnyEvents: closeInfo.receivedAnyEvents,
    })

    if (closeInfo.willRetry) {
      if (!isTerminalPhase()) {
        transitionTo('reconnecting')
      }
      return
    }

    const shouldMarkTimedOut = !receivedDoneEvent.value
      && !isTerminalPhase()
      && closeInfo.reason !== 'completed'
      && closeInfo.reason !== 'aborted'

    if (shouldMarkTimedOut) {
      transitionTo('timed_out')
    }

    cleanupStreamingState()
  }

  const createTransportCallbacks = (
    scope: TransportScope,
  ): SSECallbacks<AgentSSEEvent['data']> => {
    return {
      onOpen: () => {
        log(`${scope}:onOpen`)
        dismissRetryBanner()
        startStaleDetection()
      },
      onMessage: ({ event, data }) => {
        const eventData = data as { event_id?: string; phase?: string }
        log(`${scope}:onMessage`, {
          event,
          eventId: eventData.event_id ?? null,
          phase: eventData.phase ?? null,
        })

        enqueueEvent({
          event: event as AgentSSEEvent['event'],
          data: data as AgentSSEEvent['data'],
        })
      },
      onClose: (closeInfo: SSECloseInfo) => {
        handleTransportClose(scope, closeInfo)
      },
      onError: (error: Error) => {
        log(`${scope}:onError`, {
          message: error.message,
        })

        stopStaleDetection()
        const isMaxRetriesError = error.message.toLowerCase().includes('max reconnection attempts reached')

        if (!isTerminalPhase()) {
          setLastErrorFromTransportError(error)
          transitionTo(isMaxRetriesError ? 'timed_out' : 'error')
        }

        cleanupStreamingState()
      },
      onRetry: (attempt: number, maxAttempts: number) => {
        log(`${scope}:onRetry`, {
          attempt,
          maxAttempts,
        })

        if (!isTerminalPhase()) {
          transitionTo('reconnecting')
        }
      },
      onGapDetected: (info: SSEGapInfo) => {
        handleStreamGapDetected(scope, info)
      },
    }
  }

  return {
    setEventProcessor,
    getPendingEventCount,
    flushPendingEvents,
    clearPendingEvents,
    enqueueEvent,
    isDuplicateEvent,
    trackSeenEventId,
    createTransportCallbacks,
  }
}
