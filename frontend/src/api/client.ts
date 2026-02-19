// Backend API client configuration
import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { fetchEventSource, EventSourceMessage } from '@microsoft/fetch-event-source';
import { router } from '@/main';
import { clearStoredTokens, getStoredToken, getStoredRefreshToken, storeToken } from './auth';
import { getSseDiagnosticsHeaderValue, logSseDiagnostics } from '@/utils/sseDiagnostics';
import { getSseCircuitBreaker } from '@/composables/useCircuitBreaker';

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

// Request interceptor, add authentication token
apiClient.interceptors.request.use(
  (config) => {
    // Add authentication token if available
    const token = getStoredToken();
    if (token && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Track if we're currently refreshing token to prevent multiple concurrent requests
let isRefreshing = false;
interface QueueItem {
  resolve: (value: string | null) => void;
  reject: (reason: unknown) => void;
}

let failedQueue: QueueItem[] = [];

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
  if (window.location.pathname === LOGIN_ROUTE || 
      router.currentRoute.value.path === LOGIN_ROUTE) {
    return; // Already on login page, no need to redirect
  }

  // Use Vue Router to navigate to login page
  setTimeout(() => {
    window.location.href = LOGIN_ROUTE;
  }, 100);
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

// Response interceptor, unified error handling and token refresh
// Exported for plugins that need to re-order interceptor execution (e.g. apiResilience)
export const _responseInterceptorId = apiClient.interceptors.response.use(
  (response) => {
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
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean; __isRefreshRequest?: boolean };
    
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
    if (error.response?.status === 401 && !originalRequest._retry) {
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

    console.error('API Error:', apiError);
    return Promise.reject(apiError);
  }
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
  maxRetries: 7,
  baseDelayMs: 1000,
  maxDelayMs: 45000,
  jitterRatio: 0.25,
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
      console.log('Token refreshed for SSE connection, will retry connection');
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
  const seenEventIds = new Set<string>();

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

  const trackEventId = (eventId: string): boolean => {
    if (seenEventIds.has(eventId)) {
      return false;
    }
    seenEventIds.add(eventId);

    if (seenEventIds.size > MAX_TRACKED_EVENT_IDS) {
      const ids = Array.from(seenEventIds);
      seenEventIds.clear();
      const keepFrom = Math.max(0, ids.length - Math.floor(MAX_TRACKED_EVENT_IDS / 2));
      for (let i = keepFrom; i < ids.length; i += 1) {
        const id = ids[i];
        if (id) seenEventIds.add(id);
      }
    }

    return true;
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
        // Reconnection: send only event_id to resume streaming (no message to prevent duplicate)
        requestBody = JSON.stringify({ event_id: lastReceivedEventId });
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

      // Reset disconnect handled flag for this new connection attempt
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
                scheduleReconnect('auth_refresh');
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
            const eventId = envelope.event_id;
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
              lastReceivedEventId = eventId;
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
                if (checkpointEventId) {
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
              const progressData = parsedData as { phase?: string };
              if (progressData.phase === 'heartbeat') {
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
          const reachedMaxRetries = retryCount >= activeRetryPolicy.maxRetries;
          const willRetry = !abortController.signal.aborted
            && !reachedMaxRetries
            && !streamCompleted
            && !noEventsOnResume
            && (!noEventsAfterMessage || serverRequestedRetry);
          const retryAttempt = willRetry ? retryCount + 1 : null;
          const retryDelayMs = willRetry
            ? computeRetryDelayMs(activeRetryPolicy, retryCount, serverRetryAfterMs)
            : undefined;
          let reason: SSECloseInfo['reason'] = 'closed';
          if (streamCompleted) {
            reason = 'completed';
          } else if (noEventsAfterMessage || noEventsOnResume) {
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
          if (streamCompleted || (noEventsAfterMessage && !serverRequestedRetry) || noEventsOnResume) {
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
          console.error('EventSource error:', error);

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
        if (
          isSseControlError(error, SSE_CONTROL_ERROR_MANUAL_RETRY)
          || isSseControlError(error, SSE_CONTROL_ERROR_FATAL_STOP)
        ) {
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
  'skill_delivery',
  'skill_activation',
  'thought',
  'canvas_update',
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
  const messageSent = false;
  let receivedAnyEvents = false;
  let receivedMeaningfulEvents = false;
  let retryCount = 0;
  let manuallyClosed = false;
  let lastReceivedEventId: string | undefined =
    typeof query.event_id === 'string' ? query.event_id : undefined;
  const activeRetryPolicy = normalizeRetryPolicy(retryPolicy);
  const seenEventIds = new Set<string>();

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
    const eventId = envelope.event_id || nativeEventId;
    if (eventId) {
      const isUniqueEvent = trackEventId(eventId);
      if (!isUniqueEvent) {
        return;
      }
      lastReceivedEventId = eventId;
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
        if (checkpointEventId) {
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
        closeConnection('completed');
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

  const trackEventId = (eventId: string): boolean => {
    if (seenEventIds.has(eventId)) {
      return false;
    }
    seenEventIds.add(eventId);

    if (seenEventIds.size > MAX_TRACKED_EVENT_IDS) {
      const ids = Array.from(seenEventIds);
      seenEventIds.clear();
      const keepFrom = Math.max(0, ids.length - Math.floor(MAX_TRACKED_EVENT_IDS / 2));
      for (let i = keepFrom; i < ids.length; i += 1) {
        const id = ids[i];
        if (id) seenEventIds.add(id);
      }
    }
    return true;
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
