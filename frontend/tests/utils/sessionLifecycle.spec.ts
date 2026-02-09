import { describe, it, expect } from 'vitest'
import { SessionStatus } from '@/types/response'
import { shouldStopSessionOnExit } from '@/utils/sessionLifecycle'

describe('shouldStopSessionOnExit', () => {
  it.each([
    SessionStatus.INITIALIZING,
    SessionStatus.PENDING,
    SessionStatus.RUNNING,
    SessionStatus.WAITING,
  ])('returns true for %s', (status) => {
    expect(shouldStopSessionOnExit(status)).toBe(true)
  })

  it.each([
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    undefined,
  ])('returns false for %s', (status) => {
    expect(shouldStopSessionOnExit(status)).toBe(false)
  })
})
