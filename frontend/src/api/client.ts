// Backend API client configuration
import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { fetchEventSource, EventSourceMessage } from '@microsoft/fetch-event-source';
import { router } from '@/main';
import { clearStoredTokens, getStoredToken, getStoredRefreshToken, storeToken } from './auth';

// API configuration
export const API_CONFIG = {
  host: import.meta.env.VITE_API_URL || '',
  version: 'v1',
  timeout: 30000, // Request timeout in milliseconds
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
  const { onOpen, onMessage, onClose, onError } = callbacks;
  const {
    method = 'GET',
    body,
    headers = {}
  } = options;

  // Create AbortController for cancellation
  const abortController = new AbortController();

  const apiUrl = `${BASE_URL}${endpoint}`;

  // Add authentication headers
  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...headers,
  };

  // Add authentication token if available
  const token = getStoredToken();
  if (token && !requestHeaders.Authorization) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  // Track if the initial message has been sent to prevent duplicate submissions on retry
  let messageSent = false;

  // Track if stream completed normally (received 'done' or 'complete' event)
  let streamCompleted = false;

  // Track the last event_id received for reconnection resume
  let lastReceivedEventId: string | undefined = (body as { event_id?: string })?.event_id;

  // Retry configuration
  let retryCount = 0;
  const maxRetries = 5;
  const baseDelay = 1000; // 1 second
  const maxDelay = 30000; // 30 seconds
  let reconnectTimeout: NodeJS.Timeout | null = null;

  // Calculate exponential backoff delay
  const getRetryDelay = (attempt: number): number => {
    const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
    // Add jitter to prevent thundering herd
    return delay + Math.random() * 1000;
  };

  // Create SSE connection with retry logic
  const createConnection = async (): Promise<void> => {
    return new Promise((_resolve, reject) => {
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

      const ssePromise = fetchEventSource(apiUrl, {
        method,
        headers: requestHeaders,
        openWhenHidden: true,
        body: requestBody,
        signal: abortController.signal,
        async onopen(response) {
          // Check for authentication errors in the initial response
          if (response.status === 401) {
            const authError = new Error('Unauthorized');
            const refreshSuccess = await handleSSEAuthError(authError, endpoint, options, callbacks);

            if (refreshSuccess) {
              // Update authorization header with new token
              const newToken = getStoredToken();
              if (newToken) {
                requestHeaders.Authorization = `Bearer ${newToken}`;
                // Retry connection with new token
                // Note: messageSent stays false intentionally - 401 means the server rejected
                // at auth layer and the message was NOT processed, so we need to resend it
                setTimeout(() => createConnection().catch(console.error), 1000);
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
          if (event.event && event.event.trim() !== '') {
            // Track stream completion events to prevent unnecessary reconnection
            // Include error/failure events — agent errors are terminal, not retryable
            if (event.event === 'done' || event.event === 'complete' || event.event === 'end'
              || event.event === 'error' || event.event === 'agent_error' || event.event === 'session_error') {
              streamCompleted = true;
            }

            // Parse event data and extract event_id for reconnection resume
            const parsedData = JSON.parse(event.data) as T;
            const eventId = (parsedData as { event_id?: string })?.event_id;
            if (eventId) {
              lastReceivedEventId = eventId;
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
          if (onClose) {
            onClose();
          }

          // Don't reconnect if stream completed normally (received done/complete/end event)
          if (streamCompleted) {
            return;
          }

          // Attempt reconnection if not manually aborted
          if (!abortController.signal.aborted && retryCount < maxRetries) {
            const delay = getRetryDelay(retryCount);
            console.log(`SSE connection closed. Reconnecting in ${Math.round(delay / 1000)}s... (attempt ${retryCount + 1}/${maxRetries})`);
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
          console.error('EventSource error:', error);

          // Attempt reconnection on network errors if not manually aborted
          if (!abortController.signal.aborted && retryCount < maxRetries) {
            const delay = getRetryDelay(retryCount);
            console.log(`SSE connection error. Retrying in ${Math.round(delay / 1000)}s... (attempt ${retryCount + 1}/${maxRetries})`);
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