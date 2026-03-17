export interface ReconnectBackoffOptions {
  baseDelayMs?: number
  maxDelayMs?: number
  rng?: () => number
}

/**
 * Equal-jitter exponential backoff.
 * Keeps retry delays bounded while preventing reconnect stampedes.
 */
export function calculateReconnectDelay(
  attempt: number,
  options: ReconnectBackoffOptions = {},
): number {
  const baseDelayMs = options.baseDelayMs ?? 1000
  const maxDelayMs = options.maxDelayMs ?? 10_000
  const rng = options.rng ?? Math.random

  const safeAttempt = Number.isFinite(attempt) ? Math.max(0, Math.floor(attempt)) : 0
  const exponentialDelay = baseDelayMs * (2 ** safeAttempt)
  const cappedDelay = Math.min(exponentialDelay, maxDelayMs)

  const half = cappedDelay / 2
  return Math.round(half + (rng() * half))
}
