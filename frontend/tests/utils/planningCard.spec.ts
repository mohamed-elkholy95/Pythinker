import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildPlanningCardState,
  createPlanningPreviewBatcher,
  normalizePlanningPhase,
  summarizeThinkingText,
  type PlanningProgressState,
} from '@/utils/planningCard'

describe('planningCard utils', () => {
  it('prefers backend planning progress when available', () => {
    const progress: PlanningProgressState = {
      phase: 'planning',
      message: 'Creating an execution plan from requirements.',
      percent: 42,
      complexityCategory: 'medium',
    }

    expect(
      buildPlanningCardState({
        planningProgress: progress,
        isThinkingStreaming: true,
        thinkingText: 'Thinking stream should not override planning progress.',
      })
    ).toEqual({
      phase: 'planning',
      message: 'Creating an execution plan from requirements.',
      progressPercent: 42,
      complexityCategory: 'medium',
    })
  })

  it('uses thinking stream text at the beginning when planning progress has not arrived', () => {
    expect(
      buildPlanningCardState({
        planningProgress: null,
        isThinkingStreaming: true,
        thinkingText: 'Comparing options and identifying constraints before planning.',
      })
    ).toEqual({
      phase: 'received',
      message: 'Comparing options and identifying constraints before planning.',
      progressPercent: undefined,
      complexityCategory: undefined,
    })
  })

  it('returns null when there is no progress event and no thinking text signal', () => {
    expect(
      buildPlanningCardState({
        planningProgress: null,
        isThinkingStreaming: false,
        thinkingText: '   ',
      })
    ).toBeNull()
  })

  it('summarizes long thinking text from the start with word-safe truncation', () => {
    const longText = `start ${'x'.repeat(260)} latest reasoning`
    const result = summarizeThinkingText(longText, 80)

    expect(result.length).toBeLessThanOrEqual(83)
    expect(result.startsWith('start')).toBe(true)
    expect(result.endsWith('...')).toBe(true)
    expect(result.includes('latest reasoning')).toBe(false)
  })

  it('prefers a single leading sentence when multiple sentences exist', () => {
    const text = 'First sentence is short. Second sentence is also short. Third sentence should be excluded.'
    const result = summarizeThinkingText(text, 60)

    expect(result).toBe('First sentence is short.')
  })

  it('truncates the first sentence on a word boundary when it is too long', () => {
    const text = 'This first sentence is deliberately long so the planner card only shows a concise preview before it runs out of space and needs trimming. Second sentence should never be shown.'
    const result = summarizeThinkingText(text, 70)

    expect(result.length).toBeLessThanOrEqual(73)
    expect(result.startsWith('This first sentence is deliberately long')).toBe(true)
    expect(result.endsWith('...')).toBe(true)
    expect(result.includes('Second sentence')).toBe(false)
  })

  it('preserves extended planning phases instead of collapsing them to received', () => {
    expect(normalizePlanningPhase('verifying')).toBe('verifying')
    expect(normalizePlanningPhase('executing_setup')).toBe('executing_setup')
  })

  it('falls back to received for unknown planning phases', () => {
    expect(normalizePlanningPhase('not_a_real_phase')).toBe('received')
  })
})

describe('planning preview batcher', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('flushes the first preview immediately and batches later updates', () => {
    const seen: string[] = []
    const batcher = createPlanningPreviewBatcher((next) => {
      seen.push(next)
    }, 50)

    batcher.push('A')
    batcher.push('AB')
    batcher.push('ABC')

    expect(seen).toEqual(['A'])

    vi.advanceTimersByTime(49)
    expect(seen).toEqual(['A'])

    vi.advanceTimersByTime(1)
    expect(seen).toEqual(['A', 'ABC'])
  })

  it('resets immediately and cancels pending batched updates', () => {
    const seen: string[] = []
    const batcher = createPlanningPreviewBatcher((next) => {
      seen.push(next)
    }, 50)

    batcher.push('Thinking')
    batcher.push('Thinking harder')
    batcher.reset('')

    expect(seen).toEqual(['Thinking', ''])

    vi.advanceTimersByTime(50)
    expect(seen).toEqual(['Thinking', ''])
  })
})
