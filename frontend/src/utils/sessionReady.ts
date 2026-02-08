import { SessionStatus } from '@/types/response'

export interface SessionStatusResponse {
  status: SessionStatus
}

export interface WaitForSessionReadyOptions {
  pollIntervalMs?: number
  maxWaitMs?: number
}

export interface SessionReadyResult {
  status: SessionStatus
  timedOut: boolean
}

export async function waitForSessionReady(
  sessionId: string,
  getSessionFn: (sessionId: string) => Promise<SessionStatusResponse>,
  options: WaitForSessionReadyOptions = {}
): Promise<SessionReadyResult> {
  const pollIntervalMs = options.pollIntervalMs ?? 500
  const maxWaitMs = options.maxWaitMs
  let elapsedMs = 0
  let lastStatus: SessionStatus | null = null

  while (true) {
    if (maxWaitMs !== undefined && elapsedMs >= maxWaitMs && lastStatus === SessionStatus.INITIALIZING) {
      return { status: lastStatus, timedOut: true }
    }

    const session = await getSessionFn(sessionId)
    lastStatus = session.status
    if (session.status !== SessionStatus.INITIALIZING) {
      return { status: session.status, timedOut: false }
    }

    if (maxWaitMs !== undefined && elapsedMs >= maxWaitMs) {
      return { status: session.status, timedOut: true }
    }

    const waitMs = maxWaitMs !== undefined
      ? Math.min(pollIntervalMs, maxWaitMs - elapsedMs)
      : pollIntervalMs

    await new Promise((resolve) => setTimeout(resolve, waitMs))
    elapsedMs += waitMs
  }
}
