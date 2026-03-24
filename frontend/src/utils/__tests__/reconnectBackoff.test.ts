import { describe, it, expect } from 'vitest'
import { calculateReconnectDelay } from '@/utils/reconnectBackoff'

describe('calculateReconnectDelay', () => {
  const fixedRng = () => 0.5

  it('returns a value between half and full capped delay', () => {
    // With rng=0.5, result should be half + 0.5*half = 0.75 * cappedDelay
    const delay = calculateReconnectDelay(0, { baseDelayMs: 1000, rng: fixedRng })
    // attempt 0 → exponential = 1000 * 2^0 = 1000, half = 500
    // result = 500 + 0.5*500 = 750
    expect(delay).toBe(750)
  })

  it('increases delay exponentially with attempt number', () => {
    const d0 = calculateReconnectDelay(0, { baseDelayMs: 1000, rng: fixedRng })
    const d1 = calculateReconnectDelay(1, { baseDelayMs: 1000, rng: fixedRng })
    const d2 = calculateReconnectDelay(2, { baseDelayMs: 1000, rng: fixedRng })
    expect(d1).toBeGreaterThan(d0)
    expect(d2).toBeGreaterThan(d1)
  })

  it('caps delay at maxDelayMs', () => {
    const delay = calculateReconnectDelay(20, {
      baseDelayMs: 1000,
      maxDelayMs: 10_000,
      rng: () => 1,
    })
    // rng=1 → half + 1*half = cappedDelay = 10_000
    expect(delay).toBe(10_000)
  })

  it('returns minimum half of capped delay when rng returns 0', () => {
    const delay = calculateReconnectDelay(0, {
      baseDelayMs: 1000,
      maxDelayMs: 10_000,
      rng: () => 0,
    })
    // attempt 0, exponential = 1000, half = 500, result = 500 + 0 = 500
    expect(delay).toBe(500)
  })

  it('handles non-finite attempt gracefully', () => {
    const delay = calculateReconnectDelay(Infinity, { baseDelayMs: 1000, rng: fixedRng })
    // Non-finite → safeAttempt = 0
    expect(delay).toBe(750)
  })

  it('handles negative attempt gracefully', () => {
    const delay = calculateReconnectDelay(-5, { baseDelayMs: 1000, rng: fixedRng })
    // Negative → safeAttempt = 0
    expect(delay).toBe(750)
  })

  it('uses default options when none provided', () => {
    const delay = calculateReconnectDelay(0)
    // baseDelayMs=1000, maxDelayMs=10_000, rng=Math.random
    expect(delay).toBeGreaterThanOrEqual(500)
    expect(delay).toBeLessThanOrEqual(1000)
  })

  it('respects custom baseDelayMs', () => {
    const delay = calculateReconnectDelay(0, { baseDelayMs: 2000, rng: fixedRng })
    // exponential = 2000, half = 1000, result = 1000 + 500 = 1500
    expect(delay).toBe(1500)
  })
})
