import { ref, computed, onUnmounted, readonly, getCurrentInstance, type ComputedRef, type Ref } from 'vue';

/**
 * Circuit Breaker pattern implementation for resilient streaming connections.
 *
 * States:
 * - CLOSED: Normal operation, all requests pass through
 * - OPEN: All requests fail immediately, waiting for reset timeout
 * - HALF_OPEN: Limited probe requests allowed to test if service recovered
 */

export type CircuitState = 'closed' | 'open' | 'half-open';

export interface CircuitBreakerConfig {
  /** Number of consecutive failures before opening circuit (default: 5) */
  failureThreshold: number;
  /** Time in ms before attempting to close circuit after opening (default: 30000) */
  resetTimeoutMs: number;
  /** Number of successful probes in half-open before closing (default: 2) */
  halfOpenSuccessThreshold: number;
  /** Time window in ms for counting failures (default: 60000) */
  failureWindowMs: number;
  /** Optional async probe executed in half-open state before accepting traffic */
  healthProbe?: () => Promise<boolean>;
  /** Timeout for half-open probe in ms (default: 5000) */
  halfOpenProbeTimeoutMs: number;
  /** Callback when circuit opens */
  onOpen?: () => void;
  /** Callback when circuit closes */
  onClose?: () => void;
  /** Callback when circuit enters half-open */
  onHalfOpen?: () => void;
}

export interface CircuitBreakerInstance {
  /** Current circuit state */
  state: Readonly<Ref<CircuitState>>;
  /** Number of consecutive failures */
  failureCount: Readonly<Ref<number>>;
  /** Whether requests are allowed to proceed */
  isRequestAllowed: ComputedRef<boolean>;
  /** Whether circuit is currently open (blocking all requests) */
  isOpen: ComputedRef<boolean>;
  /** Time remaining in ms until circuit resets (0 if not open) */
  resetTimeRemaining: Readonly<Ref<number>>;
  /** Record a successful operation */
  recordSuccess: () => void;
  /** Record a failed operation */
  recordFailure: () => void;
  /** Force open the circuit (e.g., after detecting unrecoverable error) */
  forceOpen: () => void;
  /** Force close the circuit (e.g., after user manually refreshes) */
  forceClose: () => void;
  /** Reset all state */
  reset: () => void;
}

const DEFAULT_CONFIG: CircuitBreakerConfig = {
  failureThreshold: 5,
  resetTimeoutMs: 30000,
  halfOpenSuccessThreshold: 2,
  failureWindowMs: 60000,
  halfOpenProbeTimeoutMs: 5000,
};

/**
 * Create a circuit breaker instance.
 *
 * @param config - Circuit breaker configuration
 * @returns Circuit breaker instance
 *
 * @example
 * ```typescript
 * const circuit = useCircuitBreaker({
 *   failureThreshold: 5,
 *   resetTimeoutMs: 30000,
 * });
 *
 * if (circuit.isRequestAllowed.value) {
 *   try {
 *     await makeRequest();
 *     circuit.recordSuccess();
 *   } catch (error) {
 *     circuit.recordFailure();
 *   }
 * } else {
 *   showFallbackUI();
 * }
 * ```
 */
export function useCircuitBreaker(config: Partial<CircuitBreakerConfig> = {}): CircuitBreakerInstance {
  const finalConfig: CircuitBreakerConfig = { ...DEFAULT_CONFIG, ...config };

  // State
  const state = ref<CircuitState>('closed');
  const failureCount = ref(0);
  const halfOpenSuccessCount = ref(0);
  const resetTimeRemaining = ref(0);
  const lastFailureTime = ref(0);

  // Failure tracking within window
  const recentFailures = ref<number[]>([]);

  // Timer references
  let resetTimer: ReturnType<typeof setTimeout> | null = null;
  let countdownInterval: ReturnType<typeof setInterval> | null = null;
  let resetStartTime = 0;
  let probeInFlight = false;

  const cleanupTimers = () => {
    if (resetTimer) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    if (countdownInterval) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }
  };

  const pruneOldFailures = () => {
    const cutoff = Date.now() - finalConfig.failureWindowMs;
    recentFailures.value = recentFailures.value.filter((t) => t > cutoff);
  };

  // Computed
  const isRequestAllowed = computed(() => {
    if (state.value === 'closed') return true;
    if (state.value === 'open') return false;
    // half-open: allow limited requests
    return true;
  });

  const isOpen = computed(() => state.value === 'open');

  // Actions
  const recordSuccess = () => {
    if (state.value === 'half-open') {
      halfOpenSuccessCount.value += 1;
      if (halfOpenSuccessCount.value >= finalConfig.halfOpenSuccessThreshold) {
        closeCircuit();
      }
    } else if (state.value === 'closed') {
      // Reset failure count on success in closed state
      failureCount.value = 0;
      pruneOldFailures();
    }
  };

  const recordFailure = () => {
    const now = Date.now();
    lastFailureTime.value = now;
    recentFailures.value.push(now);
    pruneOldFailures();

    if (state.value === 'half-open') {
      // Failure during half-open -> back to open
      openCircuit();
      return;
    }

    if (state.value === 'closed') {
      failureCount.value += 1;

      // Check if we've exceeded threshold
      const failCount = recentFailures.value.length;
      if (failCount >= finalConfig.failureThreshold) {
        openCircuit();
      }
    }
  };

  const openCircuit = () => {
    cleanupTimers();
    state.value = 'open';
    halfOpenSuccessCount.value = 0;
    resetStartTime = Date.now();
    resetTimeRemaining.value = finalConfig.resetTimeoutMs;

    finalConfig.onOpen?.();

    // Set up reset timer
    resetTimer = setTimeout(() => {
      enterHalfOpen();
    }, finalConfig.resetTimeoutMs);

    // Set up countdown interval
    countdownInterval = setInterval(() => {
      const elapsed = Date.now() - resetStartTime;
      const remaining = Math.max(0, finalConfig.resetTimeoutMs - elapsed);
      resetTimeRemaining.value = remaining;
    }, 1000);
  };

  const enterHalfOpen = () => {
    cleanupTimers();
    state.value = 'half-open';
    halfOpenSuccessCount.value = 0;
    resetTimeRemaining.value = 0;
    probeInFlight = false;

    finalConfig.onHalfOpen?.();
    void runHalfOpenProbe();
  };

  const closeCircuit = () => {
    cleanupTimers();
    state.value = 'closed';
    failureCount.value = 0;
    halfOpenSuccessCount.value = 0;
    resetTimeRemaining.value = 0;
    recentFailures.value = [];
    probeInFlight = false;

    finalConfig.onClose?.();
  };

  const forceOpen = () => {
    openCircuit();
  };

  const forceClose = () => {
    closeCircuit();
  };

  const reset = () => {
    cleanupTimers();
    state.value = 'closed';
    failureCount.value = 0;
    halfOpenSuccessCount.value = 0;
    resetTimeRemaining.value = 0;
    lastFailureTime.value = 0;
    recentFailures.value = [];
    probeInFlight = false;
  };

  const runHalfOpenProbe = async () => {
    if (!finalConfig.healthProbe || state.value !== 'half-open' || probeInFlight) {
      return;
    }
    probeInFlight = true;
    try {
      const probeTimeoutMs = Math.max(100, finalConfig.halfOpenProbeTimeoutMs);
      const result = await Promise.race<boolean>([
        finalConfig.healthProbe(),
        new Promise<boolean>((resolve) => {
          setTimeout(() => resolve(false), probeTimeoutMs);
        }),
      ]);
      if (state.value !== 'half-open') {
        return;
      }
      if (result) {
        closeCircuit();
      } else {
        openCircuit();
      }
    } catch {
      if (state.value === 'half-open') {
        openCircuit();
      }
    } finally {
      probeInFlight = false;
    }
  };

  // Cleanup on unmount when created in component setup.
  // Global singletons can be created outside setup; avoid lifecycle warnings there.
  if (getCurrentInstance()) {
    onUnmounted(() => {
      cleanupTimers();
    });
  }

  return {
    state: readonly(state),
    failureCount: readonly(failureCount),
    isRequestAllowed,
    isOpen,
    resetTimeRemaining: readonly(resetTimeRemaining),
    recordSuccess,
    recordFailure,
    forceOpen,
    forceClose,
    reset,
  };
}

/**
 * Global SSE circuit breaker singleton.
 * Used to coordinate streaming reconnection attempts across the app.
 */
let globalSseCircuitBreaker: CircuitBreakerInstance | null = null;

function getSseHealthProbeUrl(): string {
  const host = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');
  return host ? `${host}/api/v1/health` : '/api/v1/health';
}

export function getSseCircuitBreaker(): CircuitBreakerInstance {
  if (!globalSseCircuitBreaker) {
    globalSseCircuitBreaker = useCircuitBreaker({
      failureThreshold: 5,
      resetTimeoutMs: 30000,
      halfOpenSuccessThreshold: 2,
      failureWindowMs: 60000,
      halfOpenProbeTimeoutMs: 5000,
      healthProbe: async () => {
        if (typeof fetch === 'undefined') {
          return true;
        }
        const abortController = typeof AbortController !== 'undefined' ? new AbortController() : null;
        const timeoutHandle = setTimeout(() => {
          abortController?.abort();
        }, 4000);
        try {
          const response = await fetch(getSseHealthProbeUrl(), {
            method: 'GET',
            cache: 'no-store',
            headers: { Accept: 'application/json' },
            signal: abortController?.signal,
          });
          return response.ok;
        } catch {
          // Treat transport-level probe failures as inconclusive so the
          // next real SSE reconnection can serve as the half-open probe.
          return true;
        } finally {
          clearTimeout(timeoutHandle);
        }
      },
    });
  }
  return globalSseCircuitBreaker;
}

export function resetSseCircuitBreaker(): void {
  if (globalSseCircuitBreaker) {
    globalSseCircuitBreaker.reset();
  }
}
