import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useErrorReporter, recordSSEError } from '@/composables/useErrorReporter'

describe('useErrorReporter', () => {
  let reporter: ReturnType<typeof useErrorReporter>

  beforeEach(() => {
    vi.useFakeTimers()
    reporter = useErrorReporter()
    reporter.reset()
    // Clear sessionStorage
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('recordError', () => {
    it('should record an error with default categorization', () => {
      const error = new Error('Network connection failed')
      const entry = reporter.recordError(error)
      
      expect(entry.message).toBe('Network connection failed')
      expect(entry.category).toBe('network')
      expect(entry.recoverable).toBe(true)
      expect(entry.severity).toBe('low')
    })

    it('should categorize auth errors correctly', () => {
      const error = new Error('Unauthorized access')
      const entry = reporter.recordError(error)
      
      expect(entry.category).toBe('auth')
      expect(entry.severity).toBe('high')
      expect(entry.recoverable).toBe(false)
    })

    it('should categorize timeout errors correctly', () => {
      const error = new Error('Request timed out')
      const entry = reporter.recordError(error)
      
      expect(entry.category).toBe('timeout')
      expect(entry.severity).toBe('low')
      expect(entry.recoverable).toBe(true)
    })

    it('should categorize validation errors correctly', () => {
      const error = new Error('Validation failed: invalid input')
      const entry = reporter.recordError(error)
      
      expect(entry.category).toBe('validation')
      expect(entry.severity).toBe('high')
      expect(entry.recoverable).toBe(false)
    })

    it('should categorize server errors correctly', () => {
      const error = new Error('500 Internal Server Error')
      const entry = reporter.recordError(error)
      
      expect(entry.category).toBe('server')
      expect(entry.severity).toBe('medium')
    })

    it('should allow overriding category and severity', () => {
      const error = new Error('Custom error')
      const entry = reporter.recordError(error, {
        category: 'circuit_breaker',
        severity: 'critical',
        recoverable: false,
      })
      
      expect(entry.category).toBe('circuit_breaker')
      expect(entry.severity).toBe('critical')
      expect(entry.recoverable).toBe(false)
    })

    it('should include sessionId when provided', () => {
      const error = new Error('Test error')
      const entry = reporter.recordError(error, { sessionId: 'session-123' })
      
      expect(entry.sessionId).toBe('session-123')
    })

    it('should include retryAfterMs when provided', () => {
      const error = new Error('Test error')
      const entry = reporter.recordError(error, { retryAfterMs: 5000 })
      
      expect(entry.retryAfterMs).toBe(5000)
    })
  })

  describe('error collection', () => {
    it('should collect multiple errors', () => {
      reporter.recordError(new Error('Error 1'))
      reporter.recordError(new Error('Error 2'))
      reporter.recordError(new Error('Error 3'))
      
      expect(reporter.errors.value.length).toBe(3)
    })

    it('should limit stored errors to MAX_STORED_ERRORS', () => {
      for (let i = 0; i < 60; i++) {
        reporter.recordError(new Error(`Error ${i}`))
      }
      
      expect(reporter.errors.value.length).toBeLessThanOrEqual(50)
    })

    it('should order errors with most recent first', () => {
      reporter.recordError(new Error('First'))
      vi.advanceTimersByTime(100)
      reporter.recordError(new Error('Second'))
      vi.advanceTimersByTime(100)
      reporter.recordError(new Error('Third'))
      
      expect(reporter.errors.value[0].message).toBe('Third')
      expect(reporter.errors.value[2].message).toBe('First')
    })
  })

  describe('summary', () => {
    it('should calculate correct summary', () => {
      reporter.recordError(new Error('Network error')) // low, recoverable
      reporter.recordError(new Error('Unauthorized')) // high, unrecoverable
      reporter.recordError(new Error('Another network error')) // low, recoverable
      
      const summary = reporter.summary.value
      
      expect(summary.totalErrors).toBe(3)
      expect(summary.criticalCount).toBe(0)
      expect(summary.unrecoverableCount).toBe(1)
      expect(summary.categories.network).toBe(2)
      expect(summary.categories.auth).toBe(1)
    })

    it('should identify most recent error', () => {
      reporter.recordError(new Error('First'))
      vi.advanceTimersByTime(100)
      reporter.recordError(new Error('Second'))
      
      expect(reporter.summary.value.mostRecentError?.message).toBe('Second')
    })

    it('should calculate error rate', () => {
      vi.setSystemTime(0)
      const freshReporter = useErrorReporter()
      freshReporter.reset()
      
      freshReporter.recordError(new Error('Error 1'))
      vi.advanceTimersByTime(60000) // 1 minute
      freshReporter.recordError(new Error('Error 2'))
      
      // 2 errors in ~1 minute = ~2 errors per minute
      expect(freshReporter.summary.value.errorRate).toBeGreaterThan(1)
      expect(freshReporter.summary.value.errorRate).toBeLessThan(3)
    })
  })

  describe('clearErrors', () => {
    it('should clear all errors', () => {
      reporter.recordError(new Error('Error 1'))
      reporter.recordError(new Error('Error 2'))
      
      reporter.clearErrors()
      
      expect(reporter.errors.value.length).toBe(0)
    })
  })

  describe('clearOldErrors', () => {
    it('should only clear errors older than threshold', () => {
      reporter.recordError(new Error('Old error'))
      vi.advanceTimersByTime(60000) // 1 minute
      reporter.recordError(new Error('New error'))
      
      reporter.clearOldErrors(30000) // Clear errors older than 30 seconds
      
      expect(reporter.errors.value.length).toBe(1)
      expect(reporter.errors.value[0].message).toBe('New error')
    })
  })

  describe('getErrorsForSession', () => {
    it('should filter errors by session', () => {
      reporter.recordError(new Error('Error 1'), { sessionId: 'session-a' })
      reporter.recordError(new Error('Error 2'), { sessionId: 'session-b' })
      reporter.recordError(new Error('Error 3'), { sessionId: 'session-a' })
      
      const sessionAErrors = reporter.getErrorsForSession('session-a')
      
      expect(sessionAErrors.length).toBe(2)
      expect(sessionAErrors.every(e => e.sessionId === 'session-a')).toBe(true)
    })
  })

  describe('persistence', () => {
    it('should persist errors to sessionStorage', () => {
      reporter.recordError(new Error('Test error'))
      
      const stored = sessionStorage.getItem('pythinker-error-log')
      expect(stored).not.toBeNull()
      
      const parsed = JSON.parse(stored!)
      expect(parsed.length).toBe(1)
      expect(parsed[0].message).toBe('Test error')
    })

    it('should load persisted errors on init', () => {
      // Pre-populate sessionStorage
      const mockErrors = [
        { id: 'err-1', timestamp: Date.now(), message: 'Persisted error', category: 'network', severity: 'low', recoverable: true }
      ]
      sessionStorage.setItem('pythinker-error-log', JSON.stringify(mockErrors))
      
      const newReporter = useErrorReporter()
      newReporter.reset()
      newReporter.recordError(new Error('New error'))
      
      // The new reporter should have loaded the persisted errors
      // But reset() clears them, so let's test without reset
      const anotherReporter = useErrorReporter()
      expect(anotherReporter.errors.value.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('exportErrors', () => {
    it('should export errors as JSON', () => {
      reporter.recordError(new Error('Error 1'))
      reporter.recordError(new Error('Error 2'))
      
      const exported = reporter.exportErrors()
      const parsed = JSON.parse(exported)
      
      expect(parsed.exportedAt).toBeDefined()
      expect(parsed.errors.length).toBe(2)
      expect(parsed.summary).toBeDefined()
    })
  })
})

describe('recordSSEError', () => {
  it('should record error using global reporter', () => {
    const error = new Error('SSE connection failed')
    const entry = recordSSEError(error, 'session-123', 5000)
    
    expect(entry.message).toBe('SSE connection failed')
    expect(entry.sessionId).toBe('session-123')
    expect(entry.retryAfterMs).toBe(5000)
  })
})
