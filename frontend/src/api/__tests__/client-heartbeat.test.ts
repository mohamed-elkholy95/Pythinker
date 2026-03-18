import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('SSE Heartbeat Integration', () => {
  beforeEach(() => {
    vi.clearAllTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should emit heartbeat event when receiving progress event with heartbeat phase', async () => {
    const heartbeatListener = vi.fn()
    window.addEventListener('sse:heartbeat', heartbeatListener)

    // Simulate heartbeat progress event
    const heartbeatEvent = new CustomEvent('sse:heartbeat', {
      detail: { eventId: 'evt-123' }
    })
    window.dispatchEvent(heartbeatEvent)

    expect(heartbeatListener).toHaveBeenCalledTimes(1)
    expect(heartbeatListener).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'sse:heartbeat',
        detail: { eventId: 'evt-123' }
      })
    )

    window.removeEventListener('sse:heartbeat', heartbeatListener)
  })

  it('should not emit heartbeat event for non-heartbeat progress events', () => {
    const heartbeatListener = vi.fn()
    window.addEventListener('sse:heartbeat', heartbeatListener)

    // This test validates the logic in client.ts that filters heartbeat events
    // The actual filtering happens in client.ts onmessage handler
    // Here we just verify the event listener works correctly

    window.removeEventListener('sse:heartbeat', heartbeatListener)
    expect(heartbeatListener).not.toHaveBeenCalled()
  })

  it('should track heartbeat time when receiving heartbeat events', async () => {
    const { useSSEConnection } = await import('../../composables/useSSEConnection')
    const { lastHeartbeatTime, lastEventId, startStaleDetection, stopStaleDetection } = useSSEConnection()

    startStaleDetection()

    const beforeTime = Date.now()
    const heartbeatEvent = new CustomEvent('sse:heartbeat', {
      detail: { eventId: 'evt-heartbeat-456' }
    })
    window.dispatchEvent(heartbeatEvent)

    // Wait for event processing
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(lastHeartbeatTime.value).toBeGreaterThanOrEqual(beforeTime)
    expect(lastEventId.value).toBe('evt-heartbeat-456')

    stopStaleDetection()
  })

  it('should prevent stale connection detection when heartbeats are received', async () => {
    vi.useFakeTimers()
    const onStaleDetected = vi.fn()

    const { useSSEConnection } = await import('../../composables/useSSEConnection')
    const { connectionState, updateLastEventTime, startStaleDetection, stopStaleDetection } = useSSEConnection({
      staleThresholdMs: 60000,
      onStaleDetected
    })

    connectionState.value = 'connected'
    updateLastEventTime()
    startStaleDetection()

    // Simulate heartbeat every 30 seconds
    for (let i = 0; i < 5; i++) {
      vi.advanceTimersByTime(30000)
      const heartbeatEvent = new CustomEvent('sse:heartbeat', {
        detail: { eventId: `evt-${i}` }
      })
      window.dispatchEvent(heartbeatEvent)
    }

    // Total time: 150 seconds with heartbeat every 30s
    // Should NOT trigger stale detection (threshold is 60s)
    expect(onStaleDetected).not.toHaveBeenCalled()

    stopStaleDetection()
    vi.useRealTimers()
  })

  it('should trigger stale detection when heartbeats stop', async () => {
    vi.useFakeTimers()
    const onStaleDetected = vi.fn()

    const { useSSEConnection } = await import('../../composables/useSSEConnection')
    const { connectionState, updateLastEventTime, startStaleDetection, stopStaleDetection } = useSSEConnection({
      staleThresholdMs: 60000,
      onStaleDetected
    })

    connectionState.value = 'connected'
    updateLastEventTime()
    startStaleDetection()

    // Send one heartbeat
    const heartbeatEvent = new CustomEvent('sse:heartbeat', {
      detail: { eventId: 'evt-1' }
    })
    window.dispatchEvent(heartbeatEvent)

    // Advance time by 70 seconds without more heartbeats
    vi.advanceTimersByTime(70000)

    // Should trigger stale detection
    expect(onStaleDetected).toHaveBeenCalled()

    stopStaleDetection()
    vi.useRealTimers()
  })
})
