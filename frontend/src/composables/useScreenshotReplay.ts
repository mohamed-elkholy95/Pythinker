import { ref, computed, watch, onUnmounted, type Ref, type ComputedRef } from 'vue'
import type { ScreenshotMetadata, ScreenshotListResponse } from '../types/screenshot'
import { apiClient, type ApiResponse } from '../api/client'

export function useScreenshotReplay(sessionId: Ref<string | undefined>) {
  const screenshots = ref<ScreenshotMetadata[]>([])
  const currentIndex = ref<number>(-1)
  const isLoading = ref(false)

  // Blob URL for currently rendered frame
  const currentBlobUrl = ref<string>('')
  const blobUrlCache = new Map<string, string>()
  let renderRequestVersion = 0

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

  async function fetchScreenshotBlob(screenshotId: string): Promise<string> {
    if (!sessionId.value) return ''
    try {
      const response = await apiClient.get(
        `/sessions/${sessionId.value}/screenshots/${screenshotId}`,
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

  async function prefetchNextScreenshot(): Promise<void> {
    const nextIndex = currentIndex.value + 1
    if (nextIndex < 0 || nextIndex >= screenshots.value.length) return

    const nextScreenshot = screenshots.value[nextIndex]
    if (!nextScreenshot || blobUrlCache.has(nextScreenshot.id)) return

    const blobUrl = await fetchScreenshotBlob(nextScreenshot.id)
    if (blobUrl) blobUrlCache.set(nextScreenshot.id, blobUrl)
  }

  // Keep the current frame warm and prefetch the next frame for smoother stepping.
  watch(currentScreenshot, async (screenshot) => {
    const requestVersion = ++renderRequestVersion
    if (!screenshot) {
      currentBlobUrl.value = ''
      return
    }

    const blobUrl = await getOrFetchBlobUrl(screenshot.id)
    if (requestVersion !== renderRequestVersion) return

    currentBlobUrl.value = blobUrl
    void prefetchNextScreenshot()
  })

  watch(sessionId, (nextSessionId, previousSessionId) => {
    if (nextSessionId !== previousSessionId) {
      renderRequestVersion++
      clearBlobCache()
      screenshots.value = []
      currentIndex.value = -1
    }
  })

  async function loadScreenshots(): Promise<void> {
    if (!sessionId.value) return
    isLoading.value = true
    renderRequestVersion++
    clearBlobCache()
    try {
      const response = await apiClient.get<ApiResponse<ScreenshotListResponse>>(
        `/sessions/${sessionId.value}/screenshots`
      )
      screenshots.value = response.data.data.screenshots
      if (screenshots.value.length > 0) {
        currentIndex.value = screenshots.value.length - 1
      }
    } catch {
      screenshots.value = []
      currentIndex.value = -1
    } finally {
      isLoading.value = false
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
    currentIndex.value = Math.round((percent / 100) * maxIndex)
  }

  // Cleanup blob URLs on unmount
  onUnmounted(() => {
    renderRequestVersion++
    clearBlobCache()
  })

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
