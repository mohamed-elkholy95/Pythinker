import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { SSECloseInfo } from '@/api/client'
import type { AgentSSEEvent } from '@/types/event'

import { useSessionStreamController } from '../useSessionStreamController'

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

const createController = (options?: { responsePhase?: 'connecting' | 'streaming'; receivedDoneEvent?: boolean }) => {
  const transitionTo = vi.fn()
  const startStaleDetection = vi.fn()
  const stopStaleDetection = vi.fn()
  const cleanupStreamingState = vi.fn()
  const dismissRetryBanner = vi.fn()
  const setRetryBannerState = vi.fn()
  const setLastErrorFromTransportError = vi.fn()
  const handleStreamGapDetected = vi.fn()
  const log = vi.fn()

  const controller = useSessionStreamController({
    responsePhase: ref(options?.responsePhase ?? 'streaming'),
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
  }
}

describe('useSessionStreamController', () => {
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
})
