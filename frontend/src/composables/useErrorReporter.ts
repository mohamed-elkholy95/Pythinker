import { ref, computed, onUnmounted, readonly, getCurrentInstance } from 'vue'

/**
 * Error categories for streaming errors
 */
export type ErrorCategory = 
  | 'network' 
  | 'timeout' 
  | 'auth' 
  | 'validation' 
  | 'server' 
  | 'circuit_breaker'
  | 'unknown'

/**
 * Error severity levels
 */
export type ErrorSeverity = 'low' | 'medium' | 'high' | 'critical'

/**
 * Structured error entry
 */
export interface ErrorEntry {
  id: string
  timestamp: number
  message: string
  category: ErrorCategory
  severity: ErrorSeverity
  recoverable: boolean
  retryAfterMs?: number
  details?: Record<string, unknown>
  sessionId?: string
}

/**
 * Error summary for display
 */
export interface ErrorSummary {
  totalErrors: number
  criticalCount: number
  unrecoverableCount: number
  mostRecentError: ErrorEntry | null
  errorRate: number // errors per minute
  categories: Record<ErrorCategory, number>
}

const MAX_STORED_ERRORS = 50
const STORAGE_KEY = 'pythinker-error-log'
/** Errors older than this are excluded from the summary (prevents stale banners) */
const ERROR_SUMMARY_TTL_MS = 5 * 60 * 1000 // 5 minutes

/**
 * Categorize an error based on its message and type
 */
function categorizeError(error: Error): ErrorCategory {
  const message = error.message.toLowerCase()
  
  if (message.includes('unauthorized') || message.includes('forbidden') || message.includes('401')) {
    return 'auth'
  }
  if (message.includes('validation') || message.includes('422') || message.includes('invalid')) {
    return 'validation'
  }
  if (message.includes('timeout') || message.includes('timed out')) {
    return 'timeout'
  }
  if (message.includes('network') || message.includes('fetch') || message.includes('connection')) {
    return 'network'
  }
  if (message.includes('circuit breaker') || message.includes('temporarily unavailable')) {
    return 'circuit_breaker'
  }
  if (message.includes('500') || message.includes('502') || message.includes('503') || message.includes('server')) {
    return 'server'
  }
  
  return 'unknown'
}

/**
 * Determine error severity
 */
function determineSeverity(category: ErrorCategory): ErrorSeverity {
  // Auth and validation errors are high severity
  if (category === 'auth' || category === 'validation') {
    return 'high'
  }
  
  // Circuit breaker is medium (temporary)
  if (category === 'circuit_breaker') {
    return 'medium'
  }
  
  // Network/timeout are typically low (will auto-retry)
  if (category === 'network' || category === 'timeout') {
    return 'low'
  }
  
  // Server errors are medium-high depending on frequency
  if (category === 'server') {
    return 'medium'
  }
  
  return 'low'
}

/**
 * Check if error is recoverable
 */
function isRecoverable(category: ErrorCategory): boolean {
  return category !== 'auth' && category !== 'validation'
}

/**
 * Composable for collecting, categorizing, and reporting streaming errors
 */
export function useErrorReporter() {
  const errors = ref<ErrorEntry[]>([])
  const startTime = ref(Date.now())
  
  /**
   * Add an error to the log
   */
  function recordError(
    error: Error, 
    options: {
      sessionId?: string
      severity?: ErrorSeverity
      category?: ErrorCategory
      recoverable?: boolean
      retryAfterMs?: number
      details?: Record<string, unknown>
    } = {}
  ): ErrorEntry {
    const category = options.category ?? categorizeError(error)
    const severity = options.severity ?? determineSeverity(category)
    const recoverable = options.recoverable ?? isRecoverable(category)
    
    const entry: ErrorEntry = {
      id: `err-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now(),
      message: error.message,
      category,
      severity,
      recoverable,
      retryAfterMs: options.retryAfterMs,
      details: options.details,
      sessionId: options.sessionId,
    }
    
    // Add to front of array
    errors.value = [entry, ...errors.value].slice(0, MAX_STORED_ERRORS)
    
    // Persist to sessionStorage for post-mortem analysis
    persistErrors()
    
    return entry
  }
  
  /**
   * Clear all errors
   */
  function clearErrors(): void {
    errors.value = []
    persistErrors()
  }
  
  /**
   * Clear errors older than a certain age
   */
  function clearOldErrors(maxAgeMs: number): void {
    const cutoff = Date.now() - maxAgeMs
    errors.value = errors.value.filter(e => e.timestamp > cutoff)
    persistErrors()
  }
  
  /**
   * Get error summary for display
   */
  const summary = computed((): ErrorSummary => {
    const now = Date.now()
    const durationMs = now - startTime.value
    const durationMinutes = durationMs / 60000
    const ttlCutoff = now - ERROR_SUMMARY_TTL_MS

    const categoryCounts: Record<ErrorCategory, number> = {
      network: 0,
      timeout: 0,
      auth: 0,
      validation: 0,
      server: 0,
      circuit_breaker: 0,
      unknown: 0,
    }

    let criticalCount = 0
    let unrecoverableCount = 0

    // Only count recent errors in the summary to prevent stale banners.
    // Errors older than ERROR_SUMMARY_TTL_MS are kept in storage for
    // post-mortem analysis but don't affect the UI.
    const recentErrors = errors.value.filter(e => e.timestamp > ttlCutoff)

    for (const error of recentErrors) {
      categoryCounts[error.category]++
      if (error.severity === 'critical') criticalCount++
      if (!error.recoverable) unrecoverableCount++
    }

    return {
      totalErrors: recentErrors.length,
      criticalCount,
      unrecoverableCount,
      mostRecentError: recentErrors[0] ?? null,
      errorRate: durationMinutes > 0 ? recentErrors.length / durationMinutes : 0,
      categories: categoryCounts,
    }
  })
  
  /**
   * Get errors for a specific session
   */
  function getErrorsForSession(sessionId: string): ErrorEntry[] {
    return errors.value.filter(e => e.sessionId === sessionId)
  }
  
  /**
   * Export errors as JSON for debugging
   */
  function exportErrors(): string {
    return JSON.stringify({
      exportedAt: new Date().toISOString(),
      errors: errors.value,
      summary: summary.value,
    }, null, 2)
  }
  
  /**
   * Persist errors to sessionStorage
   */
  function persistErrors(): void {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(errors.value))
    } catch {
      // Storage might be full or unavailable
    }
  }
  
  /**
   * Load errors from sessionStorage
   */
  function loadPersistedErrors(): void {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed: ErrorEntry[] = JSON.parse(stored)
        // Drop persisted code-bug errors (ReferenceError / TypeError) — these are
        // artefacts of old code that has since been fixed. Re-surfacing them after
        // a deploy creates phantom banners that the user cannot dismiss permanently.
        const isCodeBug = (e: ErrorEntry) =>
          e.message.includes('is not a function') ||
          e.message.includes('is not defined') ||
          e.message.includes('Cannot read propert')
        errors.value = parsed.filter(e => !isCodeBug(e))
        // If we dropped anything, persist the cleaned list immediately
        if (errors.value.length !== parsed.length) persistErrors()
      }
    } catch {
      // Invalid data, ignore
    }
  }
  
  /**
   * Clear persisted errors
   */
  function clearPersistedErrors(): void {
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      // Ignore
    }
  }
  
  /**
   * Reset the reporter (clear errors and reset start time)
   */
  function reset(): void {
    errors.value = []
    startTime.value = Date.now()
    clearPersistedErrors()
  }
  
  // Load persisted errors on init
  loadPersistedErrors()
  
  // Cleanup on unmount only when used inside component setup.
  if (getCurrentInstance()) {
    onUnmounted(() => {
      // Optionally persist on unmount
      persistErrors()
    })
  }
  
  return {
    errors: readonly(errors),
    summary,
    recordError,
    clearErrors,
    clearOldErrors,
    getErrorsForSession,
    exportErrors,
    reset,
  }
}

/**
 * Global error reporter singleton
 */
let globalErrorReporter: ReturnType<typeof useErrorReporter> | null = null

export function getErrorReporter(): ReturnType<typeof useErrorReporter> {
  if (!globalErrorReporter) {
    globalErrorReporter = useErrorReporter()
  }
  return globalErrorReporter
}

/**
 * Helper to record an SSE error from the client
 */
export function recordSSEError(
  error: Error,
  sessionId?: string,
  retryAfterMs?: number
): ErrorEntry {
  const reporter = getErrorReporter()
  return reporter.recordError(error, { sessionId, retryAfterMs })
}
