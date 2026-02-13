/**
 * useVNC - Composable for VNC connections using noVNC
 *
 * Loads noVNC directly from CDN as native ESM to avoid CommonJS/bundler issues.
 * Provides a clean, reactive interface for Vue components.
 */
import { ref, shallowRef, type Ref } from 'vue';

// Type definitions for noVNC RFB
interface RFBOptions {
  credentials?: { password?: string; username?: string; target?: string };
  shared?: boolean;
  repeaterID?: string;
  wsProtocols?: string[];
}

interface RFBInstance {
  viewOnly: boolean;
  scaleViewport: boolean;
  clipViewport: boolean;
  resizeSession: boolean;
  disconnect: () => void;
  sendCredentials: (credentials: { password?: string; username?: string }) => void;
  sendCtrlAltDel: () => void;
  focus: () => void;
  blur: () => void;
  addEventListener: (event: string, handler: (e: any) => void) => void;
  removeEventListener: (event: string, handler: (e: any) => void) => void;
}

type RFBConstructor = new (
  target: HTMLElement,
  url: string,
  options?: RFBOptions
) => RFBInstance;

// Module cache
let RFBClass: RFBConstructor | null = null;
let loadPromise: Promise<RFBConstructor> | null = null;

/**
 * Load noVNC RFB module - tries npm package first, falls back to CDN
 */
async function loadRFBModule(): Promise<RFBConstructor> {
  // Return cached module
  if (RFBClass) return RFBClass;

  // Return existing load promise to prevent duplicate loads
  if (loadPromise) return loadPromise;

  loadPromise = (async (): Promise<RFBConstructor> => {
    // Try npm package first (transformed by vite-plugin-commonjs)
    try {
      const module = await import('@novnc/novnc/lib/rfb');
      const RFB = module.default || (module as any).RFB || module;

      if (RFB && typeof RFB === 'function') {
        RFBClass = RFB as RFBConstructor;
        if (import.meta.env.DEV) {
          console.log('[VNC] RFB module loaded from npm package');
        }
        return RFBClass;
      }
    } catch (error) {
      console.warn('[VNC] Failed to load from npm package:', error);
    }

    // Fallback to CDN
    const cdnUrls = [
      'https://cdn.jsdelivr.net/gh/novnc/noVNC@v1.5.0/core/rfb.js',
      'https://cdn.jsdelivr.net/gh/novnc/noVNC@v1.4.0/core/rfb.js',
    ];

    for (const url of cdnUrls) {
      try {
        const module = await import(/* @vite-ignore */ url);
        const RFB = module.default || module.RFB;

        if (RFB && typeof RFB === 'function') {
          RFBClass = RFB as RFBConstructor;
          if (import.meta.env.DEV) {
            console.log('[VNC] RFB module loaded from CDN:', url);
          }
          return RFBClass;
        }
      } catch (error) {
        console.warn(`[VNC] Failed to load from ${url}:`, error);
      }
    }

    throw new Error('Failed to load noVNC from any source');
  })();

  return loadPromise;
}

export interface UseVNCOptions {
  viewOnly?: boolean;
  scaleViewport?: boolean;
  clipViewport?: boolean;
  maxReconnectAttempts?: number;
  reconnectDelayMs?: number;
}

export interface UseVNCReturn {
  // State
  isConnected: Ref<boolean>;
  isConnecting: Ref<boolean>;
  connectionFailed: Ref<boolean>;
  error: Ref<string | null>;

  // Actions
  connect: (container: HTMLElement, wsUrl: string) => Promise<void>;
  disconnect: () => void;
  sendCredentials: (password: string) => void;
  setViewOnly: (viewOnly: boolean) => void;

  // RFB instance (for advanced usage)
  rfb: Ref<RFBInstance | null>;
}

/**
 * Vue composable for VNC connections
 */
export function useVNC(options: UseVNCOptions = {}): UseVNCReturn {
  const {
    viewOnly = false,
    scaleViewport = true,
    clipViewport = true,
    maxReconnectAttempts = 5,
    reconnectDelayMs = 1000,
  } = options;

  // Reactive state
  const isConnected = ref(false);
  const isConnecting = ref(false);
  const connectionFailed = ref(false);
  const error = ref<string | null>(null);
  const rfb = shallowRef<RFBInstance | null>(null);

  // Internal state
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let lastContainer: HTMLElement | null = null;
  let lastWsUrl: string | null = null;

  /**
   * Clean up timers
   */
  function clearTimers() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  /**
   * Disconnect and clean up
   */
  function disconnect() {
    clearTimers();

    if (rfb.value) {
      try {
        rfb.value.disconnect();
      } catch {
        // Ignore disconnect errors
      }
      rfb.value = null;
    }

    // Clear any stale canvas elements from the container
    if (lastContainer) {
      while (lastContainer.firstChild) {
        lastContainer.removeChild(lastContainer.firstChild);
      }
    }

    isConnected.value = false;
    isConnecting.value = false;
    lastContainer = null;
    lastWsUrl = null;
    reconnectAttempts = 0;
  }

  /**
   * Schedule a reconnection attempt
   */
  function scheduleReconnect() {
    if (!lastContainer || !lastWsUrl || isConnecting.value) return;
    if (reconnectAttempts >= maxReconnectAttempts) {
      console.warn('[VNC] Max reconnect attempts reached');
      connectionFailed.value = true;
      return;
    }

    reconnectAttempts++;
    const delay = Math.min(reconnectDelayMs * reconnectAttempts, 5000);
    if (import.meta.env.DEV) {
      console.log(`[VNC] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);
    }

    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      if (lastContainer && lastWsUrl) {
        connect(lastContainer, lastWsUrl);
      }
    }, delay);
  }

  /**
   * Connect to VNC server
   */
  async function connect(container: HTMLElement, wsUrl: string): Promise<void> {
    if (isConnecting.value) return;

    // Disconnect existing connection
    if (rfb.value) {
      rfb.value.disconnect();
      rfb.value = null;
    }

    isConnecting.value = true;
    isConnected.value = false;
    connectionFailed.value = false;
    error.value = null;
    lastContainer = container;
    lastWsUrl = wsUrl;

    try {
      // Load RFB module
      const RFB = await loadRFBModule();

      // Create connection
      const instance = new RFB(container, wsUrl, {
        credentials: { password: '' },
        shared: true,
        wsProtocols: ['binary'],
      });

      // Configure display options
      instance.viewOnly = viewOnly;
      instance.scaleViewport = scaleViewport;
      instance.clipViewport = clipViewport;

      // Event handlers
      instance.addEventListener('connect', () => {
        if (import.meta.env.DEV) {
          console.log('[VNC] Connected');
        }
        isConnected.value = true;
        isConnecting.value = false;
        connectionFailed.value = false;
        reconnectAttempts = 0;

        // Re-apply scaling after connection to ensure proper sizing
        instance.scaleViewport = true;
        instance.clipViewport = true;
      });

      instance.addEventListener('disconnect', (e: any) => {
        if (import.meta.env.DEV) {
          console.log('[VNC] Disconnected', e?.detail);
        }
        isConnected.value = false;
        isConnecting.value = false;

        // Only reconnect if not a clean disconnect
        if (!e?.detail?.clean && lastContainer && lastWsUrl) {
          scheduleReconnect();
        }
      });

      instance.addEventListener('credentialsrequired', () => {
        if (import.meta.env.DEV) {
          console.log('[VNC] Credentials required');
        }
        error.value = 'Password required';
      });

      instance.addEventListener('securityfailure', (e: any) => {
        console.error('[VNC] Security failure:', e?.detail);
        error.value = e?.detail?.reason || 'Security failure';
        connectionFailed.value = true;
      });

      rfb.value = instance;

    } catch (e) {
      const message = e instanceof Error ? e.message : 'Unknown error';
      console.error('[VNC] Connection failed:', message);
      error.value = message;
      isConnecting.value = false;
      connectionFailed.value = true;
      scheduleReconnect();
    }
  }

  /**
   * Send credentials for authentication
   */
  function sendCredentials(password: string) {
    if (rfb.value) {
      rfb.value.sendCredentials({ password });
    }
  }

  /**
   * Update viewOnly mode
   */
  function setViewOnly(value: boolean) {
    if (rfb.value) {
      rfb.value.viewOnly = value;
    }
  }

  return {
    isConnected,
    isConnecting,
    connectionFailed,
    error,
    connect,
    disconnect,
    sendCredentials,
    setViewOnly,
    rfb,
  };
}
