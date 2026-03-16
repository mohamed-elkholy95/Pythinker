/**
 * Shared elapsed-time timer composable.
 *
 * Provides a reactive MM:SS formatted timer that can be started, stopped, and
 * reset. Used by TaskProgressBar and ToolPanelContent header to keep elapsed
 * time displays in sync.
 */
import { ref, computed, onScopeDispose } from 'vue'

export function useElapsedTimer() {
  const startTime = ref<number | null>(null)
  const elapsedSeconds = ref(0)
  let intervalId: ReturnType<typeof setInterval> | null = null

  /** MM:SS formatted string, safe for `font-variant-numeric: tabular-nums`. */
  const formatted = computed(() => {
    const s = elapsedSeconds.value
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
  })

  function start(fromTime?: number) {
    if (intervalId) return // already running
    startTime.value = fromTime ?? Date.now()
    elapsedSeconds.value = Math.floor((Date.now() - startTime.value) / 1000)
    intervalId = setInterval(() => {
      if (startTime.value) {
        elapsedSeconds.value = Math.floor((Date.now() - startTime.value) / 1000)
      }
    }, 1000)
  }

  function stop() {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  function reset() {
    stop()
    startTime.value = null
    elapsedSeconds.value = 0
  }

  // Cleanup on scope disposal (prevents leaked intervals)
  onScopeDispose(() => stop())

  return { startTime, elapsedSeconds, formatted, start, stop, reset }
}
