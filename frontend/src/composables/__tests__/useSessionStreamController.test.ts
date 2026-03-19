import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

import type { SSECloseInfo } from '@/api/client'
import type { AgentSSEEvent } from '@/types/event'

import { useSessionStreamController } from '../useSessionStreamController'
import type { ResponsePhase } from '@/stores/connectionStore'

const baseCloseInfo = (): SSECloseInfo => ({
  willRetry: false,
  retryAttempt: null,
  maxRetries: 7,
  streamCompleted: false,
  messageSent: true,
  receivedAnyEvents: true,
  reason: 'closed',
})

const buildDoneEvent = (eventId: string): AgentSSEEvent => ({
  event: 'done',
  data: {
    event_id: eventId,
    timestamp: Date.now(),
  },
})

const createController = (options?: { responsePhase?: ResponsePhase; receivedDoneEvent?: boolean }) => {
  const transitionTo = vi.fn()
  const startStaleDetection = vi.fn()
  const stopStaleDetection = vi.fn()
  const cleanupStreamingState = vi.fn()
  const dismissRetryBanner = vi.fn()
  const setRetryBannerState = vi.fn()
  const setLastErrorFromTransportError = vi.fn()
  const handleStreamGapDetected = vi.fn()
  const log = vi.fn()
  const responsePhase = ref<ResponsePhase>(options?.responsePhase ?? 'streaming')

  const controller = useSessionStreamController({
    responsePhase,
    receivedDoneEvent: ref(options?.receivedDoneEvent ?? false),
    seenEventIds: ref(new Map<string, number>()),
    transitionTo,
    startStaleDetection,
    stopStaleDetection,
    cleanupStreamingState,
    dismissRetryBanner,
    setRetryBannerState,
    setLastErrorFromTransportError,
    handleStreamGapDetected,
    log,
  })

  return {
    controller,
    transitionTo,
    startStaleDetection,
    stopStaleDetection,
    cleanupStreamingState,
    dismissRetryBanner,
    setRetryBannerState,
    setLastErrorFromTransportError,
    handleStreamGapDetected,
    log,
    responsePhase,
  }
}

describe('useSessionStreamController', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('tracks and detects duplicate event ids', () => {
    const { controller } = createController({
      responsePhase: 'connecting',
    })

    expect(controller.isDuplicateEvent('evt-1')).toBe(false)
    controller.trackSeenEventId('evt-1')
    expect(controller.isDuplicateEvent('evt-1')).toBe(true)
  })

  it('queues and flushes pending events in order', () => {
    const { controller, log } = createController()
    const processEvent = vi.fn()
    controller.setEventProcessor(processEvent)

    const firstEvent = buildDoneEvent('evt-1')
    const secondEvent = buildDoneEvent('evt-2')

    controller.enqueueEvent(firstEvent)
    controller.enqueueEvent(secondEvent)

    expect(controller.getPendingEventCount()).toBe(2)

    controller.flushPendingEvents()

    expect(processEvent).toHaveBeenNthCalledWith(1, firstEvent)
    expect(processEvent).toHaveBeenNthCalledWith(2, secondEvent)
    expect(controller.getPendingEventCount()).toBe(0)
    expect(log).toHaveBeenCalledWith('batch:flush', { eventCount: 2 })
  })

  it('transitions to reconnecting and sets retry banner on retry close', () => {
    const {
      controller,
      transitionTo,
      stopStaleDetection,
      cleanupStreamingState,
      setRetryBannerState,
    } = createController({
      responsePhase: 'streaming',
    })
    const processEvent = vi.fn()
    controller.setEventProcessor(processEvent)

    const callbacks = controller.createTransportCallbacks('transport')
    callbacks.onMessage?.({
      event: 'done',
      data: buildDoneEvent('evt-1').data,
    })
    expect(controller.getPendingEventCount()).toBe(1)

    callbacks.onClose?.({
      ...baseCloseInfo(),
      willRetry: true,
      retryAttempt: 1,
      retryDelayMs: 500,
      reason: 'retrying',
    })

    expect(stopStaleDetection).toHaveBeenCalled()
    expect(processEvent).toHaveBeenCalledTimes(1)
    expect(controller.getPendingEventCount()).toBe(0)
    expect(setRetryBannerState).toHaveBeenCalledWith({ retryAttempt: 1, maxRetries: 7, retryDelayMs: 500 })
    expect(transitionTo).toHaveBeenCalledWith('reconnecting')
    expect(cleanupStreamingState).not.toHaveBeenCalled()
  })

  it('dismisses retry banner for retry closes when already in terminal phase', () => {
    const {
      controller,
      responsePhase,
      transitionTo,
      dismissRetryBanner,
      setRetryBannerState,
    } = createController({
      responsePhase: 'streaming',
    })

    responsePhase.value = 'settled'
    const callbacks = controller.createTransportCallbacks('transport')
    callbacks.onClose?.({
      ...baseCloseInfo(),
      willRetry: true,
      retryAttempt: 1,
      retryDelayMs: 500,
      reason: 'retrying',
    })

    expect(dismissRetryBanner).toHaveBeenCalled()
    expect(setRetryBannerState).not.toHaveBeenCalled()
    expect(transitionTo).not.toHaveBeenCalledWith('reconnecting')
  })

  it('transitions to timed_out when stream closes without done', () => {
    const { controller, transitionTo, dismissRetryBanner, cleanupStreamingState } = createController({
      responsePhase: 'streaming',
      receivedDoneEvent: false,
    })

    const callbacks = controller.createTransportCallbacks('transport_retry')
    callbacks.onClose?.({
      ...baseCloseInfo(),
      reason: 'closed',
    })

    expect(dismissRetryBanner).toHaveBeenCalled()
    expect(transitionTo).toHaveBeenCalledWith('timed_out')
    expect(cleanupStreamingState).toHaveBeenCalled()
  })

  it('settles without timeout when no-input resume closes with no events', () => {
    const { controller, transitionTo, cleanupStreamingState } = createController({
      responsePhase: 'connecting',
      receivedDoneEvent: false,
    })

    const callbacks = controller.createTransportCallbacks('transport_retry')
    callbacks.onClose?.({
      ...baseCloseInfo(),
      messageSent: false,
      receivedAnyEvents: true,
      reason: 'no_events_after_message',
    })

    expect(transitionTo).toHaveBeenCalledWith('settled')
    expect(transitionTo).not.toHaveBeenCalledWith('timed_out')
    expect(cleanupStreamingState).toHaveBeenCalled()
  })

  it('settles without timeout when message stream closes with no meaningful events', () => {
    const { controller, transitionTo, cleanupStreamingState } = createController({
      responsePhase: 'connecting',
      receivedDoneEvent: false,
    })

    const callbacks = controller.createTransportCallbacks('transport_retry')
    callbacks.onClose?.({
      ...baseCloseInfo(),
      messageSent: true,
      receivedAnyEvents: true,
      reason: 'no_events_after_message',
    })

    expect(transitionTo).toHaveBeenCalledWith('settled')
    expect(transitionTo).not.toHaveBeenCalledWith('timed_out')
    expect(cleanupStreamingState).toHaveBeenCalled()
  })

  it('schedules auto retry when phase becomes timed_out', async () => {
    vi.useFakeTimers()
    const { controller, responsePhase } = createController({
      responsePhase: 'streaming',
    })
    const autoRetryCount = ref(0)
    const isFallbackStatusPolling = ref(false)
    const onRetryConnection = vi.fn().mockResolvedValue(undefined)
    const pollFallbackStatus = vi.fn().mockResolvedValue('continue')

    controller.setupReconnectCoordinator({
      autoRetryCount,
      isFallbackStatusPolling,
      onRetryConnection,
      pollFallbackStatus,
      autoRetryDelaysMs: [25],
      fallbackPollInitialIntervalMs: 25,
      fallbackPollMaxAttempts: 2,
      maxAutoRetries: 4,
    })

    responsePhase.value = 'timed_out'
    await nextTick()
    await vi.advanceTimersByTimeAsync(25)

    expect(autoRetryCount.value).toBe(1)
    expect(onRetryConnection).toHaveBeenCalledTimes(1)
    expect(isFallbackStatusPolling.value).toBe(false)
  })

  it('starts fallback polling after max retries and stops when poll returns stop', async () => {
    vi.useFakeTimers()
    const { controller, responsePhase } = createController({
      responsePhase: 'streaming',
    })
    const autoRetryCount = ref(4)
    const isFallbackStatusPolling = ref(false)
    const onRetryConnection = vi.fn().mockResolvedValue(undefined)
    const pollFallbackStatus = vi.fn()
      .mockResolvedValueOnce('continue')
      .mockResolvedValueOnce('stop')

    controller.setupReconnectCoordinator({
      autoRetryCount,
      isFallbackStatusPolling,
      onRetryConnection,
      pollFallbackStatus,
      autoRetryDelaysMs: [25],
      fallbackPollInitialIntervalMs: 25,
      fallbackPollMaxAttempts: 4,
      maxAutoRetries: 4,
    })

    responsePhase.value = 'timed_out'
    await nextTick()
    await Promise.resolve()
    expect(isFallbackStatusPolling.value).toBe(true)
    expect(pollFallbackStatus).toHaveBeenCalledTimes(1)
    expect(onRetryConnection).not.toHaveBeenCalled()

    // Exponential backoff with ±20% jitter: first interval is 25 * 2^0 * [0.8..1.2] = 20..30ms
    // Advance well past the max jittered interval to guarantee the timer fires
    await vi.advanceTimersByTimeAsync(60)
    await Promise.resolve()
    expect(pollFallbackStatus).toHaveBeenCalledTimes(2)
    expect(isFallbackStatusPolling.value).toBe(false)
  })
})
