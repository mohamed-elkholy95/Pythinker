import { SessionStatus } from '@/types/response'

export const shouldStopSessionOnExit = (status?: SessionStatus): boolean => {
  if (!status) return false
  return [SessionStatus.INITIALIZING, SessionStatus.PENDING].includes(status)
}
