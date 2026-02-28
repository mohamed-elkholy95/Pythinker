import { describe, expect, it } from 'vitest';

import { SessionStatus } from '@/types/response';

import { getRestoreAbortReason, isTerminalSessionStatus } from '../chatRestoreGuards';

describe('chatRestoreGuards', () => {
  it('aborts restore when epoch no longer matches', () => {
    expect(getRestoreAbortReason({
      epoch: 2,
      activeEpoch: 3,
      targetSessionId: 'session-a',
      currentSessionId: 'session-a',
    })).toBe('stale_epoch');
  });

  it('aborts restore when active session id changed', () => {
    expect(getRestoreAbortReason({
      epoch: 5,
      activeEpoch: 5,
      targetSessionId: 'session-a',
      currentSessionId: 'session-b',
    })).toBe('session_mismatch');
  });

  it('allows restore only when epoch and session id both match', () => {
    expect(getRestoreAbortReason({
      epoch: 7,
      activeEpoch: 7,
      targetSessionId: 'session-a',
      currentSessionId: 'session-a',
    })).toBeNull();
  });

  it('recognizes terminal statuses', () => {
    expect(isTerminalSessionStatus(SessionStatus.COMPLETED)).toBe(true);
    expect(isTerminalSessionStatus(SessionStatus.FAILED)).toBe(true);
    expect(isTerminalSessionStatus(SessionStatus.CANCELLED)).toBe(true);
    expect(isTerminalSessionStatus(SessionStatus.RUNNING)).toBe(false);
    expect(isTerminalSessionStatus(undefined)).toBe(false);
  });
});
