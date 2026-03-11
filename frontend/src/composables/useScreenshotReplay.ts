import { ref, computed, watch, getCurrentScope, onScopeDispose, type Ref, type ComputedRef } from 'vue'
import type { ScreenshotMetadata, ScreenshotListResponse } from '../types/screenshot'
import { apiClient, type ApiResponse } from '../api/client'

type ReplayStartPosition = 'first' | 'last' | 'preserve'

interface LoadScreenshotsOptions {
  startAt?: ReplayStartPosition
}

interface UseScreenshotReplayOptions {
  isShared?: boolean
}

export function useScreenshotReplay(
  sessionId: Ref<string | undefined>,
  options: UseScreenshotReplayOptions = {},
) {
  const screenshots = ref<ScreenshotMetadata[]>([])
  const currentIndex = ref<number>(-1)
  const isLoading = ref(false)

  // Blob URL for currently rendered frame
  const currentBlobUrl = ref<string>('')
  const blobUrlCache = new Map<string, string>()
  let renderRequestVersion = 0
  let loadRequestVersion = 0

  const currentScreenshot: ComputedRef<ScreenshotMetadata | null> = computed(() => {
    if (currentIndex.value < 0 || currentIndex.value >= screenshots.value.length) return null
    return screenshots.value[currentIndex.value]
  })

  const currentScreenshotUrl: ComputedRef<string> = computed(() => {
    return currentBlobUrl.value
  })

  const progress: ComputedRef<number> = computed(() => {
    const total = screenshots.value.length
    if (total <= 1 || currentIndex.value < 0) return 0
    return (currentIndex.value / (total - 1)) * 100
  })

  const canStepForward: ComputedRef<boolean> = computed(() => {
    return currentIndex.value >= 0 && currentIndex.value < screenshots.value.length - 1
  })

  const canStepBackward: ComputedRef<boolean> = computed(() => {
    return currentIndex.value > 0
  })

  const currentTimestamp: ComputedRef<number | undefined> = computed(() => {
    return currentScreenshot.value?.timestamp
  })

  const hasScreenshots: ComputedRef<boolean> = computed(() => {
    return screenshots.value.length > 0
  })

  const getScreenshotsBasePath = (activeSessionId: string): string => {
    const prefix = options.isShared ? '/sessions/shared' : '/sessions'
    return `${prefix}/${activeSessionId}/screenshots`
  }

  async function fetchScreenshotBlob(screenshotId: string): Promise<string> {
    const activeSessionId = sessionId.value
    if (!activeSessionId) return ''
    try {
      const response = await apiClient.get(
        `${getScreenshotsBasePath(activeSessionId)}/${screenshotId}`,
        { responseType: 'blob' }
      )
      return URL.createObjectURL(response.data as Blob)
    } catch {
      return ''
    }
  }

  function clearBlobCache(): void {
    for (const url of blobUrlCache.values()) {
      URL.revokeObjectURL(url)
    }
    blobUrlCache.clear()
    currentBlobUrl.value = ''
  }

  async function getOrFetchBlobUrl(screenshotId: string): Promise<string> {
    const cachedUrl = blobUrlCache.get(screenshotId)
    if (cachedUrl) return cachedUrl

    const blobUrl = await fetchScreenshotBlob(screenshotId)
    if (blobUrl) blobUrlCache.set(screenshotId, blobUrl)
    return blobUrl
  }

  const MAX_CACHE_SIZE = 20

  function evictOldFrames(): void {
    if (blobUrlCache.size <= MAX_CACHE_SIZE) return
    const current = currentIndex.value
    // Build set of IDs we want to keep (current ± 5)
    const keepIds = new Set<string>()
    for (let i = Math.max(0, current - 5); i <= Math.min(screenshots.value.length - 1, current + 5); i++) {
      keepIds.add(screenshots.value[i].id)
    }
    for (const [id, url] of blobUrlCache.entries()) {
      if (!keepIds.has(id)) {
        URL.revokeObjectURL(url)
        blobUrlCache.delete(id)
      }
      if (blobUrlCache.size <= MAX_CACHE_SIZE) break
    }
  }

  async function prefetchAhead(count = 3): Promise<void> {
    const fetches: Promise<void>[] = []
    for (let offset = 1; offset <= count; offset++) {
      const idx = currentIndex.value + offset
      if (idx < 0 || idx >= screenshots.value.length) break
      const s = screenshots.value[idx]
      if (!s || blobUrlCache.has(s.id)) continue
      fetches.push(
        fetchScreenshotBlob(s.id).then((url) => {
          if (url) blobUrlCache.set(s.id, url)
        })
      )
    }
    await Promise.all(fetches)
    evictOldFrames()
  }

  async function prefetchBehind(count = 2): Promise<void> {
    const fetches: Promise<void>[] = []
    for (let offset = 1; offset <= count; offset++) {
      const idx = currentIndex.value - offset
      if (idx < 0) break
      const s = screenshots.value[idx]
      if (!s || blobUrlCache.has(s.id)) continue
      fetches.push(
        fetchScreenshotBlob(s.id).then((url) => {
          if (url) blobUrlCache.set(s.id, url)
        })
      )
    }
    await Promise.all(fetches)
  }

  // Keep the current frame warm and prefetch adjacent frames for smoother stepping.
  watch(currentScreenshot, async (screenshot) => {
    const requestVersion = ++renderRequestVersion
    if (!screenshot) {
      currentBlobUrl.value = ''
      return
    }

    const blobUrl = await getOrFetchBlobUrl(screenshot.id)
    if (requestVersion !== renderRequestVersion) return

    currentBlobUrl.value = blobUrl
    void prefetchAhead(3)
    void prefetchBehind(2)
  })

  watch(sessionId, (nextSessionId, previousSessionId) => {
    if (nextSessionId !== previousSessionId) {
      renderRequestVersion++
      loadRequestVersion++
      clearBlobCache()
      screenshots.value = []
      currentIndex.value = -1
      isLoading.value = false
    }
  })

  async function loadScreenshots(options: LoadScreenshotsOptions = {}): Promise<void> {
    const activeSessionId = sessionId.value
    if (!activeSessionId) {
      screenshots.value = []
      currentIndex.value = -1
      isLoading.value = false
      return
    }

    const requestVersion = ++loadRequestVersion
    isLoading.value = true
    renderRequestVersion++
    const previousIndex = currentIndex.value
    clearBlobCache()
    try {
      const response = await apiClient.get<ApiResponse<ScreenshotListResponse>>(
        getScreenshotsBasePath(activeSessionId)
      )
      if (requestVersion !== loadRequestVersion || sessionId.value !== activeSessionId) return

      // Filter out session_end screenshots (captured after browser navigates to about:blank)
      screenshots.value = response.data.data.screenshots.filter(
        (s) => s.trigger !== 'session_end'
      )

      if (screenshots.value.length === 0) {
        currentIndex.value = -1
        return
      }

      if (options.startAt === 'first') {
        currentIndex.value = 0
      } else if (options.startAt === 'preserve' && previousIndex >= 0) {
        currentIndex.value = Math.min(previousIndex, screenshots.value.length - 1)
      } else {
        currentIndex.value = screenshots.value.length - 1
      }
    } catch {
      if (requestVersion !== loadRequestVersion) return
      screenshots.value = []
      currentIndex.value = -1
    } finally {
      if (requestVersion === loadRequestVersion) {
        isLoading.value = false
      }
    }
  }

  function stepForward(): void {
    if (canStepForward.value) {
      currentIndex.value++
    }
  }

  function stepBackward(): void {
    if (canStepBackward.value) {
      currentIndex.value--
    }
  }

  function seekByProgress(percent: number): void {
    const total = screenshots.value.length
    if (total === 0) return
    const maxIndex = total - 1
    const clampedPercent = Math.max(0, Math.min(percent, 100))
    currentIndex.value = Math.round((clampedPercent / 100) * maxIndex)
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      renderRequestVersion++
      loadRequestVersion++
      clearBlobCache()
    })
  }

  return {
    screenshots,
    currentIndex,
    isLoading,
    currentScreenshot,
    currentScreenshotUrl,
    progress,
    canStepForward,
    canStepBackward,
    currentTimestamp,
    hasScreenshots,
    loadScreenshots,
    stepForward,
    stepBackward,
    seekByProgress,
  }
}
