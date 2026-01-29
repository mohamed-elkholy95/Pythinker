<template>
  <div v-if="isVisible" class="task-progress-bar">
    <!-- Collapsed View -->
    <div v-if="!isExpanded" class="relative">
      <!-- Live VNC thumbnail (auto-updates every 1s during task execution) -->
      <div
        v-if="showCollapsedThumbnail"
        class="absolute -top-[38px] left-2 z-[1100] flex-shrink-0 group/thumb"
        @mouseenter="showTooltip"
        @mouseleave="hideTooltip"
      >
        <div
          v-if="displayThumbnailUrl"
          class="w-[140px] h-[80px] rounded-lg overflow-hidden border border-gray-200 dark:border-[#3a3a3a] bg-gray-50 dark:bg-[#1a1a1a] cursor-pointer hover:border-gray-300 dark:hover:border-[#4a4a4a] transition-colors flex items-center justify-center"
          @click.stop="emit('openPanel')"
        >
          <img
            :src="displayThumbnailUrl"
            alt="Screenshot"
            class="w-full h-full object-cover"
          />
        </div>
      </div>

      <!-- Compact Progress Bar -->
      <div
        class="bg-white dark:bg-[#2a2a2a] rounded-lg border border-gray-200 dark:border-[#3a3a3a] px-4 py-2.5 flex items-center gap-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-[#2d2d2d] transition-colors shadow-sm"
        :class="showCollapsedThumbnail && displayThumbnailUrl ? 'pl-[156px]' : ''"
        @click="toggleExpand"
      >
        <div class="flex-shrink-0">
          <Check v-if="isAllCompleted" class="w-4 h-4 text-[#22c55e]" :stroke-width="2.5" />
          <div
            v-else
            class="status-morph status-morph-small"
            :class="[
              isIdle ? 'status-morph-idle' : 'status-morph-active',
              `shape-${currentShape}`
            ]"
          ></div>
        </div>

        <div class="flex-1 min-w-0 flex flex-col gap-1">
          <span class="text-[15px] font-normal text-gray-900 dark:text-[#e5e5e5] truncate">
            {{ currentTaskDescription }}
          </span>
          <div class="flex items-center gap-2 text-xs text-gray-600 dark:text-[#888888]">
            <span v-if="taskStartTime">{{ formattedElapsedTime }}</span>
            <span v-if="taskStartTime && (currentToolName || props.isThinking || props.isLoading)">•</span>
            <span v-if="isToolRunning">Using {{ currentToolName.toLowerCase() }}</span>
            <span v-else-if="props.isThinking">Thinking</span>
            <span v-else-if="props.currentTool && currentToolName && !isAllCompleted">Using {{ currentToolName.toLowerCase() }}</span>
            <span v-else-if="props.isLoading && !isAllCompleted">Processing</span>
          </div>
        </div>

        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-sm font-normal text-gray-600 dark:text-[#888888]">{{ progressText }}</span>
          <button @click.stop="toggleExpand" class="p-0.5 hover:bg-gray-200 dark:hover:bg-[#3a3a3a] rounded transition-colors">
            <ChevronUp class="w-4 h-4 text-gray-600 dark:text-[#888888]" />
          </button>
        </div>
      </div>
    </div>

    <!-- Expanded View -->
    <div
      v-else
      class="flex flex-col rounded-lg border border-gray-200 dark:border-[#3a3a3a] bg-white dark:bg-[#2a2a2a] overflow-hidden shadow-sm"
    >
      <!-- Header -->
      <div class="px-5 py-4 border-b border-gray-200 dark:border-[#3a3a3a]">
        <div class="flex items-start gap-4">
          <!-- Live VNC thumbnail (auto-updates every 1s during task execution) -->
          <div
            v-if="showExpandedThumbnail && displayThumbnailUrl"
            class="flex-shrink-0 w-[140px] h-[80px] rounded-lg overflow-hidden border border-gray-200 dark:border-[#3a3a3a] bg-gray-50 dark:bg-[#1a1a1a] cursor-pointer hover:border-gray-300 dark:hover:border-[#4a4a4a] transition-colors flex items-center justify-center"
            @click.stop="emit('openPanel')"
          >
            <img
              :src="displayThumbnailUrl"
              alt="Screenshot"
              class="w-full h-full object-cover"
            />
          </div>

          <!-- Title and Tool Info -->
          <div class="flex-1 min-w-0">
            <h2 class="text-xl font-normal text-gray-900 dark:text-[#e5e5e5] mb-3">
              {{ $t("Pythinker's computer") }}
            </h2>

            <div class="flex items-center gap-2.5">
              <div class="w-7 h-7 rounded bg-gray-200 dark:bg-[#3a3a3a] flex items-center justify-center flex-shrink-0">
                <component :is="currentToolIcon" class="w-4 h-4 text-gray-600 dark:text-[#888888]" />
              </div>
              <span class="text-[15px] text-gray-600 dark:text-[#888888]">
                Pythinker is using <span class="text-gray-900 dark:text-[#e5e5e5]">{{ currentToolName }}</span>
              </span>
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              @click.stop="emit('openPanel')"
              class="p-1.5 hover:bg-gray-200 dark:hover:bg-[#3a3a3a] rounded transition-colors"
            >
              <MonitorPlay class="w-5 h-5 text-gray-600 dark:text-[#888888]" />
            </button>
            <button
              @click="toggleExpand"
              class="p-1.5 hover:bg-gray-200 dark:hover:bg-[#3a3a3a] rounded transition-colors"
            >
              <ChevronDown class="w-5 h-5 text-gray-600 dark:text-[#888888]" />
            </button>
          </div>
        </div>
      </div>

      <!-- Task Progress Section -->
      <div class="px-5 py-4">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-normal text-gray-900 dark:text-[#e5e5e5]">{{ $t('Task progress') }}</h3>
          <span class="text-sm text-gray-600 dark:text-[#888888]">{{ progressText }}</span>
        </div>

        <!-- Task List -->
        <div class="flex flex-col gap-2.5 overflow-y-auto max-h-[50vh] custom-scrollbar">
          <div
            v-for="step in steps"
            :key="step.id"
            class="flex items-start gap-3"
          >
            <div class="flex-shrink-0 mt-0.5">
              <Check
                v-if="step.status === 'completed'"
                class="w-4 h-4 text-[#22c55e]"
                :stroke-width="2.5"
              />
              <div
                v-else-if="step.status === 'running'"
                class="status-morph-step"
                :class="`shape-${currentShape}`"
              ></div>
              <div v-else class="w-4 h-4 rounded-full border-2 border-gray-300 dark:border-[#3a3a3a]"></div>
            </div>

            <span
              class="text-[15px] leading-relaxed flex-1"
              :class="step.status === 'completed' || step.status === 'running' ? 'text-gray-900 dark:text-[#e5e5e5]' : 'text-gray-400 dark:text-[#666666]'"
            >
              {{ step.description }}
            </span>
          </div>
        </div>

        <!-- Timer -->
        <div v-if="taskStartTime" class="mt-4 pt-4 border-t border-gray-200 dark:border-[#3a3a3a] flex items-center justify-between">
          <span class="text-sm text-gray-600 dark:text-[#888888]">Elapsed time</span>
          <span class="text-sm font-mono text-gray-900 dark:text-[#e5e5e5]">{{ formattedElapsedTime }}</span>
        </div>
      </div>
    </div>
    
    <Teleport to="body">
      <Transition name="tooltip">
        <div
          v-if="tooltipVisible"
          ref="tooltipRef"
          class="tooltip-badge fixed inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-[#1a1a1a] text-gray-900 dark:text-[#e5e5e5] rounded text-xs font-normal whitespace-nowrap shadow-lg z-[12000] pointer-events-none border border-gray-200 dark:border-[#3a3a3a]"
          :style="tooltipStyle"
        >
          {{ $t("View Pythinker's computer") }}
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick, toRef } from 'vue'
import { ChevronUp, ChevronDown, Check, MonitorPlay, Terminal, Globe, FolderOpen } from 'lucide-vue-next'
import type { PlanEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'
import { useLiveVncThumbnail } from '@/composables/useLiveVncThumbnail'

interface Props {
  plan?: PlanEventData
  isLoading: boolean
  isThinking: boolean
  showThumbnail?: boolean
  hideThumbnail?: boolean
  defaultExpanded?: boolean
  compact?: boolean
  thumbnailUrl?: string
  currentTool?: { name: string; function: string; functionArg?: string; status?: string } | null
  toolContent?: ToolContent | null
  sessionId?: string
  liveVnc?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showThumbnail: false,
  hideThumbnail: false,
  defaultExpanded: false,
  compact: false,
  thumbnailUrl: '',
  currentTool: null,
  sessionId: '',
  liveVnc: false
})

const emit = defineEmits<{
  (e: 'openPanel'): void
}>()

const isToolRunning = computed(() => {
  return props.currentTool?.status === 'calling' || props.currentTool?.status === 'running'
})

// Computed: show thumbnails in collapsed/expanded view
// Show thumbnail in collapsed view when showThumbnail is true (regardless of compact prop)
const showCollapsedThumbnail = computed(() => {
  return props.showThumbnail && !props.hideThumbnail
})

const showExpandedThumbnail = computed(() => {
  return props.showThumbnail && !props.hideThumbnail
})

// Check if all tasks are completed
const isAllCompleted = computed(() => {
  if (!props.plan?.steps) return false
  return props.plan.steps.every(step => step.status === 'completed')
})

// Computed: when to enable live VNC polling
const enableLivePolling = computed(() =>
  (showCollapsedThumbnail.value || showExpandedThumbnail.value) &&
  !!props.sessionId &&
  !isAllCompleted.value &&
  props.liveVnc
)

// Use live VNC thumbnail composable
const {
  thumbnailUrl: liveThumbnailUrl,
  isLoading: _thumbnailLoading,
  error: _thumbnailError,
  forceRefresh: refreshThumbnail
} = useLiveVncThumbnail({
  sessionId: toRef(props, 'sessionId'),
  enabled: enableLivePolling,
  updateIntervalMs: 1000,  // 1 FPS
  quality: 50,             // Optimized for 140x80px thumbnails
  scale: 0.3               // 30% scale
})

// Computed: prefer live thumbnail, fallback to static prop
const displayThumbnailUrl = computed(() =>
  liveThumbnailUrl.value || props.thumbnailUrl
)

const isExpanded = ref(props.defaultExpanded)
const tooltipVisible = ref(false)
const tooltipTop = ref(0)
const tooltipLeft = ref(0)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipAnchor = ref<DOMRect | null>(null)

const tooltipStyle = computed(() => ({
  top: `${tooltipTop.value}px`,
  left: `${tooltipLeft.value}px`
}))

const updateTooltipPosition = () => {
  if (!tooltipAnchor.value) return
  const rect = tooltipAnchor.value
  const padding = 12
  const tooltipRect = tooltipRef.value?.getBoundingClientRect()
  let left = rect.left + rect.width / 2
  if (tooltipRect) {
    const halfWidth = tooltipRect.width / 2
    left = Math.min(window.innerWidth - padding - halfWidth, Math.max(padding + halfWidth, left))
    const minTop = tooltipRect.height + padding
    const desiredTop = rect.top - 10
    tooltipTop.value = Math.max(desiredTop, minTop)
  } else {
    tooltipTop.value = rect.top - 10
  }
  tooltipLeft.value = left
}

const showTooltip = (event: MouseEvent) => {
  const target = event.currentTarget as HTMLElement | null
  if (!target) return
  const rect = target.getBoundingClientRect()
  tooltipAnchor.value = rect
  tooltipTop.value = rect.top - 10
  tooltipLeft.value = rect.left + rect.width / 2
  tooltipVisible.value = true
  nextTick(updateTooltipPosition)
}

const hideTooltip = () => {
  tooltipVisible.value = false
}

const handleScroll = () => {
  if (tooltipVisible.value) hideTooltip()
}

const handleResize = () => {
  if (tooltipVisible.value) updateTooltipPosition()
}

// Morphing shape animation
const shapes = ['circle', 'diamond', 'cube', 'square'] as const
type Shape = typeof shapes[number]
const currentShapeIndex = ref(0)
const currentShape = ref<Shape>('circle')
let shapeIntervalId: ReturnType<typeof setInterval> | null = null

// Task timer
const taskStartTime = ref<number | null>(null)
const taskElapsedSeconds = ref(0)
let timerIntervalId: ReturnType<typeof setInterval> | null = null

const isVisible = computed(() => {
  return props.plan && props.plan.steps.length > 0
})

// Idle state: not loading, not completed - agent is paused between steps
const isIdle = computed(() => {
  return !props.isLoading && !isAllCompleted.value && steps.value.length > 0
})

const steps = computed(() => props.plan?.steps ?? [])

const progressText = computed(() => {
  const completed = steps.value.filter(s => s.status === 'completed').length
  const total = steps.value.length
  return `${completed} / ${total}`
})

const formattedElapsedTime = computed(() => {
  const seconds = taskElapsedSeconds.value
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
})

const currentTaskDescription = computed(() => {
  const runningStep = steps.value.find(s => s.status === 'running')
  if (runningStep) return runningStep.description

  const pendingStep = steps.value.find(s => s.status === 'pending')
  if (pendingStep) return pendingStep.description

  if (isAllCompleted.value && steps.value.length > 0) {
    return steps.value[steps.value.length - 1].description
  }

  return 'Processing...'
})

// Get current tool name for display
const currentToolName = computed(() => {
  if (isAllCompleted.value) return 'Terminal' // Default back to terminal on complete
  if (props.currentTool?.function) return props.currentTool.function
  return 'Terminal'
})

// Get icon for current tool
const currentToolIcon = computed(() => {
  const toolName = props.currentTool?.name || ''
  if (toolName.includes('browser') || toolName.includes('web')) return Globe
  if (toolName.includes('file') || toolName.includes('folder')) return FolderOpen
  return Terminal
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
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

// Start/stop animations based on loading/thinking state
watch(() => props.isLoading, (loading) => {
  if (loading && !isAllCompleted.value) {
    startShapeAnimation()
    startTimer()
  } else {
    stopShapeAnimation()
    stopTimer()
  }
}, { immediate: true })

// Also watch for completion
watch(isAllCompleted, (completed) => {
  if (completed) {
    stopShapeAnimation()
    stopTimer()
    // Capture final screenshot when tasks complete
    if (props.sessionId && props.liveVnc) {
      refreshThumbnail()
    }
  }
})

onMounted(() => {
  if (props.isLoading && !isAllCompleted.value) {
    startShapeAnimation()
    startTimer()
  }
  window.addEventListener('scroll', handleScroll, true)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  stopShapeAnimation()
  stopTimer()
  window.removeEventListener('scroll', handleScroll, true)
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
/* Morphing shape animation */
.status-morph {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

.status-morph.status-morph-small {
  width: 10px;
  height: 10px;
}

/* Step indicator morphing shape */
.status-morph-step {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%);
  background-size: 200% 200%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  animation: shimmer 1.5s ease-in-out infinite;
}

.status-morph-step.shape-circle {
  border-radius: 50%;
}

.status-morph-step.shape-diamond {
  border-radius: 2px;
  transform: rotate(45deg) scale(0.85);
}

.status-morph-step.shape-cube {
  border-radius: 2px;
}

.status-morph-step.shape-square {
  border-radius: 3px;
}

.status-morph-active {
  background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%);
  background-size: 200% 200%;
  border: none;
  animation: shimmer 1.5s ease-in-out infinite, pulse-glow 2s ease-in-out infinite;
}

.status-morph-idle {
  border: 2px solid #666666;
  background: transparent;
}

/* Shape transformations */
.status-morph.shape-circle {
  border-radius: 50%;
  transform: rotate(0deg);
}

.status-morph.shape-square {
  border-radius: 2px;
  transform: rotate(0deg);
}

.status-morph.shape-diamond {
  border-radius: 2px;
  transform: rotate(45deg);
}

.status-morph.shape-cube {
  border-radius: 3px;
  transform: rotate(90deg) scale(1.1);
}

@keyframes pulse-glow {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(59, 130, 246, 0);
  }
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* Custom scrollbar */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 10px;
  transition: background 0.2s;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

:global(.dark) .custom-scrollbar::-webkit-scrollbar-thumb {
  background: #3a3a3a;
}

:global(.dark) .custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #4a4a4a;
}

.tooltip-badge {
  transform: translate(-50%, -100%);
  will-change: opacity, transform;
}

.tooltip-enter-active,
.tooltip-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}

.tooltip-enter-from,
.tooltip-leave-to {
  opacity: 0;
  transform: translate(-50%, calc(-100% + 6px));
}

.tooltip-enter-to,
.tooltip-leave-from {
  opacity: 1;
  transform: translate(-50%, -100%);
}
</style>