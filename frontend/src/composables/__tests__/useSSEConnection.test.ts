import { describe, it, expect, vi } from 'vitest'

describe('useSSEConnection', () => {
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
