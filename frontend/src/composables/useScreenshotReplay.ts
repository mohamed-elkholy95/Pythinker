import { ref, computed, watch, onUnmounted, type Ref, type ComputedRef } from 'vue'
import type { ScreenshotMetadata, ScreenshotListResponse } from '../types/screenshot'
import { apiClient, type ApiResponse } from '../api/client'

export function useScreenshotReplay(sessionId: Ref<string | undefined>) {
  const screenshots = ref<ScreenshotMetadata[]>([])
  const currentIndex = ref<number>(-1)
  const isLoading = ref(false)

  // Blob URL management — revoke previous to prevent memory leaks
  const currentBlobUrl = ref<string>('')
  let pendingBlobUrl: string | null = null

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

  // Watch currentScreenshot and fetch blob
  watch(currentScreenshot, async (screenshot) => {
    if (!screenshot) {
      if (pendingBlobUrl) {
        URL.revokeObjectURL(pendingBlobUrl)
        pendingBlobUrl = null
      }
      currentBlobUrl.value = ''
      return
    }

    const url = await fetchScreenshotBlob(screenshot.id)
    // Revoke previous blob URL
    if (pendingBlobUrl) {
      URL.revokeObjectURL(pendingBlobUrl)
    }
    pendingBlobUrl = url
    currentBlobUrl.value = url
  })

  async function loadScreenshots(): Promise<void> {
    if (!sessionId.value) return
    isLoading.value = true
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
    if (pendingBlobUrl) {
      URL.revokeObjectURL(pendingBlobUrl)
      pendingBlobUrl = null
    }
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
