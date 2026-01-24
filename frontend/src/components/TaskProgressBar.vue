<template>
  <div v-if="isVisible" class="task-progress-bar">
    <!-- Collapsed View -->
    <div
      v-if="!isExpanded"
      @click="toggleExpand"
      class="flex items-center gap-3 px-4 py-2.5 bg-[var(--background-menu-white)] border border-black/8 dark:border-[var(--border-main)] rounded-xl shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] cursor-pointer hover:bg-[var(--fill-tsp-white-light)] transition-colors"
    >
      <!-- Morphing Indicator -->
      <div class="thinking-shape" :class="currentShape"></div>

      <!-- Task Description -->
      <div class="flex-1 min-w-0 flex items-center gap-2">
        <span class="text-sm text-[var(--text-primary)] truncate">{{ currentTaskDescription }}</span>
      </div>

      <!-- Progress, Timer, and Status -->
      <div class="flex items-center gap-3 flex-shrink-0">
        <span class="text-xs text-[var(--text-tertiary)]">{{ progressText }}</span>
        <ChevronUp class="w-4 h-4 text-[var(--icon-tertiary)]" />
      </div>
    </div>

    <!-- Bottom Status Row (always visible in collapsed) -->
    <div v-if="!isExpanded" class="flex items-center gap-2 mt-1.5 px-1">
      <span class="text-xs font-mono text-[var(--text-tertiary)]">{{ formattedTime }}</span>
      <span class="text-xs text-[var(--text-tertiary)]">{{ isThinking ? 'Thinking' : 'Processing' }}</span>
    </div>

    <!-- Expanded View -->
    <div
      v-else
      class="bg-[var(--background-menu-white)] border border-black/8 dark:border-[var(--border-main)] rounded-xl shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] overflow-hidden"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-3 border-b border-[var(--border-light)]">
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold text-[var(--text-primary)]">{{ $t('Task Progress') }}</span>
          <span class="text-xs text-[var(--text-tertiary)]">{{ progressText }}</span>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs font-mono text-[var(--text-tertiary)]">{{ formattedTime }}</span>
          <button
            @click.stop="toggleExpand"
            class="w-7 h-7 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)] cursor-pointer"
          >
            <ChevronDown class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>

      <!-- Task List -->
      <div class="max-h-[300px] overflow-y-auto">
        <div v-for="(step, index) in steps" :key="step.id" class="flex items-start gap-3 px-4 py-2.5 hover:bg-[var(--fill-tsp-white-light)]">
          <!-- Step Indicator -->
          <div class="flex-shrink-0 w-5 h-5 flex items-center justify-center mt-0.5">
            <div v-if="step.status === 'completed'" class="w-4 h-4 rounded-full bg-green-500 flex items-center justify-center">
              <Check class="w-3 h-3 text-white" />
            </div>
            <div v-else-if="step.status === 'running'" class="thinking-shape small" :class="currentShape"></div>
            <div v-else class="w-4 h-4 rounded-full border-2 border-[var(--border-dark)]"></div>
          </div>

          <!-- Step Content -->
          <div class="flex-1 min-w-0">
            <div
              class="text-sm truncate"
              :class="step.status === 'running' ? 'text-[var(--text-primary)] font-medium' : 'text-[var(--text-secondary)]'"
            >
              {{ step.description }}
            </div>
            <div v-if="step.status === 'running'" class="text-xs text-[var(--text-tertiary)] mt-0.5">
              {{ isThinking ? 'Thinking' : 'Processing' }}
            </div>
          </div>

          <!-- Step Number -->
          <div class="flex-shrink-0 text-xs text-[var(--text-tertiary)]">
            {{ index + 1 }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ChevronUp, ChevronDown, Check } from 'lucide-vue-next'
import type { PlanEventData } from '@/types/event'

interface Props {
  plan?: PlanEventData
  isLoading: boolean
  isThinking: boolean
  showThumbnail?: boolean
  thumbnailUrl?: string
}

const props = withDefaults(defineProps<Props>(), {
  showThumbnail: false,
  thumbnailUrl: ''
})

const isExpanded = ref(false)

// Morphing shape animation (same as ThinkingIndicator)
const shapes = ['circle', 'diamond', 'cube'] as const
type Shape = typeof shapes[number]
const currentShapeIndex = ref(0)
const currentShape = ref<Shape>('circle')
let shapeIntervalId: ReturnType<typeof setInterval> | null = null

// Timer functionality
const startTime = ref<number | null>(null)
const elapsedSeconds = ref(0)
let timerIntervalId: ReturnType<typeof setInterval> | null = null

const isVisible = computed(() => {
  return props.isLoading && props.plan && props.plan.steps.length > 0
})

const steps = computed(() => props.plan?.steps ?? [])

const progressText = computed(() => {
  const completed = steps.value.filter(s => s.status === 'completed').length
  const running = steps.value.find(s => s.status === 'running')
  const currentIndex = running ? steps.value.indexOf(running) + 1 : completed + 1
  const total = steps.value.length
  return `${Math.min(currentIndex, total)} / ${total}`
})

const currentTaskDescription = computed(() => {
  const runningStep = steps.value.find(s => s.status === 'running')
  if (runningStep) return runningStep.description

  const pendingStep = steps.value.find(s => s.status === 'pending')
  if (pendingStep) return pendingStep.description

  return 'Processing...'
})

const formattedTime = computed(() => {
  const minutes = Math.floor(elapsedSeconds.value / 60)
  const seconds = elapsedSeconds.value % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

// Define functions before watchers to avoid reference errors
const startShapeAnimation = () => {
  if (shapeIntervalId) return
  shapeIntervalId = setInterval(() => {
    currentShapeIndex.value = (currentShapeIndex.value + 1) % shapes.length
    currentShape.value = shapes[currentShapeIndex.value]
  }, 800)
}

const stopShapeAnimation = () => {
  if (shapeIntervalId) {
    clearInterval(shapeIntervalId)
    shapeIntervalId = null
  }
}

const startTimer = () => {
  if (timerIntervalId) return
  startTime.value = Date.now()
  elapsedSeconds.value = 0
  timerIntervalId = setInterval(() => {
    if (startTime.value) {
      elapsedSeconds.value = Math.floor((Date.now() - startTime.value) / 1000)
    }
  }, 1000)
}

const stopTimer = () => {
  if (timerIntervalId) {
    clearInterval(timerIntervalId)
    timerIntervalId = null
  }
  // Keep the elapsed time visible after stopping
}

// Start/stop shape animation based on thinking state
watch(() => props.isThinking, (thinking) => {
  if (thinking) {
    startShapeAnimation()
  } else {
    stopShapeAnimation()
  }
}, { immediate: true })

// Start/stop timer based on loading state
watch(() => props.isLoading, (loading) => {
  if (loading) {
    startTimer()
  } else {
    stopTimer()
  }
}, { immediate: true })

onMounted(() => {
  if (props.isThinking) {
    startShapeAnimation()
  }
  if (props.isLoading) {
    startTimer()
  }
})

onUnmounted(() => {
  stopShapeAnimation()
  stopTimer()
})
</script>

<style scoped>
.thinking-shape {
  width: 12px;
  height: 12px;
  background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%);
  background-size: 200% 200%;
  animation: shimmer 1.5s ease-in-out infinite;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}

.thinking-shape.small {
  width: 10px;
  height: 10px;
}

/* Circle */
.thinking-shape.circle {
  border-radius: 50%;
}

/* Diamond */
.thinking-shape.diamond {
  border-radius: 2px;
  transform: rotate(45deg) scale(0.85);
}

/* Cube */
.thinking-shape.cube {
  border-radius: 2px;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
