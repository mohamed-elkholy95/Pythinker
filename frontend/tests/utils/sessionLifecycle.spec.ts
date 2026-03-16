import { describe, it, expect } from 'vitest'
import { SessionStatus } from '@/types/response'
import { shouldStopSessionOnExit } from '@/utils/sessionLifecycle'

describe('shouldStopSessionOnExit', () => {
  it.each([
    SessionStatus.INITIALIZING,
    SessionStatus.PENDING,
  ])('returns true for %s', (status) => {
    expect(shouldStopSessionOnExit(status)).toBe(true)
  })

  it.each([
    SessionStatus.RUNNING,
    SessionStatus.WAITING,
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    undefined,
  ])('returns false for %s', (status) => {
    expect(shouldStopSessionOnExit(status)).toBe(false)
  })
})
