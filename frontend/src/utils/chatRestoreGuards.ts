import { SessionStatus } from '@/types/response';

export type RestoreAbortReason = 'stale_epoch' | 'session_mismatch';

export interface RestoreGuardInput {
  epoch: number;
  activeEpoch: number;
  targetSessionId: string;
  currentSessionId?: string;
}

export const getRestoreAbortReason = ({
  epoch,
  activeEpoch,
  targetSessionId,
  currentSessionId,
}: RestoreGuardInput): RestoreAbortReason | null => {
  if (epoch !== activeEpoch) {
    return 'stale_epoch';
  }
  if (currentSessionId !== targetSessionId) {
    return 'session_mismatch';
  }
  return null;
};

export const isTerminalSessionStatus = (status?: SessionStatus): boolean => {
  return status === SessionStatus.COMPLETED
    || status === SessionStatus.FAILED
    || status === SessionStatus.CANCELLED;
};
