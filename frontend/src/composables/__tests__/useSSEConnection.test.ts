import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('useSSEConnection', () => {
  beforeEach(() => {
    vi.clearAllTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should track connection state', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { connectionState } = useSSEConnection()
    expect(connectionState.value).toBe('disconnected')
  })

  it('should track last event time', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { lastEventTime, updateLastEventTime } = useSSEConnection()

    expect(lastEventTime.value).toBe(0)
    updateLastEventTime()
    expect(lastEventTime.value).toBeGreaterThan(0)
  })

  it('should track last heartbeat time', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { lastHeartbeatTime, lastEventTime, updateLastHeartbeatTime } = useSSEConnection()

    expect(lastHeartbeatTime.value).toBe(0)
    updateLastHeartbeatTime()
    expect(lastHeartbeatTime.value).toBeGreaterThan(0)
    // Heartbeat should also update general event time
    expect(lastEventTime.value).toBeGreaterThan(0)
  })

  it('should detect stale connections', async () => {
    vi.useFakeTimers()
    const { useSSEConnection } = await import('../useSSEConnection')
    const { updateLastEventTime, isConnectionStale } = useSSEConnection()

    updateLastEventTime()
    expect(isConnectionStale(30000)).toBe(false)

    vi.advanceTimersByTime(31000)
    expect(isConnectionStale(30000)).toBe(true)

    vi.useRealTimers()
  })

  it('should detect stale heartbeat', async () => {
    vi.useFakeTimers()
    const { useSSEConnection } = await import('../useSSEConnection')
    const { updateLastHeartbeatTime, isHeartbeatStale } = useSSEConnection()

    updateLastHeartbeatTime()
    expect(isHeartbeatStale(30000)).toBe(false)

    vi.advanceTimersByTime(31000)
    expect(isHeartbeatStale(30000)).toBe(true)

    vi.useRealTimers()
  })

  it('should call onStaleDetected when connection becomes stale', async () => {
    vi.useFakeTimers()
    const onStaleDetected = vi.fn()
    const { useSSEConnection } = await import('../useSSEConnection')
    const { updateLastEventTime, connectionState, startStaleDetection } = useSSEConnection({
      staleThresholdMs: 60000,
      onStaleDetected
    })

    // Simulate connection
    connectionState.value = 'connected'
    updateLastEventTime()
    startStaleDetection()

    // Advance time past stale threshold
    vi.advanceTimersByTime(70000)

    expect(onStaleDetected).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('should not detect stale before receiving any events', async () => {
    vi.useFakeTimers()
    const onStaleDetected = vi.fn()
    const { useSSEConnection } = await import('../useSSEConnection')
    const { connectionState, startStaleDetection } = useSSEConnection({
      staleThresholdMs: 60000,
      onStaleDetected
    })

    connectionState.value = 'connected'
    startStaleDetection()

    // Advance time without any events
    vi.advanceTimersByTime(70000)

    // Should not trigger stale detection (lastEventTime is 0)
    expect(onStaleDetected).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('should handle heartbeat custom events', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { lastHeartbeatTime, lastEventId, startStaleDetection, stopStaleDetection } = useSSEConnection()

    // Start stale detection to set up the event listener
    startStaleDetection()

    // Simulate heartbeat event
    const heartbeatEvent = new CustomEvent('sse:heartbeat', {
      detail: { eventId: 'heartbeat-123' }
    })

    const beforeTime = Date.now()
    window.dispatchEvent(heartbeatEvent)

    // Wait for event to be processed
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(lastHeartbeatTime.value).toBeGreaterThanOrEqual(beforeTime)
    expect(lastEventId.value).toBe('heartbeat-123')

    // Clean up
    stopStaleDetection()
  })

  it('should stop stale detection on cleanup', async () => {
    vi.useFakeTimers()
    const onStaleDetected = vi.fn()
    const { useSSEConnection } = await import('../useSSEConnection')
    const { updateLastEventTime, connectionState, startStaleDetection, stopStaleDetection } = useSSEConnection({
      staleThresholdMs: 60000,
      onStaleDetected
    })

    connectionState.value = 'connected'
    updateLastEventTime()
    startStaleDetection()

    // Stop detection before threshold
    vi.advanceTimersByTime(30000)
    stopStaleDetection()

    // Advance past threshold - should not trigger
    vi.advanceTimersByTime(40000)
    expect(onStaleDetected).not.toHaveBeenCalled()

    vi.useRealTimers()
  })

  it('should persist and restore lastEventId', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { lastEventId, persistEventId, getPersistedEventId } = useSSEConnection()

    const sessionId = 'test-session-123'
    lastEventId.value = 'event-456'
    persistEventId(sessionId)

    const restored = getPersistedEventId(sessionId)
    expect(restored).toBe('event-456')
  })
})
