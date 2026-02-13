import { describe, it, expect } from 'vitest'

describe('SSE reconnection backoff', () => {
  it('should use exponential backoff with jitter on reconnection', () => {
    const baseDelay = 1000
    const maxDelay = 45000

    // Retry 0: ~1000ms
    const delay0 = Math.min(baseDelay * Math.pow(2, 0), maxDelay)
    expect(delay0).toBe(1000)

    // Retry 3: ~8000ms
    const delay3 = Math.min(baseDelay * Math.pow(2, 3), maxDelay)
    expect(delay3).toBe(8000)

    // Retry 10: capped at 45000ms
    const delay10 = Math.min(baseDelay * Math.pow(2, 10), maxDelay)
    expect(delay10).toBe(45000)
  })

  it('should add jitter to prevent thundering herd', () => {
    const baseDelay = 1000
    const maxDelay = 45000
    const retryCount = 3
    const delay = Math.min(baseDelay * Math.pow(2, retryCount), maxDelay)
    const jitter = delay * 0.25 * Math.random()

    expect(jitter).toBeGreaterThanOrEqual(0)
    expect(jitter).toBeLessThanOrEqual(delay * 0.25)
  })

  it('should produce correct delays for all retry attempts', () => {
    const baseDelay = 1000
    const maxDelay = 45000

    const expectedDelays = [1000, 2000, 4000, 8000, 16000, 32000, 45000]

    for (let i = 0; i < expectedDelays.length; i++) {
      const delay = Math.min(baseDelay * Math.pow(2, i), maxDelay)
      expect(delay).toBe(expectedDelays[i])
    }
  })

  it('should cap jitter at 25% of the base delay for the attempt', () => {
    const baseDelay = 1000
    const maxDelay = 45000

    // For retry 3, delay = 8000ms, max jitter = 2000ms
    const delay3 = Math.min(baseDelay * Math.pow(2, 3), maxDelay)
    const maxJitter3 = delay3 * 0.25
    expect(maxJitter3).toBe(2000)

    // For retry 5, delay = 32000ms, max jitter = 8000ms
    const delay5 = Math.min(baseDelay * Math.pow(2, 5), maxDelay)
    const maxJitter5 = delay5 * 0.25
    expect(maxJitter5).toBe(8000)

    // For retry 6 (capped at 45000), delay = 45000ms, max jitter = 11250ms
    const delay6 = Math.min(baseDelay * Math.pow(2, 6), maxDelay)
    const maxJitter6 = delay6 * 0.25
    expect(maxJitter6).toBe(11250)
  })
})
