// Backend API client configuration
import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { fetchEventSource, EventSourceMessage } from '@microsoft/fetch-event-source';
import { router } from '@/router';
import { clearStoredTokens, getStoredToken, getStoredRefreshToken, storeToken, storeRefreshToken } from './auth';
import { getSseDiagnosticsHeaderValue, logSseDiagnostics } from '@/utils/sseDiagnostics';
import { getSseCircuitBreaker } from '@/composables/useCircuitBreaker';
import { tokenExpiresIn } from '@/utils/jwt';

// API configuration
export const API_CONFIG = {
  host: import.meta.env.VITE_API_URL || '',
  version: 'v1',
  timeout: 60000, // 60s - accommodates slow networks and long-running agent tasks
};

// Complete API base URL
export const BASE_URL = API_CONFIG.host
  ? `${API_CONFIG.host}/api/${API_CONFIG.version}`
  : `/api/${API_CONFIG.version}`;

// Login page route name/path
const LOGIN_ROUTE = '/login';

// Unified response format
export interface ApiResponse<T> {
  code: number;
  msg: string;
  data: T;
}

// Error format
export interface ApiError {
  code: number;
  message: string;
  details?: unknown;
}

// Create axios instance
export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: API_CONFIG.timeout,
  headers: {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    Pragma: 'no-cache',
  },
});

// Track if we're currently refreshing token to prevent multiple concurrent requests
let isRefreshing = false;

/** Timestamp of last SSE heartbeat token refresh attempt (ms) — debounce guard */
let _lastHeartbeatRefreshMs = 0;
const _HEARTBEAT_REFRESH_DEBOUNCE_MS = 120_000; // 2 minutes between refreshes
interface QueueItem {
  resolve: (value: string | null) => void;
  reject: (reason: unknown) => void;
}

let failedQueue: QueueItem[] = [];

const buildAuthenticationRequiredError = (): ApiError => ({
  code: 401,
  message: 'Authentication required',
})

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else {
      resolve(token);
    }
  });

  failedQueue = [];
};

/**
 * Redirect to login page using Vue Router
 */
const redirectToLogin = () => {
  // Check if we're already on the login page
  if (router.currentRoute.value.path === LOGIN_ROUTE) {
    return; // Already on login page, no need to redirect
  }

  // Use Vue Router to navigate to login page (preserves Vue state)
  router.push(LOGIN_ROUTE);
};

/**
 * Common token refresh logic used by both axios interceptor and SSE connections
 */
const refreshAuthToken = async (): Promise<string | null> => {
  if (isRefreshing) {
    // If already refreshing, queue this request
    return new Promise((resolve, reject) => {
      failedQueue.push({ resolve, reject });
    });
  }

  isRefreshing = true;
  const refreshToken = getStoredRefreshToken();

  if (!refreshToken) {
    // No refresh token available, clear auth and redirect to login
    clearStoredTokens();
    delete apiClient.defaults.headers.Authorization;
    window.dispatchEvent(new CustomEvent('auth:logout'));
    redirectToLogin();
    isRefreshing = false;
    throw new Error('No refresh token available');
  }

  try {
    // Attempt to refresh token
    const response = await apiClient.post('/auth/refresh', {
      refresh_token: refreshToken
    }, {
      // Add special marker to prevent interceptor from retrying this request
      __isRefreshRequest: true
    } as AxiosRequestConfig & { __isRefreshRequest: boolean });

    if (response.data && response.data.data) {
      const newAccessToken = response.data.data.access_token;
      storeToken(newAccessToken);
      const newRefreshToken = response.data.data.refresh_token;
      if (newRefreshToken) {
        storeRefreshToken(newRefreshToken);
      }

      // Update default headers
      apiClient.defaults.headers.Authorization = `Bearer ${newAccessToken}`;

      // Process queued requests
      processQueue(null, newAccessToken);

      return newAccessToken;
    } else {
      throw new Error('Invalid refresh response');
    }
  } catch (refreshError) {
    // Refresh token failed, clear tokens and redirect to login
    clearStoredTokens();
    delete apiClient.defaults.headers.Authorization;

    processQueue(refreshError, null);

    // Emit logout event
    window.dispatchEvent(new CustomEvent('auth:logout'));

    // Redirect to login page
    redirectToLogin();

    throw refreshError;
  } finally {
    isRefreshing = false;
  }
};

const handleExpiredAuthBeforeRequest = () => {
  clearStoredTokens();
  delete apiClient.defaults.headers.Authorization;
  window.dispatchEvent(new CustomEvent('auth:logout'));
  redirectToLogin();
}

// Request interceptor — preemptively refresh expired tokens before sending
export const _requestInterceptorFulfilled = async (config: InternalAxiosRequestConfig) => {
  const reqConfig = config as InternalAxiosRequestConfig & { __isRefreshRequest?: boolean };
  // Skip for refresh requests and auth endpoints to avoid loops
  if (reqConfig.__isRefreshRequest || /\/auth\/(login|logout|register|status)/.test(reqConfig.url ?? '')) {
    const token = getStoredToken();
    if (token && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  }

  let token = getStoredToken();

  // If the access token is expired (or expires within 5s), refresh proactively.
  // If refresh is impossible or fails, stop before sending a guaranteed 401.
  if (token && tokenExpiresIn(token) < 5) {
    const refreshToken = getStoredRefreshToken();
    if (!refreshToken) {
      handleExpiredAuthBeforeRequest();
      return Promise.reject(buildAuthenticationRequiredError());
    }

    try {
      const newToken = await refreshAuthToken();
      if (newToken) {
        token = newToken;
      } else {
        handleExpiredAuthBeforeRequest();
        return Promise.reject(buildAuthenticationRequiredError());
      }
    } catch {
      return Promise.reject(buildAuthenticationRequiredError());
    }
  }

  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}

apiClient.interceptors.request.use(
  _requestInterceptorFulfilled,
  (error) => Promise.reject(error),
);

// Response interceptor callbacks — extracted as named functions so plugins
// can eject and re-register them without accessing undocumented Axios internals.
export const _responseInterceptorFulfilled = (response: import('axios').AxiosResponse) => {
  // Check backend response format
  if (response.data && typeof response.data.code === 'number') {
    // If it's a business logic error (code not 0), convert to error handling
    if (response.data.code !== 0) {
      const apiError: ApiError = {
        code: response.data.code,
        message: response.data.msg || 'Unknown error',
        details: response.data
      };
      return Promise.reject(apiError);
    }
  }
  return response;
};

export const _responseInterceptorRejected = async (error: AxiosError) => {
  const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean; __isRefreshRequest?: boolean }) | undefined;

  // Axios omits config on network errors / cancelled requests — nothing to retry
  if (!originalRequest) {
    return Promise.reject({
      code: error.response?.status || 0,
      message: error.message || 'Network error',
      details: error.response?.data,
    } satisfies ApiError);
  }

  // Skip retry logic for refresh requests to prevent infinite loops
  if (originalRequest.__isRefreshRequest) {
    const apiError: ApiError = {
      code: error.response?.status || 500,
      message: 'Token refresh failed',
      details: error.response?.data
    };
    console.error('Refresh token request failed:', apiError);
    return Promise.reject(apiError);
  }

  // Handle 401 Unauthorized errors with token refresh
  // Skip refresh for auth endpoints — a 401 on login/register means bad credentials, not an expired token
  const requestUrl = originalRequest.url ?? '';
  const isAuthEndpoint = /\/auth\/(login|logout|register)/.test(requestUrl);
  const authErrorCode = (() => {
    const payload = error.response?.data;
    if (!payload || typeof payload !== 'object') return null;
    const data = payload as Record<string, unknown>;
    const detail = data.data;
    if (!detail || typeof detail !== 'object') return null;
    const codeValue = (detail as Record<string, unknown>).code;
    return typeof codeValue === 'string' ? codeValue : null;
  })();

  const shouldAttemptRefresh = authErrorCode === null || authErrorCode === 'token_expired';
  if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
    if (!shouldAttemptRefresh) {
      clearStoredTokens();
      delete apiClient.defaults.headers.Authorization;
      window.dispatchEvent(new CustomEvent('auth:logout'));
      redirectToLogin();
      return Promise.reject({
        ...buildAuthenticationRequiredError(),
        details: error.response?.data,
      } satisfies ApiError);
    }

    originalRequest._retry = true;

    try {
      const newAccessToken = await refreshAuthToken();
      if (newAccessToken) {
        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      }
    } catch (refreshError) {
      // Token refresh failed, error already handled in refreshAuthToken
      console.error('Token refresh failed:', refreshError);
    }
  }

  // Transient backend unavailability (uvicorn --reload, slow startup, Vite proxy 504).
  const transientCfg = originalRequest as InternalAxiosRequestConfig & {
    _transientBackendRetry?: number;
  };
  const transientAttempt = transientCfg._transientBackendRetry ?? 0;
  const maxTransientRetries = 5;
  const httpMethod = (originalRequest.method ?? 'get').toLowerCase();
  const respStatus = error.response?.status;
  const isTransientStatus =
    respStatus === 502 || respStatus === 503 || respStatus === 504;
  const isNetworkNoResponse = !error.response && Boolean(error.request);
  const safeForNetworkRetry = ['get', 'head', 'options'].includes(httpMethod);
  const allowWriteRetry504 =
    ['post', 'put', 'patch', 'delete'].includes(httpMethod) && respStatus === 504;

  if (
    !originalRequest.__isRefreshRequest &&
    transientAttempt < maxTransientRetries &&
    (isTransientStatus || (isNetworkNoResponse && safeForNetworkRetry)) &&
    (safeForNetworkRetry || allowWriteRetry504)
  ) {
    transientCfg._transientBackendRetry = transientAttempt + 1;
    const delayMs = Math.min(400 * 2 ** transientAttempt, 5000);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return apiClient(originalRequest);
  }

  // Detect stale session references — emit event so composables can clean up.
  // Matches: /api/v1/sessions/<id>/... returning 404 (session deleted or server restarted).
  if (error.response?.status === 404) {
    const url = error.config?.url ?? '';
    if (/\/api\/v1\/sessions\/[^/]+/.test(url)) {
      window.dispatchEvent(new CustomEvent('session:invalidated', { detail: { url } }));
    }
  }

  const apiError: ApiError = {
    code: 500,
    message: 'Request failed',
  };

  if (error.response) {
    const status = error.response.status;
    apiError.code = status;

    // Try to extract detailed error information from response content
    if (error.response.data && typeof error.response.data === 'object') {
      const data = error.response.data as Record<string, unknown>;
      if (typeof data.code === 'number' && typeof data.msg === 'string') {
        apiError.code = data.code;
        apiError.message = data.msg;
      } else {
        apiError.message = (typeof data.message === 'string' ? data.message : null) || error.response.statusText || 'Request failed';
      }
      apiError.details = data;
    } else {
      apiError.message = error.response.statusText || 'Request failed';
    }
  } else if (error.request) {
    apiError.code = 503;
    apiError.message = 'Network error, please check your connection';
  }

  console.error('API Error:', apiError.message || JSON.stringify(apiError));
  return Promise.reject(apiError);
};

// Response interceptor, unified error handling and token refresh
// Exported for plugins that need to re-order interceptor execution (e.g. apiResilience)
export const _responseInterceptorId = apiClient.interceptors.response.use(
  _responseInterceptorFulfilled,
  _responseInterceptorRejected,
);

export interface SSECallbacks<T = unknown> {
  onOpen?: () => void;
  onMessage?: (event: { event: string; data: T }) => void;
  onClose?: (info: SSECloseInfo) => void;
  onError?: (error: Error) => void;
  onRetry?: (attempt: number, maxAttempts: number) => void;
  onGapDetected?: (info: SSEGapInfo) => void;
}

export interface SSECloseInfo {
  willRetry: boolean;
  retryAttempt: number | null;
  maxRetries: number;
  streamCompleted: boolean;
  messageSent: boolean;
  receivedAnyEvents: boolean;
  lastReceivedEventId?: string;
  retryDelayMs?: number;
  reason: 'completed' | 'no_events_after_message' | 'retrying' | 'max_retries' | 'aborted' | 'closed';
}

export interface SSERetryPolicy {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
  jitterRatio: number;
}

export interface SSEGapInfo {
  requestedEventId?: string;
  firstAvailableEventId?: string;
  checkpointEventId?: string;
}

export interface SSEOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: Record<string, unknown>;
  headers?: Record<string, string>;
  retryPolicy?: Partial<SSERetryPolicy>;
}

interface StreamEnvelope {
  event_id?: string;
  timestamp?: number;
}

interface StreamErrorEnvelope extends StreamEnvelope {
  recoverable?: boolean;
  retry_after_ms?: number;
  can_resume?: boolean;
  error_type?: string;
  error_code?: string;
  checkpoint_event_id?: string;
  details?: Record<string, unknown>;
}

const DEFAULT_SSE_RETRY_POLICY: SSERetryPolicy = {
  maxRetries: 5,
  baseDelayMs: 10000,
  maxDelayMs: 60000,
  jitterRatio: 0.2,
};

const SSE_POLICY_LIMITS = {
  minRetries: 0,
  maxRetries: 50,
  minDelayMs: 100,
  maxDelayMs: 300000,
  minJitterRatio: 0,
  maxJitterRatio: 0.5,
};

const MAX_TRACKED_EVENT_IDS = 5000;
const SSE_CONTROL_ERROR_MANUAL_RETRY = '__sse_manual_retry_scheduled__';
const SSE_CONTROL_ERROR_FATAL_STOP = '__sse_fatal_stop__';
const TERMINAL_STREAM_EVENTS = new Set(['done', 'complete', 'end', 'wait']);
const NON_MEANINGFUL_PROGRESS_PHASES = new Set(['heartbeat', 'received']);
export const AUTH_RECONNECT_JITTER_MIN_MS = 100;
export const AUTH_RECONNECT_JITTER_MAX_MS = 300;

/**
 * Creates a deduplication tracker for SSE event IDs.
 * Uses LRU-style trimming when the set exceeds maxSize.
 */
const makeEventIdTracker = (maxSize: number): ((eventId: string) => boolean) => {
  const seen = new Set<string>();
  return (eventId: string): boolean => {
    if (seen.has(eventId)) {
      return false;
    }
    seen.add(eventId);

    if (seen.size > maxSize) {
      const ids = Array.from(seen);
      seen.clear();
      const keepFrom = Math.max(0, ids.length - Math.floor(maxSize / 2));
      for (let i = keepFrom; i < ids.length; i += 1) {
        const id = ids[i];
        if (id) seen.add(id);
      }
    }

    return true;
  };
};

export const isTerminalStreamEvent = (eventName: string): boolean => {
  return TERMINAL_STREAM_EVENTS.has(eventName);
};

const hasFreshInputPayload = (payload: unknown): boolean => {
  if (!payload || typeof payload !== 'object') {
    return false;
  }

  const body = payload as Record<string, unknown>;
  const message = typeof body.message === 'string' ? body.message.trim() : '';
  const attachments = Array.isArray(body.attachments) ? body.attachments : [];
  const skills = Array.isArray(body.skills) ? body.skills : [];
  const followUp = body.follow_up;

  return message.length > 0
    || attachments.length > 0
    || skills.length > 0
    || Boolean(followUp);
};

const isMeaningfulSseEvent = (eventName: string, payload: unknown): boolean => {
  if (eventName !== 'progress') {
    return true;
  }

  const phase = (payload as { phase?: unknown })?.phase;
  if (typeof phase === 'string') {
    return !NON_MEANINGFUL_PROGRESS_PHASES.has(phase);
  }

  return true;
};

const createSseControlError = (message: string): Error => {
  const controlError = new Error(message);
  controlError.name = 'SSEControlError';
  return controlError;
};

const isSseControlError = (error: unknown, message?: string): boolean => {
  if (!(error instanceof Error) || error.name !== 'SSEControlError') {
    return false;
  }
  if (!message) {
    return true;
  }
  return error.message === message;
};

const clampNumber = (value: number, min: number, max: number): number => {
  return Math.min(max, Math.max(min, value));
};

const parseFiniteNumber = (raw: string | null): number | undefined => {
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const parseRetryAfterMs = (raw: string | null): number | undefined => {
  if (!raw) return undefined;
  const asNumber = Number(raw);
  if (Number.isFinite(asNumber)) {
    return Math.max(0, Math.round(asNumber * 1000));
  }

  const parsedDate = Date.parse(raw);
  if (!Number.isFinite(parsedDate)) return undefined;
  const delayMs = parsedDate - Date.now();
  return delayMs > 0 ? delayMs : 0;
};

const normalizeRetryPolicy = (policy: Partial<SSERetryPolicy> | undefined): SSERetryPolicy => {
  const merged: SSERetryPolicy = {
    ...DEFAULT_SSE_RETRY_POLICY,
    ...(policy || {}),
  };
  const maxRetries = clampNumber(
    Math.round(merged.maxRetries),
    SSE_POLICY_LIMITS.minRetries,
    SSE_POLICY_LIMITS.maxRetries,
  );
  const baseDelayMs = clampNumber(
    Math.round(merged.baseDelayMs),
    SSE_POLICY_LIMITS.minDelayMs,
    SSE_POLICY_LIMITS.maxDelayMs,
  );
  const maxDelayMs = clampNumber(
    Math.round(merged.maxDelayMs),
    baseDelayMs,
    SSE_POLICY_LIMITS.maxDelayMs,
  );
  const jitterRatio = clampNumber(
    merged.jitterRatio,
    SSE_POLICY_LIMITS.minJitterRatio,
    SSE_POLICY_LIMITS.maxJitterRatio,
  );
  return { maxRetries, baseDelayMs, maxDelayMs, jitterRatio };
};

const applyServerRetryHeaders = (headers: Headers, current: SSERetryPolicy): SSERetryPolicy => {
  const serverOverrides: Partial<SSERetryPolicy> = {};
  const maxRetries = parseFiniteNumber(headers.get('X-Pythinker-SSE-Retry-Max-Attempts'));
  const baseDelayMs = parseFiniteNumber(headers.get('X-Pythinker-SSE-Retry-Base-Delay-Ms'));
  const maxDelayMs = parseFiniteNumber(headers.get('X-Pythinker-SSE-Retry-Max-Delay-Ms'));
  const jitterRatio = parseFiniteNumber(headers.get('X-Pythinker-SSE-Retry-Jitter-Ratio'));

  if (maxRetries !== undefined) serverOverrides.maxRetries = maxRetries;
  if (baseDelayMs !== undefined) serverOverrides.baseDelayMs = baseDelayMs;
  if (maxDelayMs !== undefined) serverOverrides.maxDelayMs = maxDelayMs;
  if (jitterRatio !== undefined) serverOverrides.jitterRatio = jitterRatio;

  return normalizeRetryPolicy({ ...current, ...serverOverrides });
};

const computeRetryDelayMs = (
  policy: SSERetryPolicy,
  attempt: number,
  preferredDelayMs?: number,
  rng: () => number = Math.random,
): number => {
  if (preferredDelayMs !== undefined && Number.isFinite(preferredDelayMs)) {
    return clampNumber(Math.round(preferredDelayMs), 0, SSE_POLICY_LIMITS.maxDelayMs);
  }

  const safeAttempt = Number.isFinite(attempt) ? Math.max(0, Math.floor(attempt)) : 0;
  const exponentialDelay = policy.baseDelayMs * (2 ** safeAttempt);
  const cappedDelay = Math.min(exponentialDelay, policy.maxDelayMs);

  // Equal jitter keeps latency bounded and avoids reconnect stampedes.
  const jitterWindow = cappedDelay * policy.jitterRatio;
  const minDelay = cappedDelay - jitterWindow;
  const jitteredDelay = minDelay + (rng() * jitterWindow);

  return Math.max(0, Math.round(jitteredDelay));
};

export const computeAuthReconnectJitterMs = (rng: () => number = Math.random): number => {
  const minDelay = AUTH_RECONNECT_JITTER_MIN_MS;
  const maxDelay = AUTH_RECONNECT_JITTER_MAX_MS;
  const span = Math.max(0, maxDelay - minDelay);
  const randomUnit = Math.min(1, Math.max(0, rng()));
  return minDelay + Math.round(span * randomUnit);
};

const isRetriableHttpStatus = (status: number): boolean => {
  return status === 408 || status === 409 || status === 425 || status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
};

/**
 * Handle SSE authentication errors and attempt token refresh
 */
const handleSSEAuthError = async <T = unknown>(
  _error: Error,
  _endpoint: string,
  _options: SSEOptions,
  callbacks: SSECallbacks<T>
): Promise<boolean> => {
  try {
    const newAccessToken = await refreshAuthToken();
    if (newAccessToken) {
      // Emit event for token refresh success
      window.dispatchEvent(new CustomEvent('auth:token-refreshed'));
      if (import.meta.env.DEV) console.log('Token refreshed for SSE connection, will retry connection');
      return true; // Indicate successful refresh
    }
    return false; // No new token obtained
  } catch (refreshError) {
    // Token refresh failed, error already handled in refreshAuthToken
    console.error('SSE token refresh failed:', refreshError);
    if (callbacks.onError) {
      callbacks.onError(refreshError as Error);
    }
    return false; // Indicate failed refresh
  }
};

/**
 * Generic SSE connection function with automatic reconnection
 * @param endpoint - API endpoint (relative to BASE_URL)
 * @param options - Request options
 * @param callbacks - Event callbacks
 * @returns Function to cancel the SSE connection
 */
export const createSSEConnection = async <T = unknown>(
  endpoint: string,
  options: SSEOptions = {},
  callbacks: SSECallbacks<T> = {}
): Promise<() => void> => {
  const { onOpen, onMessage, onClose, onError, onRetry, onGapDetected } = callbacks;
  const {
    method = 'GET',
    body,
    headers = {},
    retryPolicy,
  } = options;

  // Get the global SSE circuit breaker
  const circuitBreaker = getSseCircuitBreaker();

  // Check if circuit breaker allows this request
  if (!circuitBreaker.isRequestAllowed.value) {
    const circuitState = circuitBreaker.state.value;
    const resetRemaining = circuitBreaker.resetTimeRemaining.value ?? 0;
    const reconnectDelayMs = Math.max(250, resetRemaining || 1000);
    logSseDiagnostics('client', 'connect:blocked_by_circuit_breaker', {
      endpoint,
      circuitState,
      resetRemaining,
      reconnectDelayMs,
    });
    if (onError) {
      const error = new Error(
        `Connection temporarily unavailable. Retrying in ${Math.ceil(resetRemaining / 1000)} seconds...`
      );
      onError(error);
    }
    let deferredCancel: (() => void) | null = null;
    let cancelled = false;
    const retryTimer = setTimeout(() => {
      if (cancelled) {
        return;
      }
      createSSEConnection<T>(endpoint, options, callbacks)
        .then((cancelFn) => {
          if (cancelled) {
            cancelFn();
            return;
          }
          deferredCancel = cancelFn;
        })
        .catch((error) => {
          if (!cancelled && !deferredCancel && onError && error instanceof Error) {
            onError(error);
          }
        });
    }, reconnectDelayMs);
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      if (deferredCancel) {
        deferredCancel();
      }
    };
  }

  // Create AbortController for cancellation
  const abortController = new AbortController();

  const apiUrl = `${BASE_URL}${endpoint}`;

  // Add authentication and cache-prevention headers
  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    Pragma: 'no-cache',
    ...headers,
  };

  const diagnosticsHeader = getSseDiagnosticsHeaderValue();
  if (diagnosticsHeader) {
    requestHeaders['X-Pythinker-SSE-Debug'] = diagnosticsHeader;
  }

  // Add authentication token if available
  const token = getStoredToken();
  if (token && !requestHeaders.Authorization) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  // Track if the initial message has been sent to prevent duplicate submissions on retry
  let messageSent = false;

  // Track if stream completed normally (received 'done' or 'complete' event)
  let streamCompleted = false;

  // Track whether any events were received in this connection
  let receivedAnyEvents = false;
  let receivedMeaningfulEvents = false;
  const hasFreshInput = hasFreshInputPayload(body);

  // Track the last event_id received for reconnection resume
  let lastReceivedEventId: string | undefined = (body as { event_id?: string })?.event_id;

  // Track per-request transport attempts for diagnostics
  let connectionAttempt = 0;

  // Retry configuration (can be overridden by server response headers)
  let activeRetryPolicy = normalizeRetryPolicy(retryPolicy);
  let retryCount = 0;
  let reconnectTimeout: NodeJS.Timeout | null = null;
  let onlineRetryHandler: (() => void) | null = null;
  let serverRequestedRetry = false;
  let serverRetryAfterMs: number | undefined;
  const trackEventId = makeEventIdTracker(MAX_TRACKED_EVENT_IDS);

  // Guard against dual reconnection when both onclose and onerror fire
  // for the same disconnect event (fetch-event-source can call both)
  let isDisconnectHandled = false;

  const clearReconnectTimeout = () => {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
  };

  const clearOnlineRetryHandler = () => {
    if (onlineRetryHandler && typeof window !== 'undefined') {
      window.removeEventListener('online', onlineRetryHandler);
      onlineRetryHandler = null;
    }
  };

  const scheduleReconnect = (
    source: 'close' | 'error' | 'http_status' | 'auth_refresh' | 'promise_rejection',
    preferredDelayMs?: number,
  ): boolean => {
    if (abortController.signal.aborted) {
      return false;
    }
    if (retryCount >= activeRetryPolicy.maxRetries) {
      return false;
    }
    if (reconnectTimeout || onlineRetryHandler) {
      return true;
    }

    const nextAttempt = retryCount + 1;
    const delayMs = computeRetryDelayMs(activeRetryPolicy, retryCount, preferredDelayMs);

    if (onRetry) {
      onRetry(nextAttempt, activeRetryPolicy.maxRetries);
    }

    logSseDiagnostics('client', 'connect:retry_scheduled', {
      endpoint,
      source,
      attempt: nextAttempt,
      maxRetries: activeRetryPolicy.maxRetries,
      delayMs,
      resumeEventId: lastReceivedEventId ?? null,
    });

    retryCount += 1;

    const performRetry = () => {
      createConnection().catch((error) => {
        if (!abortController.signal.aborted) {
          console.error('SSE reconnect attempt failed:', error);
        }
      });
    };

    if (typeof navigator !== 'undefined' && navigator.onLine === false && typeof window !== 'undefined') {
      onlineRetryHandler = () => {
        clearOnlineRetryHandler();
        reconnectTimeout = setTimeout(() => {
          reconnectTimeout = null;
          performRetry();
        }, Math.min(delayMs, 1000));
      };
      window.addEventListener('online', onlineRetryHandler);
      return true;
    }

    reconnectTimeout = setTimeout(() => {
      reconnectTimeout = null;
      performRetry();
    }, delayMs);
    return true;
  };

  // Create SSE connection with retry logic
  const createConnection = async (): Promise<void> => {
    return new Promise((_resolve, reject) => {
      connectionAttempt += 1;
      const attempt = connectionAttempt;

      if (abortController.signal.aborted) {
        reject(new Error('Connection aborted'));
        return;
      }

      // Include body on first attempt OR if previous attempt failed before server acknowledged
      // Only skip body on retry after successful connection (e.g., 401 auth refresh, stream disconnect)
      // Always send at least an empty object for POST requests to avoid 422 validation errors
      // IMPORTANT: On reconnection, include event_id to resume from where we left off (prevents duplicate events)
      let requestBody: string | undefined;
      if (!messageSent && body) {
        // First attempt: send full body with message
        requestBody = JSON.stringify(body);
      } else if (method === 'POST') {
        // Reconnection: preserve original body context (skills, attachments, thinking_mode)
        // but strip the message to prevent duplicate prompt submission.
        // Update event_id to resume from last received position.
        const resumeBody: Record<string, unknown> = body ? { ...body } : {};
        delete resumeBody.message;
        resumeBody.event_id = lastReceivedEventId;
        requestBody = JSON.stringify(resumeBody);
      }

      // SSE best practice: Last-Event-ID for reconnection resumption (set per-request for retries)
      const headersWithLastId = { ...requestHeaders };
      if (lastReceivedEventId && !headersWithLastId['Last-Event-ID']) {
        headersWithLastId['Last-Event-ID'] = lastReceivedEventId;
      }

      logSseDiagnostics('client', 'connect:start', {
        endpoint,
        method,
        attempt,
        retryCount,
        maxRetries: activeRetryPolicy.maxRetries,
        messageSent,
        streamCompleted,
        receivedAnyEvents,
        resumeEventId: lastReceivedEventId ?? null,
      });

      // Reset all per-attempt state immediately before starting the connection.
      // Groups event tracking flags with the disconnect guard so reconnect
      // handlers evaluate correctly against the new attempt's state.
      receivedAnyEvents = false;
      receivedMeaningfulEvents = false;
      isDisconnectHandled = false;

      const ssePromise = fetchEventSource(apiUrl, {
        method,
        headers: headersWithLastId,
        openWhenHidden: true,
        body: requestBody,
        signal: abortController.signal,
        async onopen(response) {
          activeRetryPolicy = applyServerRetryHeaders(response.headers, activeRetryPolicy);

          logSseDiagnostics('client', 'connect:open', {
            endpoint,
            attempt,
            status: response.status,
            ok: response.ok,
            messageSent,
            retryCount,
            maxRetries: activeRetryPolicy.maxRetries,
            retryPolicy: activeRetryPolicy,
            resumeEventId: lastReceivedEventId ?? null,
            protocolVersion: response.headers.get('X-Pythinker-SSE-Protocol-Version'),
            heartbeatSeconds: response.headers.get('X-Pythinker-SSE-Heartbeat-Interval-Seconds'),
          });

          // Check for authentication errors in the initial response
          if (response.status === 401) {
            const authError = new Error('Unauthorized');
            const refreshSuccess = await handleSSEAuthError(authError, endpoint, options, callbacks);

            if (refreshSuccess) {
              // Update authorization header with new token
              const newToken = getStoredToken();
              if (newToken) {
                requestHeaders.Authorization = `Bearer ${newToken}`;
                // Retry connection with new token.
                // Note: messageSent stays false intentionally - 401 means the server rejected
                // at auth layer and the message was NOT processed, so we need to resend it
                scheduleReconnect('auth_refresh', computeAuthReconnectJitterMs());
                throw createSseControlError(SSE_CONTROL_ERROR_MANUAL_RETRY);
              }
            } else {
              abortController.abort();
              throw createSseControlError(SSE_CONTROL_ERROR_FATAL_STOP);
            }
          }

          if (!response.ok) {
            const statusError = new Error(`HTTP ${response.status}: ${response.statusText}`);
            const retryAfterMs = parseRetryAfterMs(response.headers.get('Retry-After'));
            if (isRetriableHttpStatus(response.status)) {
              const scheduled = scheduleReconnect('http_status', retryAfterMs);
              if (!scheduled && onError) {
                onError(statusError);
              }
              if (scheduled) {
                throw createSseControlError(SSE_CONTROL_ERROR_MANUAL_RETRY);
              }
              throw createSseControlError(SSE_CONTROL_ERROR_FATAL_STOP);
            }

            if (onError) {
              onError(statusError);
            }
            abortController.abort();
            throw createSseControlError(SSE_CONTROL_ERROR_FATAL_STOP);
          }

          // Connection successful - mark message as sent and reset retry counter
          // Only set messageSent after server confirms receipt (200 OK)
          if (hasFreshInput && !messageSent) {
            messageSent = true;
          }
          retryCount = 0;
          serverRequestedRetry = false;
          serverRetryAfterMs = undefined;

          // Record successful connection for circuit breaker
          circuitBreaker.recordSuccess();

          if (onOpen) {
            onOpen();
          }
        },
        onmessage(event: EventSourceMessage) {
          if (event.event && event.event.trim() !== '') {
            // Parse event data and extract event_id for reconnection resume.
            // Guard against malformed payloads so a single bad frame does not
            // crash the entire stream handler and force a reconnect cycle.
            let parsedData: T;
            try {
              parsedData = JSON.parse(event.data) as T;
            } catch {
              console.warn('SSE: failed to parse event data, skipping frame', event.event);
              return;
            }
            receivedAnyEvents = true;
            if (isMeaningfulSseEvent(event.event, parsedData)) {
              receivedMeaningfulEvents = true;
            }

            const envelope = parsedData as StreamEnvelope;
            const payloadEventId = envelope.event_id;
            const sseId = event.id;

            // Prefer the SSE transport-level id (Redis stream format "12345-0")
            // over the JSON payload's event_id (UUID format).
            // For dedup we use whichever ID is available; for the resume cursor
            // (Last-Event-ID) we ONLY store Redis stream IDs so the backend can
            // read directly from that position without a format mismatch.
            const eventId = sseId || payloadEventId;
            if (eventId) {
              const isUniqueEvent = trackEventId(eventId);
              if (!isUniqueEvent) {
                logSseDiagnostics('client', 'event:duplicate_skipped', {
                  endpoint,
                  attempt,
                  event: event.event,
                  eventId,
                });
                return;
              }
              // Only use Redis stream IDs (format: "digits-digits") as the resume
              // cursor.  UUID/synthetic IDs cause a format mismatch on the backend
              // which disables skip mode and forces full event replay on reconnect.
              if (sseId && /^\d+-\d+$/.test(sseId)) {
                lastReceivedEventId = sseId;
              }
            }

            if (isTerminalStreamEvent(event.event)) {
              streamCompleted = true;
              serverRequestedRetry = false;
              serverRetryAfterMs = undefined;
            }

            if (event.event === 'error' || event.event === 'agent_error' || event.event === 'session_error') {
              const streamError = parsedData as StreamErrorEnvelope;
              const recoverable = Boolean(streamError.recoverable);
              const retryAfterMs = typeof streamError.retry_after_ms === 'number'
                ? clampNumber(Math.round(streamError.retry_after_ms), 0, SSE_POLICY_LIMITS.maxDelayMs)
                : undefined;

              serverRequestedRetry = recoverable;
              serverRetryAfterMs = retryAfterMs;
              if (!recoverable) {
                streamCompleted = true;
              }

              if (streamError.error_code === 'stream_gap_detected') {
                const details = streamError.details ?? {};
                const requestedEventId = typeof details.requested_event_id === 'string'
                  ? details.requested_event_id
                  : undefined;
                const firstAvailableEventId = typeof details.first_available_event_id === 'string'
                  ? details.first_available_event_id
                  : undefined;
                const checkpointEventId = streamError.checkpoint_event_id || firstAvailableEventId;
                // Only use Redis stream IDs (format: "digits-digits") as the resume
                // cursor.  UUID checkpoint IDs from gap warnings would cause a format
                // mismatch on the backend, forcing full event replay on reconnect.
                if (checkpointEventId && /^\d+-\d+$/.test(checkpointEventId)) {
                  lastReceivedEventId = checkpointEventId;
                }
                if (onGapDetected) {
                  onGapDetected({
                    requestedEventId,
                    firstAvailableEventId,
                    checkpointEventId,
                  });
                }
              }
            }

            logSseDiagnostics('client', 'event:message', {
              endpoint,
              attempt,
              event: event.event,
              eventId: eventId ?? null,
              streamCompleted,
            });

            // Handle heartbeat events silently (update lastEventTime via custom event)
            // Heartbeat events are keep-alive signals that don't require UI updates
            if (event.event === 'progress') {
              const progressData = parsedData as { phase?: string; token_expires_at?: number };
              if (progressData.phase === 'heartbeat') {
                // Check if token is nearing expiry (within 10 minutes)
                if (typeof progressData.token_expires_at === 'number') {
                  const secondsUntilExpiry = progressData.token_expires_at - Math.floor(Date.now() / 1000);
                  const now = Date.now();
                  if (
                    secondsUntilExpiry > 0 &&
                    secondsUntilExpiry <= 600 &&
                    !isRefreshing &&
                    now - _lastHeartbeatRefreshMs > _HEARTBEAT_REFRESH_DEBOUNCE_MS
                  ) {
                    // Token expires within 10 minutes — trigger proactive refresh (debounced)
                    _lastHeartbeatRefreshMs = now;
                    refreshAuthToken().then((newToken) => {
                      if (newToken) {
                        requestHeaders.Authorization = `Bearer ${newToken}`;
                      }
                    }).catch(() => {
                      // Refresh failed — will be handled by 401 interceptor on next request
                    });
                  }
                }
                // Emit custom event for heartbeat tracking without UI notification
                window.dispatchEvent(new CustomEvent('sse:heartbeat', { detail: { eventId } }));
                // Don't pass heartbeat to onMessage callback - it's silent
                return;
              }
            }

            if (onMessage) {
              onMessage({
                event: event.event,
                data: parsedData
              });
            }
          }
        },
        onclose() {
          // Guard against dual reconnection: both onclose and onerror can fire
          // for the same disconnect. Only handle once per connection.
          if (isDisconnectHandled) {
            logSseDiagnostics('client', 'connect:close_skipped', {
              endpoint,
              attempt,
              reason: 'already_handled_by_onerror',
            });
            return;
          }
          isDisconnectHandled = true;

          const noEventsAfterMessage = messageSent && !receivedMeaningfulEvents;
          const noEventsOnResume = !hasFreshInput && receivedAnyEvents && !receivedMeaningfulEvents;
          // Zero events on a resume means the session is already done — not a network issue
          const noEventsAtAllOnResume = !hasFreshInput && !messageSent && !receivedAnyEvents;
          const reachedMaxRetries = retryCount >= activeRetryPolicy.maxRetries;
          const willRetry = !abortController.signal.aborted
            && !reachedMaxRetries
            && !streamCompleted
            && !noEventsOnResume
            && !noEventsAtAllOnResume
            && (!noEventsAfterMessage || serverRequestedRetry);
          const retryAttempt = willRetry ? retryCount + 1 : null;
          const retryDelayMs = willRetry
            ? computeRetryDelayMs(activeRetryPolicy, retryCount, serverRetryAfterMs)
            : undefined;
          let reason: SSECloseInfo['reason'] = 'closed';
          if (streamCompleted) {
            reason = 'completed';
          } else if (noEventsAfterMessage || noEventsOnResume || noEventsAtAllOnResume) {
            reason = 'no_events_after_message';
          } else if (abortController.signal.aborted) {
            reason = 'aborted';
          } else if (willRetry) {
            reason = 'retrying';
          } else if (reachedMaxRetries) {
            reason = 'max_retries';
          }

          logSseDiagnostics('client', 'connect:close', {
            endpoint,
            attempt,
            streamCompleted,
            messageSent,
            receivedAnyEvents,
            receivedMeaningfulEvents,
            noEventsAtAllOnResume,
            retryCount,
            maxRetries: activeRetryPolicy.maxRetries,
            resumeEventId: lastReceivedEventId ?? null,
            retryDelayMs: retryDelayMs ?? null,
            willRetry,
            reason,
          });

          if (onClose) {
            onClose({
              willRetry,
              retryAttempt,
              maxRetries: activeRetryPolicy.maxRetries,
              streamCompleted,
              messageSent,
              receivedAnyEvents,
              lastReceivedEventId,
              retryDelayMs,
              reason,
            });
          }

          // Don't reconnect if stream completed normally (received done/complete/end event)
          // Also don't reconnect if the stream closed without any events at all — this
          // indicates the session/task already completed (not a network interruption)
          if (streamCompleted || (noEventsAfterMessage && !serverRequestedRetry) || noEventsOnResume || noEventsAtAllOnResume) {
            return;
          }

          // Attempt reconnection if not manually aborted
          if (willRetry) {
            scheduleReconnect('close', serverRetryAfterMs);
          } else if (reachedMaxRetries) {
            console.error('SSE max reconnection attempts reached. Please refresh the page.');
            // Record failure for circuit breaker - max retries reached
            circuitBreaker.recordFailure();
            if (onError) {
              onError(new Error('Max reconnection attempts reached'));
            }
          }
        },
        onerror(err: unknown) {
          const error = err instanceof Error ? err : new Error(String(err));
          logSseDiagnostics('client', 'connect:error', {
            endpoint,
            attempt,
            retryCount,
            message: error.message,
            resumeEventId: lastReceivedEventId ?? null,
          });

          // Downgrade transient network errors to warn — these are expected
          // during HTTP/2 stream resets, proxy timeouts, and connectivity blips.
          const msg = error.message.toLowerCase();
          const isTransient = msg.includes('network error')
            || msg.includes('failed to fetch')
            || msg.includes('err_http2')
            || msg.includes('net::err_')
            || msg.includes('incomplete_chunked')
            || msg.includes('the operation was aborted')
            || msg.includes('connection was reset');
          if (isTransient) {
            console.warn(`SSE transient error on ${endpoint}:`, error.message);
          } else {
            console.error('EventSource error:', error);
          }

          // Guard against dual reconnection: if onclose already scheduled a reconnect,
          // don't schedule another one here. onclose will be called immediately after.
          if (isDisconnectHandled) {
            logSseDiagnostics('client', 'connect:error_skipped', {
              endpoint,
              attempt,
              reason: 'already_handled_by_onclose',
            });
            return;
          }

          const normalizedMessage = error.message.toLowerCase();
          const fatalTransportError = normalizedMessage.includes('validation failed')
            || normalizedMessage.includes('unauthorized')
            || normalizedMessage.includes('forbidden');

          if (fatalTransportError) {
            isDisconnectHandled = true;
            if (onError) onError(error);
            throw createSseControlError(SSE_CONTROL_ERROR_FATAL_STOP);
          }

          // Mark as handled before scheduling to prevent onclose from duplicating
          isDisconnectHandled = true;
          const scheduled = scheduleReconnect('error', serverRetryAfterMs);
          if (scheduled) {
            throw createSseControlError(SSE_CONTROL_ERROR_MANUAL_RETRY);
          }

          if (retryCount >= activeRetryPolicy.maxRetries) {
            console.error('SSE max reconnection attempts reached. Please refresh the page.');
            // Record failure for circuit breaker - max retries reached
            circuitBreaker.recordFailure();
            if (onError) {
              onError(new Error('Max reconnection attempts reached'));
            }
          } else if (onError) {
            onError(error);
          }

          throw createSseControlError(SSE_CONTROL_ERROR_FATAL_STOP);
        },
      });

      ssePromise.catch((err: unknown) => {
        const error = err instanceof Error ? err : new Error(String(err));

        // Control errors are expected reconnection flow — don't log as failures
        if (isSseControlError(error)) {
          return;
        }

        logSseDiagnostics('client', 'connect:promise_rejected', {
          endpoint,
          attempt,
          retryCount,
          message: error.message,
          resumeEventId: lastReceivedEventId ?? null,
        });

        if (abortController.signal.aborted) {
          return;
        }

        const scheduled = scheduleReconnect('promise_rejection', serverRetryAfterMs);
        if (scheduled) {
          return;
        }

        if (onError) {
          onError(error);
        }
        reject(error);
      });
    });
  };

  createConnection().catch((error) => {
    if (!abortController.signal.aborted) {
      console.error('SSE connection failed:', error);
    }
  });

  return () => {
    // Cancel any pending reconnection attempts
    clearReconnectTimeout();
    clearOnlineRetryHandler();
    abortController.abort();
  };
};

export interface EventSourceOptions {
  query?: Record<string, string | number | boolean | null | undefined>;
  withCredentials?: boolean;
  retryPolicy?: Partial<SSERetryPolicy>;
}

const NATIVE_EVENTSOURCE_EVENT_TYPES = [
  'message',
  'tool',
  'step',
  'error',
  'done',
  'title',
  'wait',
  'plan',
  'attachments',
  'mode_change',
  'suggestion',
  'report',
  'stream',
  'progress',
  'wide_research',
  'phase_transition',
  'checkpoint_saved',
  'skill',
  'skill_delivery',
  'skill_activation',
  'thought',
  'canvas_update',
  'workspace',
  'agent_error',
  'session_error',
  'complete',
  'end',
] as const;

const createNativeSseCloseInfo = (
  args: {
    reason: SSECloseInfo['reason'];
    willRetry: boolean;
    retryAttempt: number | null;
    maxRetries: number;
    streamCompleted: boolean;
    messageSent: boolean;
    receivedAnyEvents: boolean;
    lastReceivedEventId?: string;
    retryDelayMs?: number;
  },
): SSECloseInfo => {
  return {
    willRetry: args.willRetry,
    retryAttempt: args.retryAttempt,
    maxRetries: args.maxRetries,
    streamCompleted: args.streamCompleted,
    messageSent: args.messageSent,
    receivedAnyEvents: args.receivedAnyEvents,
    lastReceivedEventId: args.lastReceivedEventId,
    retryDelayMs: args.retryDelayMs,
    reason: args.reason,
  };
};

/**
 * Native EventSource transport for SSE GET endpoints.
 *
 * This variant is useful for reconnect/resume flows where the backend supports
 * query-based auth and resume cursor parameters.
 */
export const createEventSourceConnection = async <T = unknown>(
  endpoint: string,
  options: EventSourceOptions = {},
  callbacks: SSECallbacks<T> = {},
): Promise<() => void> => {
  const { onOpen, onMessage, onClose, onError, onRetry, onGapDetected } = callbacks;
  const { query = {}, withCredentials = false, retryPolicy } = options;

  let streamCompleted = false;
  // Native EventSource is GET-only; message submission is not applicable.
  const messageSent = false as const;
  let receivedAnyEvents = false;
  let receivedMeaningfulEvents = false;
  let retryCount = 0;
  let manuallyClosed = false;
  let lastReceivedEventId: string | undefined =
    typeof query.event_id === 'string' ? query.event_id : undefined;
  const activeRetryPolicy = normalizeRetryPolicy(retryPolicy);
  const trackEventId = makeEventIdTracker(MAX_TRACKED_EVENT_IDS);

  const queryParams = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) {
      continue;
    }
    queryParams.set(key, String(value));
  }

  // Native EventSource cannot set Authorization headers, so this transport
  // uses query-token auth for the dedicated backend endpoint.
  const token = getStoredToken();
  if (token && !queryParams.has('access_token')) {
    queryParams.set('access_token', token);
  }

  const base = `${BASE_URL}${endpoint}`;
  const url = typeof window !== 'undefined'
    ? new URL(base, window.location.origin)
    : new URL(base);
  for (const [key, value] of queryParams.entries()) {
    url.searchParams.set(key, value);
  }

  logSseDiagnostics('client', 'native_eventsource:connect:start', {
    endpoint,
    maxRetries: activeRetryPolicy.maxRetries,
    resumeEventId: lastReceivedEventId ?? null,
  });

  const source = new EventSource(url.toString(), { withCredentials });

  const closeConnection = (reason: SSECloseInfo['reason'], error?: Error) => {
    if (manuallyClosed) {
      return;
    }
    manuallyClosed = true;
    source.close();

    if (onClose) {
      onClose(
        createNativeSseCloseInfo({
          reason,
          willRetry: false,
          retryAttempt: null,
          maxRetries: activeRetryPolicy.maxRetries,
          streamCompleted,
          messageSent,
          receivedAnyEvents,
          lastReceivedEventId,
        }),
      );
    }

    if (error && onError) {
      onError(error);
    }
  };

  const handleParsedMessage = (eventName: string, rawData: string, nativeEventId?: string) => {
    let parsedData: T;
    try {
      parsedData = JSON.parse(rawData) as T;
    } catch {
      return;
    }

    receivedAnyEvents = true;
    if (isMeaningfulSseEvent(eventName, parsedData)) {
      receivedMeaningfulEvents = true;
    }

    const envelope = parsedData as StreamEnvelope;
    // Use any available event ID for deduplication, but only store
    // Redis stream IDs (format "digits-digits") as the resume cursor.
    // UUID/synthetic IDs cause a format mismatch on the backend which
    // disables skip mode and forces full event replay on reconnect.
    const eventId = nativeEventId || envelope.event_id;
    if (eventId) {
      const isUniqueEvent = trackEventId(eventId);
      if (!isUniqueEvent) {
        return;
      }
      if (/^\d+-\d+$/.test(eventId)) {
        lastReceivedEventId = eventId;
      }
    }

    if (eventName === 'progress') {
      const progressData = parsedData as { phase?: string };
      if (progressData.phase === 'heartbeat') {
        window.dispatchEvent(new CustomEvent('sse:heartbeat', { detail: { eventId } }));
        return;
      }
    }

    if (eventName === 'error' || eventName === 'agent_error' || eventName === 'session_error') {
      const streamError = parsedData as StreamErrorEnvelope;
      const recoverable = Boolean(streamError.recoverable);
      if (!recoverable) {
        streamCompleted = true;
      }

      if (streamError.error_code === 'stream_gap_detected') {
        const details = streamError.details ?? {};
        const requestedEventId = typeof details.requested_event_id === 'string'
          ? details.requested_event_id
          : undefined;
        const firstAvailableEventId = typeof details.first_available_event_id === 'string'
          ? details.first_available_event_id
          : undefined;
        const checkpointEventId = streamError.checkpoint_event_id || firstAvailableEventId;
        // Only use Redis stream IDs (format: "digits-digits") as the resume
        // cursor.  UUID checkpoint IDs cause format mismatch on the backend.
        if (checkpointEventId && /^\d+-\d+$/.test(checkpointEventId)) {
          lastReceivedEventId = checkpointEventId;
        }
        if (onGapDetected) {
          onGapDetected({
            requestedEventId,
            firstAvailableEventId,
            checkpointEventId,
          });
        }
      }

      if (!recoverable) {
        // Deliver error event to UI before closing so the banner can display
        if (onMessage) {
          onMessage({ event: eventName, data: parsedData });
        }
        closeConnection('completed');
        return;
      }
    }

    if (isTerminalStreamEvent(eventName)) {
      streamCompleted = true;
      if (onMessage) {
        onMessage({ event: eventName, data: parsedData });
      }
      closeConnection('completed');
      return;
    }

    if (onMessage) {
      onMessage({ event: eventName, data: parsedData });
    }
  };

  const handleTransportError = () => {
    if (manuallyClosed || streamCompleted) {
      return;
    }
    const noEventsOnResume = receivedAnyEvents && !receivedMeaningfulEvents;
    if (noEventsOnResume) {
      closeConnection('no_events_after_message');
      return;
    }

    // Safety: if we've received events but keep reconnecting, close the native
    // EventSource to prevent it from auto-reconnecting behind our back.
    // The browser's built-in reconnect fires independently of this handler.
    if (source.readyState !== EventSource.CLOSED) {
      source.close();
    }

    retryCount += 1;
    const willRetry = retryCount <= activeRetryPolicy.maxRetries;
    const retryDelayMs = willRetry
      ? computeRetryDelayMs(activeRetryPolicy, retryCount - 1)
      : undefined;

    if (willRetry) {
      logSseDiagnostics('client', 'native_eventsource:retrying', {
        endpoint,
        retryAttempt: retryCount,
        maxRetries: activeRetryPolicy.maxRetries,
        retryDelayMs,
        resumeEventId: lastReceivedEventId ?? null,
      });
      if (onRetry) {
        onRetry(retryCount, activeRetryPolicy.maxRetries);
      }
      if (onClose) {
        onClose(
          createNativeSseCloseInfo({
            reason: 'retrying',
            willRetry: true,
            retryAttempt: retryCount,
            maxRetries: activeRetryPolicy.maxRetries,
            streamCompleted,
            messageSent,
            receivedAnyEvents,
            lastReceivedEventId,
            retryDelayMs,
          }),
        );
      }
      return;
    }

    logSseDiagnostics('client', 'native_eventsource:max_retries', {
      endpoint,
      maxRetries: activeRetryPolicy.maxRetries,
      resumeEventId: lastReceivedEventId ?? null,
    });
    closeConnection('max_retries', new Error('Max reconnection attempts reached'));
  };

  const makeEventHandler = (eventName: string) => {
    return (event: Event) => {
      if (!(event instanceof MessageEvent)) {
        if (eventName === 'error') {
          handleTransportError();
        }
        return;
      }

      const messageEventId = event.lastEventId || undefined;
      handleParsedMessage(eventName, event.data, messageEventId);
    };
  };


  source.onopen = () => {
    retryCount = 0;
    logSseDiagnostics('client', 'native_eventsource:open', {
      endpoint,
      resumeEventId: lastReceivedEventId ?? null,
    });
    if (onOpen) {
      onOpen();
    }
  };

  for (const eventType of NATIVE_EVENTSOURCE_EVENT_TYPES) {
    source.addEventListener(eventType, makeEventHandler(eventType));
  }

  return () => {
    if (manuallyClosed) {
      return;
    }
    closeConnection(streamCompleted ? 'completed' : 'aborted');
  };
};
