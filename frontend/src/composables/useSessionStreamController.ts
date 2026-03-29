import { getCurrentInstance, onUnmounted, watch, type Ref } from 'vue'

import type { SSECallbacks, SSECloseInfo, SSEGapInfo } from '@/api/client'
import {
  resolveSessionReconnectPolicy,
  type SessionReconnectPolicy,
} from '@/core/session/reconnectPolicy'
import {
  createSessionReliabilityAccumulator,
  incrementSessionReliabilityCounter,
  recordSessionChunkProcessingDuration,
  recordSessionFlushBatchSize,
  recordSessionQueueDepth,
  snapshotSessionReliability,
} from '@/core/session/sessionReliability'
import type { AgentSSEEvent } from '@/types/event'

import type { ResponsePhase } from '@/stores/connectionStore'

export type TransportScope = 'transport' | 'transport_retry'

type EventProcessor = (event: AgentSSEEvent) => void

type FrameHandle = number | ReturnType<typeof setTimeout>

interface RetryBannerState {
  retryAttempt?: number
  maxRetries?: number
  retryDelayMs?: number
}

type FallbackPollOutcome = 'continue' | 'stop'

interface ReconnectCoordinatorOptions {
  autoRetryCount: Ref<number>
  isFallbackStatusPolling: Ref<boolean>
  onRetryConnection: () => void | Promise<void>
  pollFallbackStatus: () => Promise<FallbackPollOutcome>
  maxAutoRetries?: number
  autoRetryDelaysMs?: number[]
  fallbackPollInitialIntervalMs?: number
  fallbackPollMaxIntervalMs?: number
  fallbackPollMaxAttempts?: number
}

type ResolvedReconnectCoordinatorOptions =
  Omit<ReconnectCoordinatorOptions, keyof SessionReconnectPolicy> & SessionReconnectPolicy

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
const YIELD_BATCH_SIZE = 50

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

/**
 * Calculate exponential backoff interval with ±20% jitter.
 * Starts at `initialMs`, doubles each attempt, caps at `maxMs`.
 */
const calcBackoffWithJitter = (attempt: number, initialMs: number, maxMs: number): number => {
  const exponential = Math.min(initialMs * Math.pow(2, attempt), maxMs)
  // ±20% jitter to prevent thundering herd
  const jitterFactor = 0.8 + Math.random() * 0.4
  return Math.round(exponential * jitterFactor)
}

const getNowMs = (): number => {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
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
  let chunkTimeoutHandle: ReturnType<typeof setTimeout> | null = null
  let reconnectCoordinatorOptions: ResolvedReconnectCoordinatorOptions | null = null
  let autoRetryTimer: ReturnType<typeof setTimeout> | null = null
  let fallbackStatusPollTimer: ReturnType<typeof setTimeout> | null = null
  let fallbackStatusPollAttempts = 0
  let stopReconnectWatcher: (() => void) | null = null
  let reliabilityAccumulator = createSessionReliabilityAccumulator()

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
    if (chunkTimeoutHandle !== null) {
      clearTimeout(chunkTimeoutHandle)
      chunkTimeoutHandle = null
    }

    if (eventBatchQueue.length === 0) {
      return
    }

    const eventsToProcess = eventBatchQueue
    eventBatchQueue = []
    recordSessionFlushBatchSize(reliabilityAccumulator, eventsToProcess.length)

    log('batch:flush', {
      eventCount: eventsToProcess.length,
    })

    if (!eventProcessor) {
      return
    }

    // Yield to the browser between chunks to prevent main-thread jank
    // when a large burst of SSE events arrives at once
    if (eventsToProcess.length <= YIELD_BATCH_SIZE) {
      const chunkStartedAt = getNowMs()
      for (const event of eventsToProcess) {
        eventProcessor(event)
      }
      recordSessionChunkProcessingDuration(reliabilityAccumulator, getNowMs() - chunkStartedAt)
      return
    }

    let offset = 0
    const processChunk = () => {
      chunkTimeoutHandle = null
      const end = Math.min(offset + YIELD_BATCH_SIZE, eventsToProcess.length)
      const chunkStartedAt = getNowMs()
      for (let i = offset; i < end; i += 1) {
        eventProcessor!(eventsToProcess[i])
      }
      recordSessionChunkProcessingDuration(reliabilityAccumulator, getNowMs() - chunkStartedAt)
      offset = end
      if (offset < eventsToProcess.length) {
        chunkTimeoutHandle = setTimeout(processChunk, 0)
      }
    }
    processChunk()
  }

  const clearPendingEvents = (): void => {
    if (batchFrameHandle !== null) {
      cancelFrame(batchFrameHandle)
      batchFrameHandle = null
    }
    if (chunkTimeoutHandle !== null) {
      clearTimeout(chunkTimeoutHandle)
      chunkTimeoutHandle = null
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
    recordSessionQueueDepth(reliabilityAccumulator, eventBatchQueue.length)

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
    const terminalPhase = isTerminalPhase()

    if (closeInfo.willRetry && !terminalPhase) {
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
      if (!terminalPhase) {
        transitionTo('reconnecting')
      }
      return
    }

    const shouldSilentlySettleNoEvents = closeInfo.reason === 'no_events_after_message'
      && !terminalPhase

    if (shouldSilentlySettleNoEvents) {
      transitionTo('settled')
      cleanupStreamingState()
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

  const clearAutoRetryTimer = (): void => {
    if (autoRetryTimer !== null) {
      clearTimeout(autoRetryTimer)
      autoRetryTimer = null
    }
  }

  const clearFallbackStatusPolling = (): void => {
    if (fallbackStatusPollTimer !== null) {
      clearTimeout(fallbackStatusPollTimer)
      fallbackStatusPollTimer = null
    }
    fallbackStatusPollAttempts = 0
    if (reconnectCoordinatorOptions) {
      reconnectCoordinatorOptions.isFallbackStatusPolling.value = false
    }
  }

  const clearReconnectCoordinator = (): void => {
    clearAutoRetryTimer()
    clearFallbackStatusPolling()
  }

  const runFallbackStatusPoll = async (): Promise<void> => {
    if (!reconnectCoordinatorOptions) {
      return
    }

    if (responsePhase.value !== 'timed_out') {
      clearFallbackStatusPolling()
      return
    }

    fallbackStatusPollAttempts += 1
    incrementSessionReliabilityCounter(reliabilityAccumulator, 'fallbackPollAttempts')

    let outcome: FallbackPollOutcome = 'continue'
    try {
      outcome = await reconnectCoordinatorOptions.pollFallbackStatus()
    } catch (error) {
      log('fallback:poll_error', {
        message: error instanceof Error ? error.message : String(error),
        attempt: fallbackStatusPollAttempts,
      })
    }

    if (outcome === 'stop') {
      clearFallbackStatusPolling()
      return
    }

    const maxAttempts = reconnectCoordinatorOptions.fallbackPollMaxAttempts
    if (fallbackStatusPollAttempts >= maxAttempts) {
      reconnectCoordinatorOptions.isFallbackStatusPolling.value = false
      return
    }

    const initialMs = reconnectCoordinatorOptions.fallbackPollInitialIntervalMs
    const maxMs = reconnectCoordinatorOptions.fallbackPollMaxIntervalMs
    // attempt index is 0-based: first poll already happened, so use (attempts - 1)
    const intervalMs = calcBackoffWithJitter(fallbackStatusPollAttempts - 1, initialMs, maxMs)

    log('fallback:poll_scheduled', {
      attempt: fallbackStatusPollAttempts,
      nextIntervalMs: intervalMs,
    })

    fallbackStatusPollTimer = setTimeout(() => {
      fallbackStatusPollTimer = null
      void runFallbackStatusPoll()
    }, intervalMs)
  }

  const startFallbackStatusPolling = (): void => {
    if (!reconnectCoordinatorOptions) {
      return
    }

    if (reconnectCoordinatorOptions.isFallbackStatusPolling.value || fallbackStatusPollTimer !== null) {
      return
    }

    reconnectCoordinatorOptions.isFallbackStatusPolling.value = true
    fallbackStatusPollAttempts = 0
    void runFallbackStatusPoll()
  }

  const scheduleAutoRetry = (): void => {
    if (!reconnectCoordinatorOptions) {
      return
    }

    if (autoRetryTimer !== null) {
      return
    }

    const retryIndex = Math.min(
      reconnectCoordinatorOptions.autoRetryCount.value,
      reconnectCoordinatorOptions.autoRetryDelaysMs.length - 1,
    )
    const delayMs = reconnectCoordinatorOptions.autoRetryDelaysMs[retryIndex]

    log('retry:auto_scheduled', {
      retryCount: reconnectCoordinatorOptions.autoRetryCount.value,
      delayMs,
    })

    autoRetryTimer = setTimeout(() => {
      autoRetryTimer = null
      if (!reconnectCoordinatorOptions) {
        return
      }

      // Guard: phase may have left timed_out while the timer was pending
      if (responsePhase.value !== 'timed_out') {
        return
      }

      reconnectCoordinatorOptions.autoRetryCount.value += 1
      incrementSessionReliabilityCounter(reliabilityAccumulator, 'autoRetryCount')
      void Promise.resolve(reconnectCoordinatorOptions.onRetryConnection()).catch((error) => {
        log('retry:auto_failed', {
          message: error instanceof Error ? error.message : String(error),
        })
      })
    }, delayMs)
  }

  const handlePhaseTransition = (phase: ResponsePhase): void => {
    if (!reconnectCoordinatorOptions) {
      return
    }

    if (phase !== 'timed_out') {
      clearReconnectCoordinator()
      return
    }

    log('phase:timed_out', {
      autoRetryCount: reconnectCoordinatorOptions.autoRetryCount.value,
    })

    if (reconnectCoordinatorOptions.autoRetryCount.value < reconnectCoordinatorOptions.maxAutoRetries) {
      scheduleAutoRetry()
      return
    }

    startFallbackStatusPolling()
  }

  const setupReconnectCoordinator = (setupOptions: ReconnectCoordinatorOptions): void => {
    const reconnectPolicy = resolveSessionReconnectPolicy(setupOptions)
    reconnectCoordinatorOptions = {
      ...setupOptions,
      ...reconnectPolicy,
    }

    if (stopReconnectWatcher) {
      stopReconnectWatcher()
    }

    stopReconnectWatcher = watch(responsePhase, (phase) => {
      handlePhaseTransition(phase)
    })
  }

  const disposeReconnectCoordinator = (): void => {
    clearReconnectCoordinator()

    if (stopReconnectWatcher) {
      stopReconnectWatcher()
      stopReconnectWatcher = null
    }

    reconnectCoordinatorOptions = null
  }

  const getReliabilitySummary = () => {
    return snapshotSessionReliability(reliabilityAccumulator)
  }

  const resetReliabilitySummary = (): void => {
    reliabilityAccumulator = createSessionReliabilityAccumulator()
  }

  const recordDuplicateEventDrop = (): void => {
    incrementSessionReliabilityCounter(reliabilityAccumulator, 'duplicateEventDrops')
  }

  const recordStaleDetection = (): void => {
    incrementSessionReliabilityCounter(reliabilityAccumulator, 'staleDetectionCount')
  }

  if (getCurrentInstance()) {
    onUnmounted(() => {
      disposeReconnectCoordinator()
    })
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
    setupReconnectCoordinator,
    clearReconnectCoordinator,
    disposeReconnectCoordinator,
    enqueueEvent,
    isDuplicateEvent,
    trackSeenEventId,
    getReliabilitySummary,
    resetReliabilitySummary,
    recordDuplicateEventDrop,
    recordStaleDetection,
    createTransportCallbacks,
  }
}
