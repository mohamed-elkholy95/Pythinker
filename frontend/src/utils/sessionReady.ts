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

/** Extract Retry-After from 429 response (Context7: FastAPI-Limiter convention) */
function getRetryAfterMs(error: unknown): number | null {
  if (error && typeof error === 'object' && 'response' in error) {
    const res = (error as { response?: { status?: number; headers?: Record<string, string>; data?: unknown } })
      .response
    if (res?.status === 429) {
      const retryAfter = res.headers?.['retry-after'] ?? (res.data as { retry_after?: number })?.retry_after
      if (typeof retryAfter === 'string') {
        const sec = parseInt(retryAfter, 10)
        return Number.isNaN(sec) ? null : sec * 1000
      }
      if (typeof retryAfter === 'number') return retryAfter * 1000
    }
  }
  return null
}

export async function waitForSessionReady(
  sessionId: string,
  getSessionFn: (sessionId: string) => Promise<SessionStatusResponse>,
  options: WaitForSessionReadyOptions = {}
): Promise<SessionReadyResult> {
  const pollIntervalMs = options.pollIntervalMs ?? 2000
  const maxWaitMs = options.maxWaitMs
  let elapsedMs = 0
  let lastStatus: SessionStatus | null = null

  while (true) {
    if (maxWaitMs !== undefined && elapsedMs >= maxWaitMs && lastStatus === SessionStatus.INITIALIZING) {
      return { status: lastStatus, timedOut: true }
    }

    try {
      const session = await getSessionFn(sessionId)
      lastStatus = session.status
      if (session.status !== SessionStatus.INITIALIZING) {
        return { status: session.status, timedOut: false }
      }
    } catch (err) {
      const retryAfterMs = getRetryAfterMs(err)
      if (retryAfterMs !== null) {
        await new Promise((resolve) => setTimeout(resolve, retryAfterMs))
        elapsedMs += retryAfterMs
        continue
      }
      throw err
    }

    if (maxWaitMs !== undefined && elapsedMs >= maxWaitMs) {
      return { status: lastStatus ?? SessionStatus.INITIALIZING, timedOut: true }
    }

    const waitMs = maxWaitMs !== undefined
      ? Math.min(pollIntervalMs, maxWaitMs - elapsedMs)
      : pollIntervalMs

    await new Promise((resolve) => setTimeout(resolve, waitMs))
    elapsedMs += waitMs
  }
}
