export interface SessionReconnectPolicy {
  maxAutoRetries: number
  autoRetryDelaysMs: number[]
  fallbackPollInitialIntervalMs: number
  fallbackPollMaxIntervalMs: number
  fallbackPollMaxAttempts: number
}

export const DEFAULT_SESSION_RECONNECT_POLICY: Readonly<SessionReconnectPolicy> = Object.freeze({
  maxAutoRetries: 4,
  autoRetryDelaysMs: [5000, 15000, 45000, 60000],
  fallbackPollInitialIntervalMs: 5000,
  fallbackPollMaxIntervalMs: 60000,
  fallbackPollMaxAttempts: 24,
})

export const resolveSessionReconnectPolicy = (
  overrides: Partial<SessionReconnectPolicy> = {},
): SessionReconnectPolicy => ({
  maxAutoRetries: overrides.maxAutoRetries ?? DEFAULT_SESSION_RECONNECT_POLICY.maxAutoRetries,
  autoRetryDelaysMs: overrides.autoRetryDelaysMs && overrides.autoRetryDelaysMs.length > 0
    ? [...overrides.autoRetryDelaysMs]
    : [...DEFAULT_SESSION_RECONNECT_POLICY.autoRetryDelaysMs],
  fallbackPollInitialIntervalMs: overrides.fallbackPollInitialIntervalMs
    ?? DEFAULT_SESSION_RECONNECT_POLICY.fallbackPollInitialIntervalMs,
  fallbackPollMaxIntervalMs: overrides.fallbackPollMaxIntervalMs
    ?? DEFAULT_SESSION_RECONNECT_POLICY.fallbackPollMaxIntervalMs,
  fallbackPollMaxAttempts: overrides.fallbackPollMaxAttempts
    ?? DEFAULT_SESSION_RECONNECT_POLICY.fallbackPollMaxAttempts,
})
