import { onMounted, onUnmounted, ref } from 'vue';

import { getSessions, getSessionsSSE } from '@/api/agent';
import { useSessionStatus } from '@/composables/useSessionStatus';
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

  const fetchSessions = async (showLoading = false) => {
    if (showLoading || sessions.value.length === 0) {
      isLoading.value = true;
    }
    try {
      const response = await getSessions();
      sessions.value = response.sessions;
    } catch {
      // Non-blocking: retain last known sessions, retry via SSE/polling.
    } finally {
      isLoading.value = false;
    }
  };

  const startFallbackPolling = () => {
    if (fallbackPollTimer) return;
    fallbackPollTimer = setInterval(() => {
      void fetchSessions();
    }, fallbackPollIntervalMs);
  };

  const disconnectSSE = () => {
    if (!cancelGetSessionsSSE) return;
    cancelGetSessionsSSE();
    cancelGetSessionsSSE = null;
  };

  const connectSSE = async () => {
    disconnectSSE();
    stopFallbackPolling();
    try {
      cancelGetSessionsSSE = await getSessionsSSE({
        onOpen: () => {
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
          isConnected.value = false;
          startFallbackPolling();
        },
        onClose: (info) => {
          if (info.willRetry) return;
          isConnected.value = false;
          startFallbackPolling();
        },
      });
    } catch {
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

  onMounted(() => {
    if (initialFetch) {
      void fetchSessions(true);
    }
    void connectSSE();
  });

  onUnmounted(() => {
    unsubscribeStatusChange();
    disconnectSSE();
    stopFallbackPolling();
  });

  return {
    sessions,
    isLoading,
    isConnected,
    refresh: fetchSessions,
    reconnect: connectSSE,
  };
}
