// Backend API client configuration
import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { fetchEventSource, EventSourceMessage } from '@microsoft/fetch-event-source';
import { router } from '@/main';
import { clearStoredTokens, getStoredToken, getStoredRefreshToken, storeToken } from './auth';
import { getSseDiagnosticsHeaderValue, logSseDiagnostics } from '@/utils/sseDiagnostics';

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
apiClient.interceptors.response.use(
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
  onClose?: () => void;
  onError?: (error: Error) => void;
  onRetry?: (attempt: number, maxAttempts: number) => void;
}

export interface SSEOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: Record<string, unknown>;
  headers?: Record<string, string>;
}

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
  const { onOpen, onMessage, onClose, onError, onRetry } = callbacks;
  const {
    method = 'GET',
    body,
    headers = {}
  } = options;

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

  // Track the last event_id received for reconnection resume
  let lastReceivedEventId: string | undefined = (body as { event_id?: string })?.event_id;

  // Track per-request transport attempts for diagnostics
  let connectionAttempt = 0;

  // Retry configuration
  let retryCount = 0;
  const maxRetries = 7;
  const baseDelay = 1000; // 1 second
  const maxDelay = 45000; // 45 seconds
  let reconnectTimeout: NodeJS.Timeout | null = null;

  // Calculate exponential backoff delay with 25% jitter to prevent thundering herd
  const getRetryDelay = (attempt: number): number => {
    const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
    const jitter = delay * 0.25 * Math.random();
    return delay + jitter;
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
        messageSent,
        streamCompleted,
        receivedAnyEvents,
        resumeEventId: lastReceivedEventId ?? null,
      });

      const ssePromise = fetchEventSource(apiUrl, {
        method,
        headers: headersWithLastId,
        openWhenHidden: true,
        body: requestBody,
        signal: abortController.signal,
        async onopen(response) {
          logSseDiagnostics('client', 'connect:open', {
            endpoint,
            attempt,
            status: response.status,
            ok: response.ok,
            messageSent,
            retryCount,
            resumeEventId: lastReceivedEventId ?? null,
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
                // Retry connection with new token using exponential backoff
                // Note: messageSent stays false intentionally - 401 means the server rejected
                // at auth layer and the message was NOT processed, so we need to resend it
                const retryDelay = getRetryDelay(retryCount);
                console.debug(`[SSE] Reconnecting after auth refresh in ${Math.round(retryDelay)}ms (attempt ${retryCount + 1}/${maxRetries})`);
                retryCount++;
                reconnectTimeout = setTimeout(() => createConnection().catch(console.error), retryDelay);
              }
            }
            return;
          }

          // Handle rate limiting - don't retry immediately
          if (response.status === 429) {
            console.warn('Rate limit exceeded. Waiting 60 seconds before retry...');
            // Stop retrying for rate limit - user should refresh or wait
            if (onError) {
              onError(new Error('Rate limit exceeded. Please wait a moment and try again.'));
            }
            // Abort connection to prevent retry loop
            abortController.abort();
            return;
          }

          // Handle validation errors (422) - don't retry, the request body is invalid
          if (response.status === 422) {
            console.error('Request validation failed (422). Not retrying.');
            if (onError) {
              onError(new Error('Request validation failed. Please check your input.'));
            }
            // Abort connection to prevent retry loop
            abortController.abort();
            return;
          }

          // Check for other error status codes
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          // Connection successful - mark message as sent and reset retry counter
          // Only set messageSent after server confirms receipt (200 OK)
          if (body && !messageSent) {
            messageSent = true;
          }
          retryCount = 0;
          if (onOpen) {
            onOpen();
          }
        },
        onmessage(event: EventSourceMessage) {
          receivedAnyEvents = true;
          if (event.event && event.event.trim() !== '') {
            // Track stream completion events to prevent unnecessary reconnection
            // Include error/failure events — agent errors are terminal, not retryable
            if (event.event === 'done' || event.event === 'complete' || event.event === 'end'
              || event.event === 'error' || event.event === 'agent_error' || event.event === 'session_error') {
              // #region agent log
              fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'client.ts:onmessage',message:'Stream completion event received',data:{eventType:event.event,eventId:event.id},timestamp:Date.now(),hypothesisId:'A,D',runId:'initial'})}).catch(()=>{});
              // #endregion
              streamCompleted = true;
            }

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
            const eventId = (parsedData as { event_id?: string })?.event_id;
            if (eventId) {
              lastReceivedEventId = eventId;
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
          // #region agent log
          fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'client.ts:onclose',message:'SSE transport closed',data:{endpoint,streamCompleted,messageSent,receivedAnyEvents,retryCount,lastReceivedEventId,willRetry:!abortController.signal.aborted && retryCount < maxRetries && !streamCompleted && !(messageSent && !receivedAnyEvents)},timestamp:Date.now(),hypothesisId:'A,D,E',runId:'initial'})}).catch(()=>{});
          // #endregion
          logSseDiagnostics('client', 'connect:close', {
            endpoint,
            attempt,
            streamCompleted,
            messageSent,
            receivedAnyEvents,
            retryCount,
            resumeEventId: lastReceivedEventId ?? null,
            willRetry: !abortController.signal.aborted && retryCount < maxRetries && !streamCompleted && !(messageSent && !receivedAnyEvents),
          });

          if (onClose) {
            onClose();
          }

          // Don't reconnect if stream completed normally (received done/complete/end event)
          // Also don't reconnect if the stream closed without any events at all — this
          // indicates the session/task already completed (not a network interruption)
          if (streamCompleted || (messageSent && !receivedAnyEvents)) {
            return;
          }

          // Attempt reconnection if not manually aborted
          if (!abortController.signal.aborted && retryCount < maxRetries) {
            const retryAttempt = retryCount + 1;
            if (onRetry) onRetry(retryAttempt, maxRetries);
            const delay = getRetryDelay(retryCount);
            logSseDiagnostics('client', 'connect:retry_scheduled_from_close', {
              endpoint,
              attempt: retryAttempt,
              maxRetries,
              delayMs: Math.round(delay),
              resumeEventId: lastReceivedEventId ?? null,
            });
            console.log(`SSE connection closed. Reconnecting in ${Math.round(delay / 1000)}s... (attempt ${retryAttempt}/${maxRetries})`);
            retryCount++;

            reconnectTimeout = setTimeout(() => {
              createConnection().catch(console.error);
            }, delay);
          } else if (retryCount >= maxRetries) {
            console.error('SSE max reconnection attempts reached. Please refresh the page.');
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

          // Attempt reconnection on network errors if not manually aborted
          if (!abortController.signal.aborted && retryCount < maxRetries) {
            const retryAttempt = retryCount + 1;
            if (onRetry) onRetry(retryAttempt, maxRetries);
            const delay = getRetryDelay(retryCount);
            logSseDiagnostics('client', 'connect:retry_scheduled_from_error', {
              endpoint,
              attempt: retryAttempt,
              maxRetries,
              delayMs: Math.round(delay),
              resumeEventId: lastReceivedEventId ?? null,
            });
            console.log(`SSE connection error. Retrying in ${Math.round(delay / 1000)}s... (attempt ${retryAttempt}/${maxRetries})`);
            retryCount++;

            reconnectTimeout = setTimeout(() => {
              createConnection().catch(console.error);
            }, delay);
          } else if (retryCount >= maxRetries) {
            console.error('SSE max reconnection attempts reached. Please refresh the page.');
            if (onError) {
              onError(new Error('Max reconnection attempts reached'));
            }
          } else if (onError) {
            onError(error);
          }

          reject(error);
        },
      });

      ssePromise.catch(reject);
    });
  };

  createConnection().catch((error) => {
    if (!abortController.signal.aborted) {
      console.error('SSE connection failed:', error);
    }
  });

  return () => {
    // Cancel any pending reconnection attempts
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    abortController.abort();
  };
}; 
