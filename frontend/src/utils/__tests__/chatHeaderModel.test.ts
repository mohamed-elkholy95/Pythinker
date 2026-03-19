import { describe, expect, it } from 'vitest'

import {
  normalizeHeaderModelName,
  resolveInitialHeaderModelName,
  resolveNextHeaderModelName,
} from '../chatHeaderModel'

describe('chatHeaderModel', () => {
  it('normalizes the configured model name for header display', () => {
    expect(normalizeHeaderModelName('  gpt-5-mini  ')).toBe('gpt-5-mini')
    expect(normalizeHeaderModelName('')).toBe('')
    expect(normalizeHeaderModelName(undefined)).toBe('')
  })

  it('prefers an incoming flow-selection model when it is present', () => {
    expect(resolveNextHeaderModelName('gpt-5', 'gpt-5-mini')).toBe('gpt-5-mini')
  })

  it('keeps the current header model when the incoming flow-selection model is empty', () => {
    expect(resolveNextHeaderModelName('gpt-5', '   ')).toBe('gpt-5')
    expect(resolveNextHeaderModelName('gpt-5', undefined)).toBe('gpt-5')
  })

  it('falls back to the saved settings model when the live server model is unavailable', () => {
    expect(resolveInitialHeaderModelName('', 'glm-5')).toBe('glm-5')
    expect(resolveInitialHeaderModelName(undefined, 'gpt-5-mini')).toBe('gpt-5-mini')
  })

  it('prefers the live server model over the saved settings model', () => {
    expect(resolveInitialHeaderModelName('kimi-for-coding', 'gpt-5')).toBe('kimi-for-coding')
  })
})
