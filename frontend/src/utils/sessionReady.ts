import { SessionStatus } from '@/types/response'

export interface SessionStatusResponse {
  status: SessionStatus
}

export interface WaitForSessionReadyOptions {
  pollIntervalMs?: number
  maxWaitMs?: number
  /** Initial delay before the first poll (ms). Lets MongoDB write propagate. */
  initialDelayMs?: number
  /** Max consecutive transient errors before giving up. */
  maxTransientRetries?: number
}

export interface SessionReadyResult {
  status: SessionStatus
  timedOut: boolean
}

/** HTTP status codes that indicate transient infrastructure issues (proxy/gateway). */
const TRANSIENT_STATUS_CODES = new Set([502, 503, 504])

/** Max jitter added to each poll interval to avoid thundering herd (ms). */
const MAX_JITTER_MS = 500

function getHttpStatus(error: unknown): number | undefined {
  if (error && typeof error === 'object' && 'response' in error) {
    const res = (error as { response?: { status?: number } }).response
    return res?.status
  }
  return undefined
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

/** Add random jitter to an interval to prevent synchronized polling. */
function withJitter(intervalMs: number): number {
  return intervalMs + Math.floor(Math.random() * MAX_JITTER_MS)
}

export async function waitForSessionReady(
  sessionId: string,
  getSessionFn: (sessionId: string) => Promise<SessionStatusResponse>,
  options: WaitForSessionReadyOptions = {}
): Promise<SessionReadyResult> {
  const pollIntervalMs = options.pollIntervalMs ?? 2000
  const maxWaitMs = options.maxWaitMs
  const initialDelayMs = options.initialDelayMs ?? 300
  const maxTransientRetries = options.maxTransientRetries ?? 5
  let elapsedMs = 0
  let lastStatus: SessionStatus | null = null
  let consecutiveTransientErrors = 0

  // Brief initial delay to let the session persist to MongoDB before first poll
  if (initialDelayMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, initialDelayMs))
    elapsedMs += initialDelayMs
  }

  while (true) {
    if (maxWaitMs !== undefined && elapsedMs >= maxWaitMs && lastStatus === SessionStatus.INITIALIZING) {
      return { status: lastStatus, timedOut: true }
    }

    try {
      const session = await getSessionFn(sessionId)
      consecutiveTransientErrors = 0
      lastStatus = session.status
      if (session.status !== SessionStatus.INITIALIZING) {
        return { status: session.status, timedOut: false }
      }
    } catch (err) {
      // 429 rate limit — respect Retry-After header
      const retryAfterMs = getRetryAfterMs(err)
      if (retryAfterMs !== null) {
        await new Promise((resolve) => setTimeout(resolve, retryAfterMs))
        elapsedMs += retryAfterMs
        continue
      }

      // 502/503/504 — transient proxy/gateway errors, retry with backoff
      const status = getHttpStatus(err)
      if (status !== undefined && TRANSIENT_STATUS_CODES.has(status)) {
        consecutiveTransientErrors++
        if (consecutiveTransientErrors >= maxTransientRetries) {
          throw err
        }
        // Exponential backoff: 1s, 2s, 4s, 8s... capped at poll interval
        const backoffMs = Math.min(1000 * 2 ** (consecutiveTransientErrors - 1), pollIntervalMs)
        const waitMs = withJitter(backoffMs)
        await new Promise((resolve) => setTimeout(resolve, waitMs))
        elapsedMs += waitMs
        continue
      }

      // Non-transient error — propagate immediately
      throw err
    }

    if (maxWaitMs !== undefined && elapsedMs >= maxWaitMs) {
      return { status: lastStatus ?? SessionStatus.INITIALIZING, timedOut: true }
    }

    const waitMs = maxWaitMs !== undefined
      ? Math.min(withJitter(pollIntervalMs), maxWaitMs - elapsedMs)
      : withJitter(pollIntervalMs)

    await new Promise((resolve) => setTimeout(resolve, waitMs))
    elapsedMs += waitMs
  }
}
