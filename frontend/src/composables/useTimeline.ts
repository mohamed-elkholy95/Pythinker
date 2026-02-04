import { ref, computed, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import type { AgentSSEEvent } from '@/types/event'

/**
 * Timeline playback modes
 */
export type TimelineMode = 'live' | 'replay' | 'paused'

export interface TimelineState {
  // Core state
  currentIndex: Ref<number>
  isPlaying: Ref<boolean>
  playbackSpeed: Ref<number>
  mode: Ref<TimelineMode>

  // Time-based properties
  currentTime: Ref<number>
  duration: Ref<number>
  progress: Ref<number>
  currentEvent: Ref<AgentSSEEvent | null>

  // Computed state
  isLive: Ref<boolean>
  isReplay: Ref<boolean>
  isPaused: Ref<boolean>
  canStepForward: Ref<boolean>
  canStepBackward: Ref<boolean>

  // Playback controls
  play: () => void
  pause: () => void
  stop: () => void
  seek: (index: number) => void
  seekByTime: (timestamp: number) => void
  seekByProgress: (progressPercent: number) => void
  setSpeed: (speed: number) => void
  stepForward: () => void
  stepBackward: () => void

  // Mode controls
  jumpToLive: () => void
  enterReplayMode: () => void
  setMode: (mode: TimelineMode) => void
}

/**
 * Composable for managing timeline playback of session events
 * with support for live, replay, and paused modes.
 */
export function useTimeline(
  events: Ref<AgentSSEEvent[]>,
  options: {
    autoLive?: boolean  // Automatically switch to live mode on new events
  } = {}
): TimelineState {
  const { autoLive = true } = options

  // Core state
  const currentIndex = ref(0)
  const isPlaying = ref(false)
  const playbackSpeed = ref(1.0)
  const mode = ref<TimelineMode>('live')

  let playbackTimer: ReturnType<typeof setTimeout> | null = null

  // Mode computed properties
  const isLive = computed(() => mode.value === 'live')
  const isReplay = computed(() => mode.value === 'replay')
  const isPaused = computed(() => mode.value === 'paused')

  // Navigation computed properties
  const canStepForward = computed(() => currentIndex.value < events.value.length - 1)
  const canStepBackward = computed(() => currentIndex.value > 0)

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
    // In live mode, always show progress at 100% (end of timeline)
    if (mode.value === 'live') return 100
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
    if (!isPlaying.value || mode.value !== 'replay') return
    if (currentIndex.value >= events.value.length - 1) {
      // Reached end
      isPlaying.value = false
      mode.value = 'paused'
      return
    }

    const delay = getTimeToNextEvent()
    playbackTimer = setTimeout(() => {
      if (isPlaying.value && mode.value === 'replay') {
        currentIndex.value++
        scheduleNextEvent()
      }
    }, delay)
  }

  // Clear any pending playback timer
  const clearPlaybackTimer = () => {
    if (playbackTimer) {
      clearTimeout(playbackTimer)
      playbackTimer = null
    }
  }

  // Control functions
  const play = () => {
    if (mode.value === 'live') {
      // Can't play in live mode - already at live
      return
    }

    if (currentIndex.value >= events.value.length - 1) {
      currentIndex.value = 0 // Reset to start if at end
    }

    mode.value = 'replay'
    isPlaying.value = true
    scheduleNextEvent()
  }

  const pause = () => {
    isPlaying.value = false
    clearPlaybackTimer()

    if (mode.value === 'replay') {
      mode.value = 'paused'
    }
  }

  const stop = () => {
    pause()
    currentIndex.value = 0
  }

  const seek = (index: number) => {
    const wasPlaying = isPlaying.value
    clearPlaybackTimer()

    // Seeking exits live mode
    if (mode.value === 'live' && index < events.value.length - 1) {
      mode.value = 'replay'
      isPlaying.value = false
    }

    currentIndex.value = Math.max(0, Math.min(index, events.value.length - 1))

    if (wasPlaying && mode.value === 'replay') {
      isPlaying.value = true
      scheduleNextEvent()
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

  const seekByProgress = (progressPercent: number) => {
    const targetTime = (progressPercent / 100) * duration.value
    seekByTime(targetTime)
  }

  const setSpeed = (speed: number) => {
    playbackSpeed.value = Math.max(0.25, Math.min(speed, 4.0))
  }

  const stepForward = () => {
    if (canStepForward.value) {
      // Exit live mode when stepping
      if (mode.value === 'live') {
        mode.value = 'paused'
      }
      pause()
      currentIndex.value++
    }
  }

  const stepBackward = () => {
    if (canStepBackward.value) {
      // Exit live mode when stepping back
      if (mode.value === 'live') {
        mode.value = 'paused'
      }
      pause()
      currentIndex.value--
    }
  }

  // Mode control functions
  const jumpToLive = () => {
    clearPlaybackTimer()
    isPlaying.value = false
    mode.value = 'live'
    currentIndex.value = Math.max(0, events.value.length - 1)
  }

  const enterReplayMode = () => {
    if (mode.value === 'live') {
      mode.value = 'paused'
    }
  }

  const setMode = (newMode: TimelineMode) => {
    if (newMode === 'live') {
      jumpToLive()
    } else if (newMode === 'replay') {
      mode.value = 'replay'
    } else {
      pause()
      mode.value = 'paused'
    }
  }

  // Watch for new events in live mode
  watch(
    () => events.value.length,
    (newLength, oldLength) => {
      if (autoLive && mode.value === 'live' && newLength > oldLength) {
        // Auto-advance to latest event in live mode
        currentIndex.value = newLength - 1
      }
    }
  )

  // Clean up on unmount
  onUnmounted(() => {
    clearPlaybackTimer()
  })

  // Reset playback when events array changes completely
  watch(
    events,
    (newEvents, oldEvents) => {
      // Only reset if this is a completely different set of events
      if (newEvents !== oldEvents && newEvents.length === 0) {
        stop()
        mode.value = 'live'
      }
    }
  )

  return {
    // Core state
    currentIndex,
    isPlaying,
    playbackSpeed,
    mode,

    // Time-based properties
    currentTime,
    duration,
    progress,
    currentEvent,

    // Computed state
    isLive,
    isReplay,
    isPaused,
    canStepForward,
    canStepBackward,

    // Playback controls
    play,
    pause,
    stop,
    seek,
    seekByTime,
    seekByProgress,
    setSpeed,
    stepForward,
    stepBackward,

    // Mode controls
    jumpToLive,
    enterReplayMode,
    setMode,
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

/**
 * Format timestamp to human-readable date/time
 */
export function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp * 1000) // Assuming Unix timestamp in seconds
  return date.toLocaleString('en-US', {
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
