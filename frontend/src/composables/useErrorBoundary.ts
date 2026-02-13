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
