const SSE_DEBUG_STORAGE_KEY = 'pythinker:sse-debug'
const ENABLED_VALUES = new Set(['1', 'true', 'yes', 'on'])

export function isSseDiagnosticsEnabled(): boolean {
  const envValue = String(import.meta.env.VITE_SSE_DEBUG ?? '').toLowerCase()
  if (ENABLED_VALUES.has(envValue)) {
    return true
  }

  if (typeof window === 'undefined') {
    return false
  }

  const storageValue = String(window.localStorage.getItem(SSE_DEBUG_STORAGE_KEY) ?? '').toLowerCase()
  return ENABLED_VALUES.has(storageValue)
}

export function getSseDiagnosticsHeaderValue(): string | undefined {
  return isSseDiagnosticsEnabled() ? '1' : undefined
}

export function logSseDiagnostics(scope: string, message: string, details: Record<string, unknown> = {}): void {
  if (!isSseDiagnosticsEnabled()) {
    return
  }

  console.debug(`[SSE-DIAG][${scope}] ${message}`, {
    ts: new Date().toISOString(),
    ...details,
  })
}
