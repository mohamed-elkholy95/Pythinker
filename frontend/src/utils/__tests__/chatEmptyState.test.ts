import { describe, expect, it } from 'vitest'

import { shouldShowEmptySessionState } from '../chatEmptyState'

describe('shouldShowEmptySessionState', () => {
  it('returns true for an idle session with no messages', () => {
    expect(
      shouldShowEmptySessionState({
        sessionId: 'session-123',
        messageCount: 0,
        hasPendingInitialMessage: false,
        isInitializing: false,
        isLoading: false,
        isSandboxInitializing: false,
        isWaitingForSessionReady: false,
        showSessionWarmupMessage: false,
      }),
    ).toBe(true)
  })

  it('returns false when the session is still warming up or loading', () => {
    expect(
      shouldShowEmptySessionState({
        sessionId: 'session-123',
        messageCount: 0,
        hasPendingInitialMessage: false,
        isInitializing: false,
        isLoading: false,
        isSandboxInitializing: false,
        isWaitingForSessionReady: false,
        showSessionWarmupMessage: true,
      }),
    ).toBe(false)

    expect(
      shouldShowEmptySessionState({
        sessionId: 'session-123',
        messageCount: 0,
        hasPendingInitialMessage: false,
        isInitializing: true,
        isLoading: false,
        isSandboxInitializing: false,
        isWaitingForSessionReady: false,
        showSessionWarmupMessage: false,
      }),
    ).toBe(false)
  })

  it('returns false when there is no concrete empty session to show', () => {
    expect(
      shouldShowEmptySessionState({
        sessionId: undefined,
        messageCount: 0,
        hasPendingInitialMessage: false,
        isInitializing: false,
        isLoading: false,
        isSandboxInitializing: false,
        isWaitingForSessionReady: false,
        showSessionWarmupMessage: false,
      }),
    ).toBe(false)

    expect(
      shouldShowEmptySessionState({
        sessionId: 'session-123',
        messageCount: 1,
        hasPendingInitialMessage: false,
        isInitializing: false,
        isLoading: false,
        isSandboxInitializing: false,
        isWaitingForSessionReady: false,
        showSessionWarmupMessage: false,
      }),
    ).toBe(false)

    expect(
      shouldShowEmptySessionState({
        sessionId: 'session-123',
        messageCount: 0,
        hasPendingInitialMessage: true,
        isInitializing: false,
        isLoading: false,
        isSandboxInitializing: false,
        isWaitingForSessionReady: false,
        showSessionWarmupMessage: false,
      }),
    ).toBe(false)
  })
})
