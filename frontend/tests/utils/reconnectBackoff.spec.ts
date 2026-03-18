import { describe, expect, it } from 'vitest'
import { calculateReconnectDelay } from '@/utils/reconnectBackoff'

describe('calculateReconnectDelay', () => {
  it('applies equal jitter to the first reconnect attempt', () => {
    const minDelay = calculateReconnectDelay(0, { rng: () => 0 })
    const maxDelay = calculateReconnectDelay(0, { rng: () => 1 })

    expect(minDelay).toBe(500)
    expect(maxDelay).toBe(1000)
  })

  it('caps exponential growth at maxDelayMs', () => {
    const delay = calculateReconnectDelay(8, {
      baseDelayMs: 1000,
      maxDelayMs: 10_000,
      rng: () => 0.6,
    })

    // Capped delay is 10000 -> equal jitter range [5000, 10000]
    expect(delay).toBe(8000)
  })

  it('normalizes invalid attempt values', () => {
    const fromNegative = calculateReconnectDelay(-3, { rng: () => 0.4 })
    const fromNaN = calculateReconnectDelay(Number.NaN, { rng: () => 0.4 })

    expect(fromNegative).toBe(fromNaN)
  })
})
