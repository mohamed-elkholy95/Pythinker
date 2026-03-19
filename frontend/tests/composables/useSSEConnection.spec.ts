import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useSSEConnection } from '@/composables/useSSEConnection'

describe('useSSEConnection', () => {
  let connection: ReturnType<typeof useSSEConnection>

  beforeEach(() => {
    vi.useFakeTimers()
    connection = useSSEConnection()
    connection.reset()
  })

  afterEach(() => {
    connection.stopStaleDetection()
    vi.useRealTimers()
  })

  describe('initial state', () => {
    it('should start disconnected', () => {
      expect(connection.connectionState.value).toBe('disconnected')
      expect(connection.lastEventTime.value).toBe(0)
      expect(connection.lastRealEventTime.value).toBe(0)
    })
  })

  describe('event time tracking', () => {
    it('should update lastEventTime on updateLastEventTime', () => {
      connection.updateLastEventTime()
      expect(connection.lastEventTime.value).toBeGreaterThan(0)
    })

    it('should update lastRealEventTime on updateLastRealEventTime', () => {
      connection.updateLastRealEventTime()
      expect(connection.lastRealEventTime.value).toBeGreaterThan(0)
      expect(connection.lastEventTime.value).toBeGreaterThan(0)
      expect(connection.totalEvents.value).toBe(1)
    })

    it('should track total events count', () => {
      connection.updateLastRealEventTime()
      connection.updateLastRealEventTime()
      connection.updateLastRealEventTime()
      expect(connection.totalEvents.value).toBe(3)
    })
  })

  describe('heartbeat tracking', () => {
    it('should update heartbeat time separately', () => {
      connection.updateLastHeartbeatTime()
      expect(connection.lastHeartbeatTime.value).toBeGreaterThan(0)
      expect(connection.totalHeartbeats.value).toBe(1)
    })

    it('should count heartbeats separately from real events', () => {
      connection.updateLastRealEventTime()
      connection.updateLastHeartbeatTime()
      connection.updateLastHeartbeatTime()
      
      expect(connection.totalEvents.value).toBe(1)
      expect(connection.totalHeartbeats.value).toBe(2)
    })
  })

  describe('staleness detection', () => {
    it('should detect stale connection', () => {
      connection.updateLastEventTime()
      expect(connection.isConnectionStale(1000)).toBe(false)
      
      vi.advanceTimersByTime(2000)
      expect(connection.isConnectionStale(1000)).toBe(true)
    })

    it('should detect stale heartbeat', () => {
      connection.updateLastHeartbeatTime()
      expect(connection.isHeartbeatStale(1000)).toBe(false)
      
      vi.advanceTimersByTime(2000)
      expect(connection.isHeartbeatStale(1000)).toBe(true)
    })
  })

  describe('degraded state detection', () => {
    it('should detect heartbeat-only degraded state', () => {
      const now = Date.now()
      vi.setSystemTime(now)
      
      // Receive a real event
      connection.updateLastRealEventTime()
      
      // Then receive only heartbeats for a while
      vi.advanceTimersByTime(30000)
      connection.updateLastHeartbeatTime()
      
      vi.advanceTimersByTime(30000)
      connection.updateLastHeartbeatTime()
      
      // Should be degraded (heartbeats recent, real events stale)
      expect(connection.isReceivingOnlyHeartbeats(60000)).toBe(true)
    })

    it('should not be degraded if never received real events', () => {
      connection.updateLastHeartbeatTime()
      vi.advanceTimersByTime(60000)
      connection.updateLastHeartbeatTime()
      
      expect(connection.isReceivingOnlyHeartbeats(60000)).toBe(false)
    })
  })

  describe('event rate calculation', () => {
    it('should calculate events per second', () => {
      vi.setSystemTime(0)
      connection.startStaleDetection()
      
      // Simulate 10 events over 10 seconds
      for (let i = 0; i < 10; i++) {
        vi.advanceTimersByTime(1000)
        connection.updateLastRealEventTime()
      }
      
      expect(connection.eventRate.value).toBeCloseTo(1, 0)
    })
  })

  describe('health metrics', () => {
    it('should provide comprehensive health metrics', () => {
      connection.startStaleDetection()
      connection.updateLastRealEventTime()
      connection.updateLastHeartbeatTime()
      
      const metrics = connection.getHealthMetrics()
      
      expect(metrics.totalEvents).toBe(1)
      expect(metrics.totalHeartbeats).toBe(1)
      expect(metrics.timeSinceLastEvent).toBeLessThan(1000)
      expect(metrics.connectionDuration).toBeLessThan(1000)
    })
  })

  describe('stale detection lifecycle', () => {
    it('should start and stop stale detection', () => {
      connection.startStaleDetection()
      expect(connection.connectionStartTime.value).toBeGreaterThan(0)
      
      connection.stopStaleDetection()
      // Should not error
    })

    it('should detect degraded state and emit callback', () => {
      const onDegraded = vi.fn()
      const conn = useSSEConnection({
        degradedThresholdMs: 5000,
        onDegradedDetected: onDegraded,
      })
      
      conn.startStaleDetection()
      conn.updateLastRealEventTime()
      
      // Advance past degraded threshold with only heartbeats
      vi.advanceTimersByTime(3000)
      conn.updateLastHeartbeatTime()
      vi.advanceTimersByTime(3000)
      conn.updateLastHeartbeatTime()
      
      // Trigger stale check
      vi.advanceTimersByTime(10000)
      
      // State should be degraded
      expect(conn.connectionState.value).toBe('degraded')
      
      conn.stopStaleDetection()
    })

    it('returns to connected when real events resume after degraded state', () => {
      const conn = useSSEConnection({
        degradedThresholdMs: 5000,
      })

      conn.startStaleDetection()
      conn.updateLastRealEventTime()

      vi.advanceTimersByTime(3000)
      conn.updateLastHeartbeatTime()
      vi.advanceTimersByTime(3000)
      conn.updateLastHeartbeatTime()
      vi.advanceTimersByTime(10000)

      expect(conn.connectionState.value).toBe('degraded')

      conn.updateLastRealEventTime()
      expect(conn.connectionState.value).toBe('connected')

      conn.stopStaleDetection()
    })
  })

  describe('reset', () => {
    it('should reset all state', () => {
      connection.updateLastRealEventTime()
      connection.updateLastHeartbeatTime()
      connection.connectionState.value = 'connected'
      
      connection.reset()
      
      expect(connection.connectionState.value).toBe('disconnected')
      expect(connection.totalEvents.value).toBe(0)
      expect(connection.totalHeartbeats.value).toBe(0)
    })
  })

  describe('session storage', () => {
    it('should persist and retrieve event ID', () => {
      connection.lastEventId.value = 'event-123'
      connection.persistEventId('session-abc')
      
      expect(sessionStorage.getItem('pythinker-last-event-session-abc')).toBe('event-123')
      
      const retrieved = connection.getPersistedEventId('session-abc')
      expect(retrieved).toBe('event-123')
    })

    it('should cleanup session storage', () => {
      connection.lastEventId.value = 'event-123'
      connection.persistEventId('session-abc')
      sessionStorage.setItem('pythinker-stopped-session-abc', 'true')
      
      connection.cleanupSessionStorage('session-abc')
      
      expect(sessionStorage.getItem('pythinker-last-event-session-abc')).toBeNull()
      expect(sessionStorage.getItem('pythinker-stopped-session-abc')).toBeNull()
    })
  })
})
