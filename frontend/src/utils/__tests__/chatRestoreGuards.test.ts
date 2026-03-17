import { describe, expect, it } from 'vitest';

import { SessionStatus } from '@/types/response';

import {
  getRestoreAbortReason,
  isTerminalSessionStatus,
  shouldReplayHistoryEvent,
} from '../chatRestoreGuards';

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

  it('replays stream events for terminal sessions', () => {
    expect(shouldReplayHistoryEvent('stream', SessionStatus.COMPLETED)).toBe(true);
    expect(shouldReplayHistoryEvent('stream', SessionStatus.FAILED)).toBe(true);
    expect(shouldReplayHistoryEvent('stream', SessionStatus.CANCELLED)).toBe(true);
  });

  it('skips stream events for non-terminal or unknown sessions', () => {
    expect(shouldReplayHistoryEvent('stream', SessionStatus.RUNNING)).toBe(false);
    expect(shouldReplayHistoryEvent('stream', SessionStatus.PENDING)).toBe(false);
    expect(shouldReplayHistoryEvent('stream', undefined)).toBe(false);
  });

  it('always replays non-stream events', () => {
    expect(shouldReplayHistoryEvent('message', SessionStatus.RUNNING)).toBe(true);
    expect(shouldReplayHistoryEvent('report', undefined)).toBe(true);
    expect(shouldReplayHistoryEvent('done', SessionStatus.COMPLETED)).toBe(true);
  });
});
