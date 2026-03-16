import { describe, expect, it } from 'vitest'

import {
  adaptiveSmoothing,
  isJitterMove,
  stepTowards,
  type CursorMotionConfig,
} from '@/utils/agentCursorMotion'

const BASE_CONFIG: CursorMotionConfig = {
  baseSmoothing: 12,
  minSmoothing: 10,
  maxSmoothing: 26,
  distanceBoost: 0.035,
  maxSpeedPxPerSec: 2200,
  settleThresholdPx: 0.5,
  jitterThresholdPx: 0.75,
}

describe('agentCursorMotion', () => {
  it('increases smoothing with distance while respecting clamps', () => {
    const near = adaptiveSmoothing(5, BASE_CONFIG)
    const mid = adaptiveSmoothing(120, BASE_CONFIG)
    const far = adaptiveSmoothing(10_000, BASE_CONFIG)

    expect(mid).toBeGreaterThan(near)
    expect(far).toBeGreaterThanOrEqual(mid)
    expect(near).toBeGreaterThanOrEqual(BASE_CONFIG.minSmoothing)
    expect(far).toBeLessThanOrEqual(BASE_CONFIG.maxSmoothing)
  })

  it('ignores micro-jitter movement below threshold', () => {
    expect(isJitterMove(10, 10, 10.4, 10.3, BASE_CONFIG)).toBe(true)
    expect(isJitterMove(10, 10, 11.2, 10.9, BASE_CONFIG)).toBe(false)
  })

  it('respects speed cap per frame for large jumps', () => {
    const config: CursorMotionConfig = {
      ...BASE_CONFIG,
      maxSpeedPxPerSec: 1200,
    }

    const next = stepTowards(0, 0, 1000, 0, 0.016, config, false)
    const movedDistance = Math.hypot(next.x, next.y)
    const maxDistance = config.maxSpeedPxPerSec * 0.016

    expect(movedDistance).toBeLessThanOrEqual(maxDistance + 1e-6)
    expect(next.settled).toBe(false)
  })

  it('snaps directly to target in reduced-motion mode', () => {
    const next = stepTowards(20, 40, 500, 800, 0.016, BASE_CONFIG, true)

    expect(next.x).toBe(500)
    expect(next.y).toBe(800)
    expect(next.settled).toBe(true)
  })

  it('snaps when already within settle threshold', () => {
    const next = stepTowards(100, 100, 100.2, 100.2, 0.016, BASE_CONFIG, false)

    expect(next.x).toBe(100.2)
    expect(next.y).toBe(100.2)
    expect(next.settled).toBe(true)
  })
})
