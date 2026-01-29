import { ref, watch, onUnmounted, type Ref } from 'vue'
import { getVNCScreenshot } from '@/api/agent'

export interface UseLiveVncThumbnailOptions {
  sessionId: Ref<string | undefined>
  enabled: Ref<boolean>              // Visibility-based control
  updateIntervalMs?: number          // Default 1000ms (1 FPS)
  quality?: number                   // 1-100, default 50
  scale?: number                     // 0.1-1.0, default 0.3
}

export interface UseLiveVncThumbnailReturn {
  thumbnailUrl: Ref<string>          // Object URL for thumbnail
  isLoading: Ref<boolean>            // First fetch in progress
  error: Ref<string | null>          // Last error message
  lastUpdate: Ref<Date | null>       // Timestamp of last update
  startPolling: () => void
  stopPolling: () => void
  forceRefresh: () => Promise<void>
}

export function useLiveVncThumbnail(
  options: UseLiveVncThumbnailOptions
): UseLiveVncThumbnailReturn {
  const {
    sessionId,
    enabled,
    updateIntervalMs = 1000,
    quality = 50,
    scale = 0.3
  } = options

  // State
  const thumbnailUrl = ref<string>('')
  const isLoading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)

  // Polling state
  let pollingInterval: ReturnType<typeof setInterval> | null = null
  let currentBlobUrl: string | null = null

  // Fetch thumbnail from backend
  const fetchThumbnail = async () => {
    if (!sessionId.value) {
      return
    }

    try {
      // First fetch sets loading state
      if (!currentBlobUrl) {
        isLoading.value = true
      }

      const blob = await getVNCScreenshot(sessionId.value, quality, scale)

      // Revoke old URL BEFORE creating new one (memory management)
      if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl)
      }

      currentBlobUrl = URL.createObjectURL(blob)
      thumbnailUrl.value = currentBlobUrl
      lastUpdate.value = new Date()
      error.value = null
      isLoading.value = false
    } catch (err: any) {
      error.value = err.message
      console.warn('[LiveThumbnail] Fetch failed:', err)
      isLoading.value = false
      // Continue polling despite errors (graceful degradation)
    }
  }

  // Start polling
  const startPolling = () => {
    if (pollingInterval) {
      return // Guard duplicate
    }

    fetchThumbnail() // Immediate fetch
    pollingInterval = setInterval(fetchThumbnail, updateIntervalMs)
  }

  // Stop polling
  const stopPolling = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
    }
  }

  // Force refresh (manual trigger)
  const forceRefresh = async () => {
    await fetchThumbnail()
  }

  // Auto start/stop based on enabled state
  watch(
    enabled,
    (isEnabled) => {
      if (isEnabled && sessionId.value) {
        startPolling()
      } else {
        stopPolling()
        // Keep the last thumbnail visible when polling stops
        // (don't clear thumbnailUrl - user should see the final state)
      }
    },
    { immediate: true }
  )

  // Clear thumbnail when session changes (new chat)
  watch(
    sessionId,
    (newSessionId, oldSessionId) => {
      if (newSessionId !== oldSessionId) {
        stopPolling()
        // Clear old thumbnail when switching sessions
        if (currentBlobUrl) {
          URL.revokeObjectURL(currentBlobUrl)
          currentBlobUrl = null
          thumbnailUrl.value = ''
        }
        // Start polling for new session if enabled
        if (enabled.value && newSessionId) {
          startPolling()
        }
      }
    }
  )

  // Cleanup on component unmount
  onUnmounted(() => {
    stopPolling()
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl)
      currentBlobUrl = null
    }
  })

  return {
    thumbnailUrl,
    isLoading,
    error,
    lastUpdate,
    startPolling,
    stopPolling,
    forceRefresh
  }
}
