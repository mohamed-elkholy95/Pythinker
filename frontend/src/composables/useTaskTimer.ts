import { ref, watch, onUnmounted, computed, type Ref } from 'vue'

/**
 * Shared task timer state that persists across component remounts.
 * This prevents timer reset when TaskProgressBar switches between
 * ChatPage (panel closed) and ToolPanel (panel open) views.
 */

// Global timer state (persists across component instances)
const taskStartTime = ref<number | null>(null)
const taskElapsedSeconds = ref(0)
let timerIntervalId: ReturnType<typeof setInterval> | null = null

// Global animation state
const shapes = ['circle', 'diamond', 'cube', 'square'] as const
type Shape = typeof shapes[number]
const currentShapeIndex = ref(0)
const currentShape = ref<Shape>('circle')
let shapeIntervalId: ReturnType<typeof setInterval> | null = null

// Reference counting for cleanup
let activeSubscribers = 0

/**
 * Reset all global timer state.
 * Primarily used in tests to ensure clean state between test cases.
 */
export function resetTaskTimerState() {
  if (timerIntervalId) {
    clearInterval(timerIntervalId)
    timerIntervalId = null
  }
  if (shapeIntervalId) {
    clearInterval(shapeIntervalId)
    shapeIntervalId = null
  }
  taskStartTime.value = null
  taskElapsedSeconds.value = 0
  currentShapeIndex.value = 0
  currentShape.value = 'circle'
  activeSubscribers = 0
}

const startTimer = () => {
  if (timerIntervalId) return
  taskStartTime.value = Date.now()
  taskElapsedSeconds.value = 0
  timerIntervalId = setInterval(() => {
    if (taskStartTime.value) {
      taskElapsedSeconds.value = Math.floor((Date.now() - taskStartTime.value) / 1000)
    }
  }, 1000)
}

const stopTimer = () => {
  if (timerIntervalId) {
    clearInterval(timerIntervalId)
    timerIntervalId = null
  }
}

const resetTimer = () => {
  stopTimer()
  taskStartTime.value = null
  taskElapsedSeconds.value = 0
}

const startShapeAnimation = () => {
  if (shapeIntervalId) return
  shapeIntervalId = setInterval(() => {
    currentShapeIndex.value = (currentShapeIndex.value + 1) % shapes.length
    currentShape.value = shapes[currentShapeIndex.value]
  }, 1200)
}

const stopShapeAnimation = () => {
  if (shapeIntervalId) {
    clearInterval(shapeIntervalId)
    shapeIntervalId = null
  }
  currentShapeIndex.value = 0
  currentShape.value = 'circle'
}

export interface UseTaskTimerOptions {
  isLoading: Ref<boolean>
  isAllCompleted: Ref<boolean>
}

export function useTaskTimer(options: UseTaskTimerOptions) {
  const { isLoading, isAllCompleted } = options

  // Track this subscriber
  activeSubscribers++

  const formattedElapsedTime = computed(() => {
    const seconds = taskElapsedSeconds.value
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  })

  // Watch loading state to control timer/animation
  const stopLoadingWatch = watch(
    isLoading,
    (loading) => {
      if (loading && !isAllCompleted.value) {
        startShapeAnimation()
        startTimer()
      } else {
        stopShapeAnimation()
        stopTimer()
      }
    },
    { immediate: true }
  )

  // Watch completion to stop timers
  const stopCompletedWatch = watch(isAllCompleted, (completed) => {
    if (completed) {
      stopShapeAnimation()
      stopTimer()
    }
  })

  // Cleanup on unmount
  onUnmounted(() => {
    stopLoadingWatch()
    stopCompletedWatch()
    activeSubscribers--

    // Only cleanup global state when no more subscribers
    if (activeSubscribers === 0) {
      stopShapeAnimation()
      stopTimer()
    }
  })

  return {
    taskStartTime,
    taskElapsedSeconds,
    formattedElapsedTime,
    currentShape,
    startTimer,
    stopTimer,
    resetTimer,
    startShapeAnimation,
    stopShapeAnimation
  }
}
