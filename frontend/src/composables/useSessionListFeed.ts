import { onMounted, onUnmounted, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';

import { getSessions, getSessionsSSE } from '@/api/agent';
import { useSessionStatus } from '@/composables/useSessionStatus';
import { useAuthStore } from '@/stores/authStore';
import type { ListSessionItem } from '@/types/response';

interface SessionListFeedOptions {
  initialFetch?: boolean;
  fallbackPollIntervalMs?: number;
}

const DEFAULT_FALLBACK_POLL_INTERVAL_MS = 10_000;

export function useSessionListFeed(options: SessionListFeedOptions = {}) {
  const {
    initialFetch = true,
    fallbackPollIntervalMs = DEFAULT_FALLBACK_POLL_INTERVAL_MS,
  } = options;

  const { isAuthenticated } = storeToRefs(useAuthStore());

  const sessions = ref<ListSessionItem[]>([]);
  const isLoading = ref<boolean>(initialFetch);
  const isConnected = ref(false);

  let cancelGetSessionsSSE: (() => void) | null = null;
  let fallbackPollTimer: ReturnType<typeof setInterval> | null = null;

  const stopFallbackPolling = () => {
    if (!fallbackPollTimer) return;
    clearInterval(fallbackPollTimer);
    fallbackPollTimer = null;
  };

  let fetchingInProgress = false;

  const fetchSessions = async (showLoading = false) => {
    if (!isAuthenticated.value) return;
    if (fetchingInProgress) return;
    fetchingInProgress = true;
    if (showLoading || sessions.value.length === 0) {
      isLoading.value = true;
    }
    try {
      const response = await getSessions();
      sessions.value = response.sessions;
    } catch {
      // Non-blocking: retain last known sessions, retry via SSE/polling.
    } finally {
      fetchingInProgress = false;
      isLoading.value = false;
    }
  };

  const startFallbackPolling = () => {
    if (fallbackPollTimer || !isAuthenticated.value) return;
    fallbackPollTimer = setInterval(() => {
      void fetchSessions();
    }, fallbackPollIntervalMs);
  };

  const disconnectSSE = () => {
    if (!cancelGetSessionsSSE) return;
    cancelGetSessionsSSE();
    cancelGetSessionsSSE = null;
  };

  let sseConnecting = false;

  const connectSSE = async () => {
    if (!isAuthenticated.value) return;
    if (sseConnecting) return;
    sseConnecting = true;
    disconnectSSE();
    stopFallbackPolling();
    try {
      cancelGetSessionsSSE = await getSessionsSSE({
        onOpen: () => {
          sseConnecting = false;
          isConnected.value = true;
          stopFallbackPolling();
        },
        onMessage: (event) => {
          sessions.value = event.data.sessions;
          isConnected.value = true;
          isLoading.value = false;
          stopFallbackPolling();
        },
        onError: () => {
          sseConnecting = false;
          isConnected.value = false;
          startFallbackPolling();
        },
        onClose: (info) => {
          sseConnecting = false;
          if (info.willRetry) return;
          isConnected.value = false;
          startFallbackPolling();
        },
      });
    } catch {
      sseConnecting = false;
      isConnected.value = false;
      startFallbackPolling();
      await fetchSessions(true);
    }
  };

  const { onStatusChange } = useSessionStatus();
  const unsubscribeStatusChange = onStatusChange((sessionId, status) => {
    const existing = sessions.value.find((session) => session.session_id === sessionId);
    if (!existing) return;
    sessions.value = sessions.value.map((session) =>
      session.session_id === sessionId ? { ...session, status } : session,
    );
  });

  const stopAuthWatch = watch(isAuthenticated, (authed) => {
    if (authed) {
      void fetchSessions(true);
      void connectSSE();
    } else {
      disconnectSSE();
      stopFallbackPolling();
      sessions.value = [];
    }
  });

  // Auto-reconnect SSE when user returns to the tab or comes back online.
  // HTTP/2 streams are frequently reset by proxies/load balancers while the
  // tab is backgrounded; this ensures the feed recovers without a page reload.
  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible' && !isConnected.value && isAuthenticated.value) {
      void fetchSessions();
      void connectSSE();
    }
  };

  const handleOnline = () => {
    if (!isConnected.value && isAuthenticated.value) {
      void connectSSE();
    }
  };

  onMounted(() => {
    if (initialFetch) {
      void fetchSessions(true);
    }
    void connectSSE();
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('online', handleOnline);
  });

  onUnmounted(() => {
    stopAuthWatch();
    unsubscribeStatusChange();
    disconnectSSE();
    stopFallbackPolling();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    window.removeEventListener('online', handleOnline);
  });

  return {
    sessions,
    isLoading,
    isConnected,
    refresh: fetchSessions,
    reconnect: connectSSE,
  };
}
