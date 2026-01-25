import { ref, computed, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import type { AgentSSEEvent } from '@/types/event'

export interface TimelineState {
  currentIndex: Ref<number>
  isPlaying: Ref<boolean>
  playbackSpeed: Ref<number>
  currentTime: Ref<number>
  duration: Ref<number>
  progress: Ref<number>
  currentEvent: Ref<AgentSSEEvent | null>
  play: () => void
  pause: () => void
  stop: () => void
  seek: (index: number) => void
  seekByTime: (timestamp: number) => void
  setSpeed: (speed: number) => void
  stepForward: () => void
  stepBackward: () => void
}

/**
 * Composable for managing timeline playback of session events
 */
export function useTimeline(events: Ref<AgentSSEEvent[]>): TimelineState {
  const currentIndex = ref(0)
  const isPlaying = ref(false)
  const playbackSpeed = ref(1.0)
  let playbackTimer: ReturnType<typeof setTimeout> | null = null

  // Calculate time-based properties
  const timestamps = computed(() => {
    return events.value.map(e => e.data.timestamp || 0)
  })

  const startTime = computed(() => {
    if (timestamps.value.length === 0) return 0
    return Math.min(...timestamps.value)
  })

  const endTime = computed(() => {
    if (timestamps.value.length === 0) return 0
    return Math.max(...timestamps.value)
  })

  const duration = computed(() => {
    return endTime.value - startTime.value
  })

  const currentTime = computed(() => {
    if (events.value.length === 0) return 0
    const event = events.value[currentIndex.value]
    return (event?.data.timestamp || startTime.value) - startTime.value
  })

  const progress = computed(() => {
    if (duration.value === 0) return 0
    return (currentTime.value / duration.value) * 100
  })

  const currentEvent = computed(() => {
    if (events.value.length === 0) return null
    return events.value[currentIndex.value] || null
  })

  // Get time until next event (for playback scheduling)
  const getTimeToNextEvent = (): number => {
    if (currentIndex.value >= events.value.length - 1) return 0

    const current = events.value[currentIndex.value]
    const next = events.value[currentIndex.value + 1]

    if (!current?.data.timestamp || !next?.data.timestamp) {
      return 500 // Default delay if no timestamp
    }

    const delay = (next.data.timestamp - current.data.timestamp) / playbackSpeed.value
    return Math.max(100, Math.min(delay, 5000)) // Clamp between 100ms and 5s
  }

  // Schedule next event during playback
  const scheduleNextEvent = () => {
    if (!isPlaying.value) return
    if (currentIndex.value >= events.value.length - 1) {
      // Reached end
      isPlaying.value = false
      return
    }

    const delay = getTimeToNextEvent()
    playbackTimer = setTimeout(() => {
      if (isPlaying.value) {
        currentIndex.value++
        scheduleNextEvent()
      }
    }, delay)
  }

  // Control functions
  const play = () => {
    if (currentIndex.value >= events.value.length - 1) {
      currentIndex.value = 0 // Reset to start if at end
    }
    isPlaying.value = true
    scheduleNextEvent()
  }

  const pause = () => {
    isPlaying.value = false
    if (playbackTimer) {
      clearTimeout(playbackTimer)
      playbackTimer = null
    }
  }

  const stop = () => {
    pause()
    currentIndex.value = 0
  }

  const seek = (index: number) => {
    const wasPlaying = isPlaying.value
    pause()
    currentIndex.value = Math.max(0, Math.min(index, events.value.length - 1))
    if (wasPlaying) {
      play()
    }
  }

  const seekByTime = (timestamp: number) => {
    // Find the event closest to the given timestamp
    const targetTime = startTime.value + timestamp
    let closestIndex = 0
    let closestDiff = Infinity

    events.value.forEach((event, index) => {
      const diff = Math.abs((event.data.timestamp || 0) - targetTime)
      if (diff < closestDiff) {
        closestDiff = diff
        closestIndex = index
      }
    })

    seek(closestIndex)
  }

  const setSpeed = (speed: number) => {
    playbackSpeed.value = Math.max(0.25, Math.min(speed, 4.0))
  }

  const stepForward = () => {
    if (currentIndex.value < events.value.length - 1) {
      currentIndex.value++
    }
  }

  const stepBackward = () => {
    if (currentIndex.value > 0) {
      currentIndex.value--
    }
  }

  // Clean up on unmount
  onUnmounted(() => {
    if (playbackTimer) {
      clearTimeout(playbackTimer)
    }
  })

  // Stop playback when events change
  watch(events, () => {
    stop()
  })

  return {
    currentIndex,
    isPlaying,
    playbackSpeed,
    currentTime,
    duration,
    progress,
    currentEvent,
    play,
    pause,
    stop,
    seek,
    seekByTime,
    setSpeed,
    stepForward,
    stepBackward,
  }
}

/**
 * Format milliseconds to MM:SS display
 */
export function formatTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}
