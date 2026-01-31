/**
 * useVNCPreconnect - Pre-connect VNC for faster display
 *
 * Phase 4 enhancement: Pre-establishes VNC WebSocket connection when
 * session enters PENDING status, reducing perceived loading time.
 */
import { ref, watch, type Ref } from 'vue';
import { getVNCUrl } from '@/api/agent';
import { SessionStatus } from '@/types/response';

interface PreconnectState {
  /** Cached VNC WebSocket URL */
  cachedUrl: string | null;
  /** Whether URL has been fetched */
  isFetched: boolean;
  /** Whether RFB module has been loaded */
  isModuleLoaded: boolean;
  /** Any error during preconnect */
  error: string | null;
}

// Global RFB module cache
let RFBModulePromise: Promise<unknown> | null = null;

/**
 * Pre-load the noVNC RFB module to avoid loading delay later
 */
async function preloadRFBModule(): Promise<boolean> {
  if (RFBModulePromise) {
    await RFBModulePromise;
    return true;
  }

  RFBModulePromise = (async () => {
    try {
      // Dynamic import with type assertion for noVNC module
      const module = await import('@novnc/novnc/lib/rfb') as { default?: unknown; RFB?: unknown };
      console.log('[VNC Preconnect] RFB module loaded from npm');
      return module.default || module.RFB || module;
    } catch {
      // Fallback: module will be loaded when VNCViewer connects
      console.warn('[VNC Preconnect] npm import failed, will load on demand');
      return null;
    }
  })();

  try {
    await RFBModulePromise;
    return true;
  } catch (e) {
    console.error('[VNC Preconnect] Failed to load RFB module:', e);
    RFBModulePromise = null;
    return false;
  }
}

// Global URL cache per session
const urlCache = new Map<string, string>();

export interface UseVNCPreconnectOptions {
  /** Session ID to preconnect */
  sessionId: Ref<string | undefined>;
  /** Session status to watch */
  sessionStatus: Ref<SessionStatus | undefined>;
}

export interface UseVNCPreconnectReturn {
  /** Current preconnect state */
  state: Ref<PreconnectState>;
  /** Get cached URL for a session (returns null if not cached) */
  getCachedUrl: (sessionId: string) => string | null;
  /** Manually trigger preconnect */
  preconnect: () => Promise<void>;
  /** Check if preconnect is ready */
  isReady: Ref<boolean>;
}

/**
 * Vue composable for VNC pre-connection
 *
 * Automatically pre-fetches VNC URL and pre-loads RFB module when
 * session transitions to PENDING status, reducing subsequent connection time.
 */
export function useVNCPreconnect(options: UseVNCPreconnectOptions): UseVNCPreconnectReturn {
  const { sessionId, sessionStatus } = options;

  const state = ref<PreconnectState>({
    cachedUrl: null,
    isFetched: false,
    isModuleLoaded: false,
    error: null,
  });

  const isReady = ref(false);

  /**
   * Pre-fetch VNC URL and load module
   */
  async function preconnect(): Promise<void> {
    const sid = sessionId.value;
    if (!sid) return;

    // Check cache first
    if (urlCache.has(sid)) {
      state.value.cachedUrl = urlCache.get(sid)!;
      state.value.isFetched = true;
    }

    try {
      // Start both operations in parallel
      const urlPromise = state.value.isFetched
        ? Promise.resolve(state.value.cachedUrl)
        : getVNCUrl(sid).then(url => {
            urlCache.set(sid, url);
            state.value.cachedUrl = url;
            state.value.isFetched = true;
            console.log(`[VNC Preconnect] URL cached for session ${sid}`);
            return url;
          });

      const modulePromise = preloadRFBModule().then(loaded => {
        state.value.isModuleLoaded = loaded;
        return loaded;
      });

      await Promise.all([urlPromise, modulePromise]);

      isReady.value = state.value.isFetched && state.value.isModuleLoaded;
      console.log(`[VNC Preconnect] Ready for session ${sid}: url=${state.value.isFetched}, module=${state.value.isModuleLoaded}`);

    } catch (e) {
      const message = e instanceof Error ? e.message : 'Unknown error';
      state.value.error = message;
      console.warn('[VNC Preconnect] Error:', message);
    }
  }

  /**
   * Get cached URL for a session
   */
  function getCachedUrl(sid: string): string | null {
    return urlCache.get(sid) ?? null;
  }

  // Watch for session status changes to trigger preconnect
  watch(
    [sessionId, sessionStatus],
    ([sid, status], [oldSid]) => {
      // Trigger preconnect when:
      // 1. Session changes to PENDING status (sandbox ready)
      // 2. Or when a new session ID is set
      if (sid && (status === SessionStatus.PENDING || (sid !== oldSid && status))) {
        console.log(`[VNC Preconnect] Triggering for session ${sid} (status: ${status})`);
        preconnect();
      }
    },
    { immediate: true }
  );

  return {
    state,
    getCachedUrl,
    preconnect,
    isReady,
  };
}

/**
 * Export utility to check if URL is cached
 */
export function getPreconnectedVNCUrl(sessionId: string): string | null {
  return urlCache.get(sessionId) ?? null;
}

/**
 * Export utility to manually cache a URL
 */
export function cacheVNCUrl(sessionId: string, url: string): void {
  urlCache.set(sessionId, url);
}
