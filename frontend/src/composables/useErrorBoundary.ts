import { ref, onErrorCaptured, type ComponentPublicInstance } from 'vue'
import { getErrorReporter } from './useErrorReporter'

export interface AppError {
  message: string
  code?: string
  recoverable: boolean
  timestamp: number
  severity: 'low' | 'medium' | 'high' | 'critical'
  component?: string
}

/**
 * Errors that are never recoverable (code bugs)
 */
const NON_RECOVERABLE_PATTERNS = [
  'TypeError',
  'SyntaxError',
  'ReferenceError',
  'RangeError',
  'InternalError',
]

/**
 * Error messages that indicate non-recoverable issues
 */
const NON_RECOVERABLE_MESSAGES = [
  'is not a function',
  'is not defined',
  'cannot read properties',
  'cannot set properties',
  'undefined is not',
  'null is not',
  'unexpected token',
  'invalid or unexpected token',
]

/**
 * Transient render errors from non-critical UI subsystems.
 * These are typically timing/race conditions during component mount/unmount
 * that don't affect core functionality. They are logged but NOT reported
 * to the error reporter (which would trigger the scary connection banner).
 */
const TRANSIENT_ERROR_PATTERNS = [
  // Screencast/live viewer stats timing races
  "reading 'fps'",
  "reading 'bytesPerSec'",
  "reading 'frameCount'",
  "reading 'toFixed'",
  // Konva/canvas teardown races
  "reading 'getNode'",
  "reading 'batchDraw'",
  // Vue template ref access during unmount
  "reading 'zoomCtrl'",
  "reading 'annotationLayer'",
]

/**
 * Check if an error is recoverable
 */
function isRecoverableError(err: unknown): boolean {
  if (!(err instanceof Error)) {
    // Non-Error objects are usually unexpected
    return false
  }

  // Check error type
  const errorName = err.constructor?.name || err.name || ''
  if (NON_RECOVERABLE_PATTERNS.some(pattern => errorName.includes(pattern))) {
    return false
  }

  // Check error message
  const message = err.message.toLowerCase()
  if (NON_RECOVERABLE_MESSAGES.some(pattern => message.includes(pattern.toLowerCase()))) {
    return false
  }

  // Network, timeout, and async errors are usually recoverable
  if (
    message.includes('network') ||
    message.includes('timeout') ||
    message.includes('fetch') ||
    message.includes('connection') ||
    message.includes('abort')
  ) {
    return true
  }

  // Default to recoverable for unknown errors (let user retry)
  return true
}

/**
 * Determine error severity
 */
function determineSeverity(err: unknown, recoverable: boolean): 'low' | 'medium' | 'high' | 'critical' {
  if (!recoverable) {
    return 'critical'
  }

  if (err instanceof Error) {
    const message = err.message.toLowerCase()

    // Auth errors are high severity
    if (message.includes('unauthorized') || message.includes('forbidden')) {
      return 'high'
    }

    // Network/timeout are low
    if (message.includes('network') || message.includes('timeout')) {
      return 'low'
    }
  }

  return 'medium'
}

function normalizeError(err: unknown, component?: string): AppError {
  if (err instanceof Error) {
    const recoverable = isRecoverableError(err)
    return {
      message: err.message,
      code: (err as { code?: string }).code,
      recoverable,
      timestamp: Date.now(),
      severity: determineSeverity(err, recoverable),
      component,
    }
  }

  // Non-Error objects are not recoverable
  return {
    message: String(err),
    recoverable: false,
    timestamp: Date.now(),
    severity: 'critical',
    component,
  }
}

export function useErrorBoundary() {
  const lastCapturedError = ref<AppError | null>(null)
  const errorCount = ref(0)

  onErrorCaptured((err: unknown, instance: ComponentPublicInstance | null, info: string) => {
    const componentName = instance?.$options?.name || instance?.$options?.__name || undefined
    const normalized = normalizeError(err, componentName)
    lastCapturedError.value = normalized
    errorCount.value += 1

    // Check if this is a transient render error from a non-critical UI subsystem.
    // These are timing races (e.g., accessing screencast stats during component
    // teardown) that resolve on the next render cycle. Log them but don't report
    // to the error reporter — reporting triggers the ConnectionStatusBanner which
    // is disproportionate for a benign UI timing glitch.
    const errMsg = err instanceof Error ? err.message : String(err)
    const isTransient = TRANSIENT_ERROR_PATTERNS.some(p => errMsg.includes(p))

    if (isTransient) {
      console.warn(`[ErrorBoundary] Transient render error in ${info} (suppressed from banner):`, err)
      return false
    }

    console.error(`[ErrorBoundary] Captured error in ${info}:`, err)

    // Log to error reporter if available
    try {
      const reporter = getErrorReporter()
      reporter.recordError(err instanceof Error ? err : new Error(String(err)), {
        severity: normalized.severity,
        recoverable: normalized.recoverable,
        details: { info, component: componentName },
      })
    } catch {
      // Error reporter not available
    }

    // Return false to stop propagation (prevents page crash)
    return false
  })

  function clearError() {
    lastCapturedError.value = null
  }

  function reset() {
    lastCapturedError.value = null
    errorCount.value = 0
  }

  return {
    lastCapturedError,
    errorCount,
    clearError,
    reset,
    isRecoverableError,
  }
}
