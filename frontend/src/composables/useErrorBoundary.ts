import { ref, onErrorCaptured } from 'vue'

export interface AppError {
  message: string
  code?: string
  recoverable: boolean
  timestamp: number
}

function normalizeError(err: unknown): AppError {
  if (err instanceof Error) {
    return {
      message: err.message,
      code: (err as { code?: string }).code,
      recoverable: true,
      timestamp: Date.now(),
    }
  }
  return {
    message: String(err),
    recoverable: true,
    timestamp: Date.now(),
  }
}

/**
 * Vue error boundary composable that catches unhandled errors from child components.
 *
 * Uses `onErrorCaptured` to intercept errors before they propagate up and crash
 * the page. Normalizes errors into a consistent `AppError` shape and prevents
 * propagation by returning `false`.
 *
 * Usage:
 * ```typescript
 * const { lastCapturedError, clearError } = useErrorBoundary()
 *
 * // Check for captured errors in template
 * // <div v-if="lastCapturedError">{{ lastCapturedError.message }}</div>
 * ```
 */
export function useErrorBoundary() {
  const lastCapturedError = ref<AppError | null>(null)

  onErrorCaptured((err: unknown, _instance, info: string) => {
    const normalized = normalizeError(err)
    lastCapturedError.value = normalized
    console.error(`[ErrorBoundary] Captured error in ${info}:`, err)
    // Return false to stop propagation (prevents page crash)
    return false
  })

  function clearError() {
    lastCapturedError.value = null
  }

  return { lastCapturedError, clearError }
}
