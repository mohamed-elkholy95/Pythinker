/**
 * Vue 3 API Resilience Plugin
 *
 * Provides automatic retry with exponential backoff for transient network
 * errors (ECONNREFUSED, ERR_NETWORK, ETIMEDOUT, 502/503/504) on the shared
 * Axios client. Exposes a reactive `$apiResilience` state for UI indicators.
 *
 * The retry interceptor is registered BEFORE the auth/error-formatting
 * interceptor in client.ts so it receives raw AxiosErrors with full config
 * access. This is achieved by ejecting the existing interceptor and
 * re-registering it after the retry interceptor.
 *
 * Options API:
 *   <div v-if="!$apiResilience.isReachable">Backend is reconnecting...</div>
 *
 * Composition API:
 *   const resilience = useApiResilience()
 *   watch(() => resilience.isReachable, (ok) => { ... })
 */
import { type App, type InjectionKey, inject, reactive, readonly } from 'vue'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'
import {
  apiClient,
  _responseInterceptorId,
  _responseInterceptorFulfilled,
  _responseInterceptorRejected,
} from '@/api/client'

// ────────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────────

export interface ApiResilienceOptions {
  /** Maximum retry attempts per request (default: 3) */
  maxRetries?: number
  /** Base delay in ms for exponential backoff (default: 1_000) */
  baseDelayMs?: number
  /** Maximum delay cap in ms (default: 10_000) */
  maxDelayMs?: number
  /** Only retry safe/idempotent HTTP methods (default: true) */
  safeMethodsOnly?: boolean
}

export interface ApiResilienceState {
  /** Whether the backend is currently reachable */
  isReachable: boolean
  /** Consecutive failed network probes */
  consecutiveFailures: number
  /** Timestamp (ms) of last successful API response */
  lastSuccessAt: number | null
  /** Whether a retry is currently in-flight */
  isRetrying: boolean
}

/** Config with retry metadata (preserved across Axios mergeConfig). */
interface RetryableConfig extends InternalAxiosRequestConfig {
  __retryCount?: number
  __retryable?: boolean
}

// ────────────────────────────────────────────────────────────────────
// Injection key & composable
// ────────────────────────────────────────────────────────────────────

export const API_RESILIENCE_KEY: InjectionKey<Readonly<ApiResilienceState>> =
  Symbol('api-resilience')

/**
 * Composable to access resilience state from Composition API components.
 */
export function useApiResilience(): Readonly<ApiResilienceState> {
  const state = inject(API_RESILIENCE_KEY)
  if (!state) {
    return readonly(
      reactive<ApiResilienceState>({
        isReachable: true,
        consecutiveFailures: 0,
        lastSuccessAt: null,
        isRetrying: false,
      }),
    )
  }
  return state
}

// ────────────────────────────────────────────────────────────────────
// Options API type augmentation
// ────────────────────────────────────────────────────────────────────

declare module 'vue' {
  interface ComponentCustomProperties {
    /** Reactive API resilience state (provided by apiResiliencePlugin). */
    $apiResilience: Readonly<ApiResilienceState>
  }
}

// ────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────

/** HTTP methods that are safe to retry (idempotent). */
const SAFE_METHODS = new Set(['get', 'head', 'options', 'put', 'delete'])

/** Axios error codes indicating transient network issues. */
const RETRYABLE_CODES = new Set([
  'ECONNREFUSED',
  'ECONNRESET',
  'ECONNABORTED',
  'ETIMEDOUT',
  'ERR_NETWORK',
  'ERR_BAD_RESPONSE',
])

/** HTTP status codes worth retrying (server overloaded / restarting). */
const RETRYABLE_STATUSES = new Set([502, 503, 504])

function isRetryableError(error: AxiosError): boolean {
  if (!error.response && error.code && RETRYABLE_CODES.has(error.code)) return true
  if (error.response && RETRYABLE_STATUSES.has(error.response.status)) return true
  return false
}

function isNetworkError(error: AxiosError): boolean {
  return !error.response && !!error.code && RETRYABLE_CODES.has(error.code)
}

function isSafeMethod(config: RetryableConfig, safeOnly: boolean): boolean {
  if (!safeOnly) return true
  return SAFE_METHODS.has((config.method ?? 'get').toLowerCase())
}

function computeDelay(attempt: number, baseMs: number, maxMs: number): number {
  const exponential = baseMs * 2 ** attempt
  const capped = Math.min(exponential, maxMs)
  return capped + capped * 0.25 * Math.random()
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// ────────────────────────────────────────────────────────────────────
// Plugin
// ────────────────────────────────────────────────────────────────────

const apiResiliencePlugin = {
  install(app: App, options: ApiResilienceOptions = {}): void {
    const {
      maxRetries = 3,
      baseDelayMs = 1_000,
      maxDelayMs = 10_000,
      safeMethodsOnly = true,
    } = options

    // ── Reactive state ────────────────────────────────────────────
    const state = reactive<ApiResilienceState>({
      isReachable: true,
      consecutiveFailures: 0,
      lastSuccessAt: null,
      isRetrying: false,
    })

    const readonlyState = readonly(state)

    // Options API: this.$apiResilience in any component
    app.config.globalProperties.$apiResilience = readonlyState

    // Composition API: inject(API_RESILIENCE_KEY)
    app.provide(API_RESILIENCE_KEY, readonlyState)

    // ── Re-order interceptors ─────────────────────────────────────
    // The retry interceptor must run BEFORE the auth/formatting
    // interceptor in client.ts so it receives raw AxiosErrors with
    // access to error.config and error.code. We eject the existing
    // interceptor by its exported ID, register the retry interceptor
    // first, then re-register the original using the exported
    // callback functions (no undocumented Axios internals needed).
    apiClient.interceptors.response.eject(_responseInterceptorId)

    // ── 1. Retry interceptor (runs first) ─────────────────────────
    apiClient.interceptors.response.use(
      (response) => {
        // Any successful response means the backend is reachable
        if (!state.isReachable || state.consecutiveFailures > 0) {
          state.isReachable = true
          state.consecutiveFailures = 0
        }
        state.lastSuccessAt = Date.now()
        return response
      },
      async (error: AxiosError) => {
        const config = error.config as RetryableConfig | undefined
        if (!config) throw error

        const retryCount = config.__retryCount ?? 0
        const canRetry =
          config.__retryable !== false &&
          retryCount < maxRetries &&
          isRetryableError(error) &&
          isSafeMethod(config, safeMethodsOnly)

        if (!canRetry) {
          // Track reachability on terminal network errors
          if (isNetworkError(error)) {
            state.consecutiveFailures += 1
            if (state.consecutiveFailures >= 2) {
              state.isReachable = false
            }
          }
          throw error
        }

        // Exponential backoff with jitter
        const attempt = retryCount + 1
        const delayMs = computeDelay(retryCount, baseDelayMs, maxDelayMs)

        state.isRetrying = true
        await sleep(delayMs)

        // __retryCount is preserved by Axios mergeConfig (it copies
        // unknown keys via defaultToConfig2), so recursive calls to
        // this interceptor see the updated count.
        config.__retryCount = attempt

        try {
          const result = await apiClient.request(config)
          state.isRetrying = false
          return result
        } catch (retryError) {
          state.isRetrying = false
          throw retryError
        }
      },
    )

    // ── 2. Re-register original auth/formatting interceptor ───────
    apiClient.interceptors.response.use(
      _responseInterceptorFulfilled,
      _responseInterceptorRejected,
    )
  },
}

export default apiResiliencePlugin
