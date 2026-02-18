import { describe, expect, it, vi } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

import { formatCustomTime, formatRelativeTime, normalizeTimestampSeconds } from '@/utils/time'

describe('time utils', () => {
  it('returns a safe fallback for invalid relative timestamps', () => {
    expect(formatRelativeTime(Number.NaN)).toBe('Just now')
    expect(formatRelativeTime(0)).toBe('Just now')
  })

  it('returns a safe fallback for invalid custom timestamps', () => {
    expect(formatCustomTime(Number.NaN)).toBe('Just now')
    expect(formatCustomTime(0)).toBe('Just now')
  })

  it('normalizes millisecond timestamps to seconds', () => {
    const sec = 1_739_810_000
    const ms = sec * 1000

    expect(normalizeTimestampSeconds(sec)).toBe(sec)
    expect(normalizeTimestampSeconds(ms)).toBe(sec)
  })

  it('formats milliseconds and seconds consistently', () => {
    const sec = Math.floor(Date.now() / 1000) - 125
    const ms = sec * 1000

    expect(formatRelativeTime(ms)).toBe(formatRelativeTime(sec))
    expect(formatCustomTime(ms)).toBe(formatCustomTime(sec))
  })
})
