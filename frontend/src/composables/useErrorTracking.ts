import type { App } from 'vue';
import { apiClient } from '@/api/client';
import { getErrorReporter, type ErrorCategory, type ErrorSeverity } from './useErrorReporter';

/**
 * Extended category set that includes SSE, Vue, and unhandled errors
 * (superset of useErrorReporter's ErrorCategory).
 */
type TrackingCategory = ErrorCategory | 'sse' | 'vue' | 'unhandled';

interface TrackingContext {
  component?: string;
  category?: TrackingCategory;
  severity?: ErrorSeverity;
  sessionId?: string;
  details?: Record<string, unknown>;
}

interface QueuedError {
  message: string;
  category: TrackingCategory;
  severity: ErrorSeverity;
  component: string;
  url: string;
  user_agent: string;
  timestamp: number;
  session_id: string;
  details: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_BATCH_SIZE = 10;
const FLUSH_INTERVAL_MS = 30_000; // 30 seconds
const ENDPOINT = '/telemetry/frontend-errors';

// ---------------------------------------------------------------------------
// Module-level singleton state
// ---------------------------------------------------------------------------

const _queue: QueuedError[] = [];
let _flushTimer: ReturnType<typeof setInterval> | null = null;
let _installed = false;

/** Dedup key for errors within the current batch window */
const _seenKeys = new Set<string>();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stripQueryParams(url: string): string {
  try {
    const u = new URL(url, window.location.origin);
    return u.pathname;
  } catch {
    return url.split('?')[0] ?? url;
  }
}

function categorizeUnknown(error: Error): TrackingCategory {
  const msg = error.message.toLowerCase();
  if (msg.includes('sse') || msg.includes('eventsource') || msg.includes('event-source')) return 'sse';
  if (msg.includes('network') || msg.includes('fetch') || msg.includes('connection')) return 'network';
  if (msg.includes('timeout') || msg.includes('timed out')) return 'timeout';
  if (msg.includes('unauthorized') || msg.includes('forbidden') || msg.includes('401')) return 'auth';
  if (msg.includes('validation') || msg.includes('422') || msg.includes('invalid')) return 'validation';
  if (msg.includes('500') || msg.includes('502') || msg.includes('503') || msg.includes('server')) return 'server';
  return 'unknown';
}

function severityForCategory(category: TrackingCategory): ErrorSeverity {
  switch (category) {
    case 'auth':
    case 'vue':
      return 'high';
    case 'server':
    case 'sse':
      return 'medium';
    case 'network':
    case 'timeout':
      return 'low';
    default:
      return 'low';
  }
}

// ---------------------------------------------------------------------------
// Core API
// ---------------------------------------------------------------------------

/**
 * Track a single error.  The error is recorded in the local
 * `useErrorReporter` store *and* queued for backend delivery.
 */
function trackError(error: Error, context: TrackingContext = {}): void {
  const category = context.category ?? categorizeUnknown(error);
  const severity = context.severity ?? severityForCategory(category);
  const component = context.component ?? '';

  // Also feed the local sessionStorage reporter
  const reporter = getErrorReporter();
  // Map the extended category back to the ErrorCategory subset accepted by the reporter
  const reporterCategory = (['network', 'timeout', 'auth', 'validation', 'server', 'circuit_breaker', 'unknown'] as ErrorCategory[]).includes(category as ErrorCategory)
    ? (category as ErrorCategory)
    : 'unknown';
  reporter.recordError(error, {
    sessionId: context.sessionId,
    severity,
    category: reporterCategory,
    details: context.details,
  });

  // Dedup within the batch window
  const dedupKey = `${category}::${error.message}`;
  if (_seenKeys.has(dedupKey)) return;
  _seenKeys.add(dedupKey);

  const entry: QueuedError = {
    message: error.message.slice(0, 512),
    category,
    severity,
    component: component.slice(0, 64),
    url: stripQueryParams(window.location.href),
    user_agent: navigator.userAgent.slice(0, 256),
    timestamp: Date.now(),
    session_id: (context.sessionId ?? '').slice(0, 64),
    details: context.details ?? {},
  };

  _queue.push(entry);

  if (_queue.length >= MAX_BATCH_SIZE) {
    void flush();
  }
}

/**
 * Flush the current error queue to the backend.
 * Silently discards on failure (fire-and-forget).
 */
async function flush(): Promise<void> {
  if (_queue.length === 0) return;

  const batch = _queue.splice(0, MAX_BATCH_SIZE);
  _seenKeys.clear();

  try {
    await apiClient.post(ENDPOINT, { errors: batch });
  } catch {
    // Fire-and-forget — we do not re-queue to avoid infinite loops
    // if the backend itself is the source of errors.
  }
}

function _startTimer(): void {
  if (_flushTimer !== null) return;
  _flushTimer = setInterval(() => {
    void flush();
  }, FLUSH_INTERVAL_MS);
}

/**
 * Stop the periodic flush timer and send remaining queued errors.
 * Useful for cleanup in tests or before teardown.
 */
function destroy(): void {
  if (_flushTimer !== null) {
    clearInterval(_flushTimer);
    _flushTimer = null;
  }
  void flush();
}

// ---------------------------------------------------------------------------
// Vue plugin interface
// ---------------------------------------------------------------------------

/**
 * Install the error tracker as a Vue plugin.
 *
 * Hooks into `app.config.errorHandler` and the global
 * `unhandledrejection` listener.
 */
function install(app: App): void {
  if (_installed) return;
  _installed = true;

  _startTimer();

  // Wrap existing errorHandler (if any) so we don't clobber it
  const existingHandler = app.config.errorHandler;
  app.config.errorHandler = (err, instance, info) => {
    if (err instanceof Error) {
      const componentName = instance?.$options?.name ?? instance?.$options?.__name ?? '';
      trackError(err, { component: componentName, category: 'vue', details: { info } });
    }
    // Call through to the previous handler
    if (existingHandler) {
      existingHandler(err, instance, info);
    }
  };

  // Unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;

    // Skip intentional cancellations (same logic as main.ts)
    if (reason instanceof DOMException && reason.name === 'AbortError') return;
    if (reason instanceof Error && /\bCancel(?:ed|led)?\b/i.test(reason.message)) return;
    if (typeof reason === 'string' && /\bCancel(?:ed|led)?\b/i.test(reason)) return;

    const error = reason instanceof Error
      ? reason
      : new Error(String(reason ?? '(empty reason)'));

    trackError(error, { category: 'unhandled' });
  });

  // Flush remaining errors on page unload
  window.addEventListener('beforeunload', () => {
    void flush();
  });
}

// ---------------------------------------------------------------------------
// Composable export
// ---------------------------------------------------------------------------

/**
 * Composable that provides frontend error tracking.
 *
 * Batches errors and sends them to `POST /telemetry/frontend-errors`
 * for Prometheus metrics and Loki logging.
 *
 * Usage:
 * ```ts
 * // As a Vue plugin (recommended — installed once in main.ts)
 * import { useErrorTracking } from '@/composables/useErrorTracking'
 * app.use({ install: useErrorTracking().install })
 *
 * // Manually track an error anywhere
 * const { trackError } = useErrorTracking()
 * trackError(new Error('boom'), { category: 'sse', sessionId: '...' })
 * ```
 */
export function useErrorTracking() {
  return {
    trackError,
    flush,
    install,
    destroy,
  };
}
