import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useCircuitBreaker, resetSseCircuitBreaker, getSseCircuitBreaker } from '@/composables/useCircuitBreaker'

describe('useCircuitBreaker', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetSseCircuitBreaker()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('initial state', () => {
    it('should start in closed state', () => {
      const circuit = useCircuitBreaker()
      expect(circuit.state.value).toBe('closed')
      expect(circuit.failureCount.value).toBe(0)
      expect(circuit.isRequestAllowed.value).toBe(true)
      expect(circuit.isOpen.value).toBe(false)
    })
  })

  describe('failure recording', () => {
    it('should increment failure count on recordFailure', () => {
      const circuit = useCircuitBreaker()
      circuit.recordFailure()
      expect(circuit.failureCount.value).toBe(1)
    })

    it('should open circuit after threshold failures', () => {
      const circuit = useCircuitBreaker({ failureThreshold: 3 })
      circuit.recordFailure()
      circuit.recordFailure()
      expect(circuit.state.value).toBe('closed')
      
      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')
      expect(circuit.isRequestAllowed.value).toBe(false)
    })
  })

  describe('success recording', () => {
    it('should reset failure count on success in closed state', () => {
      const circuit = useCircuitBreaker()
      circuit.recordFailure()
      circuit.recordFailure()
      expect(circuit.failureCount.value).toBe(2)
      
      circuit.recordSuccess()
      expect(circuit.failureCount.value).toBe(0)
    })

    it('should close circuit after enough successes in half-open', () => {
      const circuit = useCircuitBreaker({ 
        failureThreshold: 1,
        halfOpenSuccessThreshold: 2 
      })
      
      // Open the circuit
      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')
      
      // Move to half-open by waiting for reset timeout
      vi.advanceTimersByTime(30001)
      expect(circuit.state.value).toBe('half-open')
      
      // Record successes
      circuit.recordSuccess()
      expect(circuit.state.value).toBe('half-open')
      
      circuit.recordSuccess()
      expect(circuit.state.value).toBe('closed')
    })

    it('should reopen circuit on failure in half-open', () => {
      const circuit = useCircuitBreaker({ failureThreshold: 1 })
      
      // Open the circuit
      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')
      
      // Move to half-open
      vi.advanceTimersByTime(30001)
      expect(circuit.state.value).toBe('half-open')
      
      // Failure in half-open should reopen
      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')
    })
  })

  describe('state transitions', () => {
    it('should transition from open to half-open after reset timeout', () => {
      const circuit = useCircuitBreaker({ 
        failureThreshold: 1,
        resetTimeoutMs: 5000 
      })
      
      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')
      
      vi.advanceTimersByTime(4999)
      expect(circuit.state.value).toBe('open')
      
      vi.advanceTimersByTime(2)
      expect(circuit.state.value).toBe('half-open')
    })

    it('should update resetTimeRemaining countdown', () => {
      const circuit = useCircuitBreaker({ 
        failureThreshold: 1,
        resetTimeoutMs: 10000 
      })
      
      circuit.recordFailure()
      expect(circuit.resetTimeRemaining.value).toBe(10000)
      
      vi.advanceTimersByTime(1000)
      expect(circuit.resetTimeRemaining.value).toBeLessThan(10000)
    })

    it('should close automatically when half-open health probe succeeds', async () => {
      const healthProbe = vi.fn().mockResolvedValue(true)
      const circuit = useCircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 5000,
        healthProbe,
      })

      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')

      await vi.advanceTimersByTimeAsync(5001)

      expect(healthProbe).toHaveBeenCalledTimes(1)
      expect(circuit.state.value).toBe('closed')
    })

    it('should reopen automatically when half-open health probe fails', async () => {
      const healthProbe = vi.fn().mockResolvedValue(false)
      const circuit = useCircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 5000,
        healthProbe,
      })

      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')

      await vi.advanceTimersByTimeAsync(5001)

      expect(healthProbe).toHaveBeenCalledTimes(1)
      expect(circuit.state.value).toBe('open')
    })
  })

  describe('force operations', () => {
    it('should force open circuit', () => {
      const circuit = useCircuitBreaker()
      expect(circuit.state.value).toBe('closed')
      
      circuit.forceOpen()
      expect(circuit.state.value).toBe('open')
    })

    it('should force close circuit', () => {
      const circuit = useCircuitBreaker({ failureThreshold: 1 })
      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')
      
      circuit.forceClose()
      expect(circuit.state.value).toBe('closed')
      expect(circuit.failureCount.value).toBe(0)
    })

    it('should reset all state', () => {
      const circuit = useCircuitBreaker({ failureThreshold: 1 })
      circuit.recordFailure()
      expect(circuit.state.value).toBe('open')
      
      circuit.reset()
      expect(circuit.state.value).toBe('closed')
      expect(circuit.failureCount.value).toBe(0)
    })
  })

  describe('callbacks', () => {
    it('should call onOpen callback when circuit opens', () => {
      const onOpen = vi.fn()
      const circuit = useCircuitBreaker({ 
        failureThreshold: 1,
        onOpen 
      })
      
      circuit.recordFailure()
      expect(onOpen).toHaveBeenCalledTimes(1)
    })

    it('should call onClose callback when circuit closes', () => {
      const onClose = vi.fn()
      const circuit = useCircuitBreaker({ 
        failureThreshold: 1,
        halfOpenSuccessThreshold: 1,
        onClose 
      })
      
      circuit.recordFailure()
      vi.advanceTimersByTime(30001)
      circuit.recordSuccess()
      
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('should call onHalfOpen callback when entering half-open', () => {
      const onHalfOpen = vi.fn()
      const circuit = useCircuitBreaker({ 
        failureThreshold: 1,
        resetTimeoutMs: 5000,
        onHalfOpen 
      })
      
      circuit.recordFailure()
      vi.advanceTimersByTime(5001)
      
      expect(onHalfOpen).toHaveBeenCalledTimes(1)
    })
  })

  describe('failure window', () => {
    it('should only count failures within the window', () => {
      const circuit = useCircuitBreaker({ 
        failureThreshold: 3,
        failureWindowMs: 1000 
      })
      
      circuit.recordFailure()
      circuit.recordFailure()
      expect(circuit.state.value).toBe('closed')
      
      // Wait for window to expire
      vi.advanceTimersByTime(1001)
      
      // These should be counted fresh
      circuit.recordFailure()
      expect(circuit.state.value).toBe('closed')
    })
  })
})

describe('getSseCircuitBreaker', () => {
  it('should return a singleton instance', () => {
    resetSseCircuitBreaker()
    const circuit1 = getSseCircuitBreaker()
    const circuit2 = getSseCircuitBreaker()
    
    expect(circuit1).toBe(circuit2)
  })
})
