<template>
  <div v-if="isVisible" class="task-progress-bar">
    <!-- Collapsed View - Task Summary Bar -->
    <div v-if="!isExpanded" class="relative">
      <!-- Floating Terminal Thumbnail -->
      <div
        v-if="showCollapsedThumbnail"
        class="absolute -top-14 left-3 z-[1100] flex-shrink-0 group/thumb"
        @mouseenter="showTooltip"
        @mouseleave="hideTooltip"
      >
        <div
          class="w-[140px] h-[88px] sm:w-[150px] sm:h-[96px] rounded-xl overflow-hidden border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] cursor-pointer group-hover/thumb:border-[var(--text-brand)] transition-colors shadow-md"
          @click.stop="emit('openPanel')"
        >
          <!-- Live VNC View -->
          <VNCViewer
            v-if="showVncPreview"
            :session-id="sessionId"
            :enabled="true"
            :view-only="true"
            class="w-full h-full vnc-thumbnail"
          />
          <!-- Static Screenshot -->
          <img
            v-else-if="thumbnailUrl"
            :src="thumbnailUrl"
            alt="Computer view"
            class="w-full h-full object-cover"
          />
        </div>
        <!-- Expand Button -->
        <button
          @click.stop="emit('openPanel')"
          class="absolute bottom-1.5 right-1.5 w-6 h-6 rounded-md bg-[#4a4a4a]/80 hover:bg-[#5a5a5a] flex items-center justify-center transition-colors opacity-0 group-hover/thumb:opacity-100"
        >
          <ArrowUpRight class="w-3.5 h-3.5 text-white" />
        </button>
      </div>

      <div
        class="bg-[var(--background-menu-white)] rounded-2xl border border-black/8 dark:border-[var(--border-main)] shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] p-3 sm:p-4 flex items-center gap-3 clickable"
        :class="showCollapsedThumbnail ? 'pl-[176px] sm:pl-[188px]' : ''"
        @click="toggleExpand"
      >
        <!-- Status Indicator -->
        <div class="flex items-center gap-2.5 flex-1 min-w-0">
          <div v-if="isAllCompleted" class="flex-shrink-0">
            <Check class="w-4 h-4 text-[#22c55e]" :stroke-width="2.5" />
          </div>
          <div
            v-else
            class="status-dot"
            :class="isIdle ? 'status-dot-idle' : 'status-dot-active'"
          ></div>
          <span class="text-sm text-[var(--text-primary)] truncate">{{ currentTaskDescription }}</span>
        </div>

        <!-- Progress Indicator -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-xs text-[var(--text-tertiary)]">{{ progressText }}</span>
          <button @click.stop="toggleExpand" class="p-0.5 hover:bg-[var(--fill-tsp-gray-main)] rounded cursor-pointer">
            <ChevronUp class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>
    </div>

    <!-- Expanded View -->
    <div
      v-else
      class="flex flex-col rounded-3xl border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] p-5 sm:p-6 overflow-hidden min-h-0"
      :class="compact ? 'gap-0 max-h-[50vh]' : 'gap-4 max-h-[70vh]'"
    >
      <!-- Header Section - always show for collapse control -->
      <div v-if="showExpandedHeader" class="flex flex-col sm:flex-row sm:items-start gap-4">
        <!-- Terminal Thumbnail Card - only when available -->
        <div
          v-if="showExpandedThumbnail"
          class="flex-shrink-0 relative group/thumb"
          @mouseenter="showTooltip"
          @mouseleave="hideTooltip"
        >
          <div
            class="w-[140px] h-[88px] sm:w-[150px] sm:h-[96px] rounded-xl overflow-hidden border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] cursor-pointer group-hover/thumb:border-[var(--text-brand)] transition-colors shadow-md"
            @click.stop="emit('openPanel')"
          >
            <!-- Live VNC View -->
            <VNCViewer
              v-if="showVncPreview"
              :session-id="sessionId"
              :enabled="true"
              :view-only="true"
              class="w-full h-full vnc-thumbnail"
            />
            <!-- Static Screenshot -->
            <img
              v-else-if="thumbnailUrl"
              :src="thumbnailUrl"
              alt="Computer view"
              class="w-full h-full object-cover"
            />
          </div>
          <!-- Expand Button -->
          <button
            @click.stop="emit('openPanel')"
            class="absolute bottom-2 right-2 w-7 h-7 rounded-lg bg-[#4a4a4a]/80 hover:bg-[#5a5a5a] flex items-center justify-center transition-colors"
          >
            <ArrowUpRight class="w-4 h-4 text-white" />
          </button>
        </div>

        <!-- Computer Info -->
        <div class="flex-1 min-w-0">
          <div class="flex items-start justify-between gap-4">
            <h2 class="text-lg sm:text-xl font-semibold text-[var(--text-primary)]">
              {{ $t("Pythinker's computer") }}
            </h2>
            <div class="flex items-center gap-3 flex-shrink-0 pt-0.5">
              <button
                type="button"
                @click.stop="emit('openPanel')"
                class="w-9 h-9 rounded-lg border border-black/10 dark:border-[var(--border-main)] bg-[var(--background-white-main)] flex items-center justify-center shadow-sm hover:bg-[var(--fill-tsp-gray-main)] cursor-pointer"
                aria-label="Open Pythinker's computer"
              >
                <Monitor class="w-5 h-5 text-[var(--icon-secondary)]" />
              </button>
              <button
                @click="toggleExpand"
                class="p-1 hover:bg-[var(--fill-tsp-gray-main)] rounded cursor-pointer"
              >
                <ChevronDown class="w-5 h-5 text-[var(--icon-tertiary)]" />
              </button>
            </div>
          </div>
          <div class="flex items-center gap-3 text-[var(--text-secondary)] mt-2">
            <div class="w-9 h-9 rounded-lg border border-black/10 dark:border-[var(--border-main)] bg-[var(--background-white-main)] flex items-center justify-center shadow-sm">
              <component :is="currentToolIcon" class="w-[18px] h-[18px] text-[var(--text-secondary)]" />
            </div>
            <span class="text-xs sm:text-sm">
              <span v-if="isAllCompleted" class="font-medium text-[var(--text-primary)]">
                {{ currentToolName }}
              </span>
              <span v-else>
                {{ $t('Pythinker is using') }}
                <span class="font-medium text-[var(--text-primary)]">{{ currentToolName }}</span>
              </span>
            </span>
          </div>
        </div>
      </div>

      <!-- Task Progress Card -->
      <div class="bg-[var(--fill-tsp-gray-main)] rounded-2xl p-5 sm:p-6 border border-black/5 dark:border-[var(--border-main)]">
        <!-- Card Header -->
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm sm:text-base font-semibold text-[var(--text-primary)]">{{ $t('Task progress') }}</h3>
          <div class="flex items-center gap-2">
            <span class="text-xs text-[var(--text-tertiary)]">{{ progressText }}</span>
            <button
              v-if="!showExpandedHeader"
              @click="toggleExpand"
              class="p-0.5 hover:bg-[var(--fill-tsp-gray-main)] rounded cursor-pointer"
            >
              <ChevronDown class="w-4 h-4 text-[var(--icon-tertiary)]" />
            </button>
          </div>
        </div>

        <!-- Task List -->
        <div class="flex flex-col max-h-[42vh] sm:max-h-[50vh] overflow-y-auto pr-1">
          <div
            v-for="step in steps"
            :key="step.id"
            class="flex items-start gap-2.5 py-2.5"
          >
            <!-- Checkmark -->
            <div class="flex-shrink-0 mt-0.5">
              <Check
                v-if="step.status === 'completed'"
                class="w-3.5 h-3.5 text-[#22c55e]"
                :stroke-width="2.5"
              />
              <div
                v-else-if="step.status === 'running'"
                class="w-3.5 h-3.5 rounded-full border-2 border-blue-400 bg-blue-100"
              ></div>
              <div v-else class="w-3.5 h-3.5 rounded-full border-2 border-gray-300"></div>
            </div>

            <!-- Task Text -->
            <span
              class="text-xs sm:text-sm leading-relaxed"
              :class="step.status === 'running' ? 'text-[var(--text-primary)] font-semibold' : 'text-[var(--text-primary)] font-medium'"
            >
              {{ step.description }}
            </span>
          </div>
        </div>
      </div>
    </div>
    <Teleport to="body">
      <Transition name="tooltip">
        <div
          v-if="tooltipVisible"
          ref="tooltipRef"
          class="tooltip-badge fixed inline-flex items-center gap-1.5 px-4 py-2 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] rounded-full text-sm font-medium whitespace-nowrap shadow-lg z-[6000] pointer-events-none"
          :style="tooltipStyle"
        >
          {{ $t("View Pythinker's computer") }}
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ChevronUp, ChevronDown, Check, Monitor, Terminal, Globe, FolderOpen, ArrowUpRight } from 'lucide-vue-next'
import type { PlanEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'
import VNCViewer from '@/components/VNCViewer.vue'

interface Props {
  plan?: PlanEventData
  isLoading: boolean
  isThinking: boolean
  showThumbnail?: boolean
  hideThumbnail?: boolean
  defaultExpanded?: boolean
  compact?: boolean
  thumbnailUrl?: string
  currentTool?: { name: string; function: string; functionArg?: string } | null
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
const shapes = ['circle', 'diamond', 'cube'] as const
type Shape = typeof shapes[number]
const currentShapeIndex = ref(0)
const currentShape = ref<Shape>('circle')
let shapeIntervalId: ReturnType<typeof setInterval> | null = null

// Check if all steps are completed
const isAllCompleted = computed(() => {
  return steps.value.length > 0 && steps.value.every(s => s.status === 'completed')
})

const isVisible = computed(() => {
  return props.plan && props.plan.steps.length > 0
})

// Idle state: not loading, not completed - agent is paused between steps
const isIdle = computed(() => {
  return !props.isLoading && !isAllCompleted.value && steps.value.length > 0
})

const steps = computed(() => props.plan?.steps ?? [])

const COMPUTER_TOOLS = new Set(['browser', 'shell', 'file', 'browser_agent', 'code_executor'])
const hasComputerActivity = computed(() => {
  const toolName = props.toolContent?.name || props.currentTool?.name || ''
  return COMPUTER_TOOLS.has(toolName)
})

// Prioritize VNC when liveVnc is enabled (shows live sandbox activity)
const showVncPreview = computed(() => (
  !!props.sessionId &&
  !!props.liveVnc &&
  hasComputerActivity.value
))

const progressText = computed(() => {
  const completed = steps.value.filter(s => s.status === 'completed').length
  const total = steps.value.length
  return `${completed} / ${total}`
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

const showCollapsedThumbnail = computed(() => {
  if (props.hideThumbnail) return false
  if (!hasComputerActivity.value) return false
  return props.showThumbnail || (isAllCompleted.value && !!props.thumbnailUrl)
})

const showExpandedThumbnail = computed(() => {
  if (props.hideThumbnail) return false
  if (!hasComputerActivity.value) return false
  return props.showThumbnail || !!props.thumbnailUrl || !!props.sessionId
})

const showExpandedHeader = computed(() => !props.compact && hasComputerActivity.value)

// Get current tool name for display
const currentToolName = computed(() => {
  if (isAllCompleted.value) return 'Task completed'
  if (props.currentTool?.function) return props.currentTool.function
  return 'Terminal'
})

// Get icon for current tool
const currentToolIcon = computed(() => {
  if (isAllCompleted.value) return Check
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
  }, 800)
}

const stopShapeAnimation = () => {
  if (shapeIntervalId) {
    clearInterval(shapeIntervalId)
    shapeIntervalId = null
  }
}

// Start/stop shape animation based on thinking state
watch(() => props.isThinking, (thinking) => {
  if (thinking) {
    startShapeAnimation()
  } else {
    stopShapeAnimation()
  }
}, { immediate: true })

onMounted(() => {
  if (props.isThinking) {
    startShapeAnimation()
  }
  window.addEventListener('scroll', handleScroll, true)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  stopShapeAnimation()
  window.removeEventListener('scroll', handleScroll, true)
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
/* Thinking shape animation */
.status-dot {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  border: 2px solid var(--text-tertiary);
  flex-shrink: 0;
}

.status-dot-active {
  border-color: #9c7dff;
  background: rgba(156, 125, 255, 0.2);
}

.status-dot-idle {
  border-color: var(--text-tertiary);
  background: transparent;
}

/* Terminal cursor blink */
.terminal-cursor {
  display: inline-block;
  width: 6px;
  height: 10px;
  background: #22c55e;
  animation: cursor-blink 1s step-end infinite;
  margin-left: 2px;
  vertical-align: middle;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.fetching-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.fetching-dot {
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: var(--text-tertiary);
  animation: fetching-dot 1.1s ease-in-out infinite;
}

.fetching-dot:nth-child(2) {
  animation-delay: 0.15s;
}

.fetching-dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes fetching-dot {
  0%, 80%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  40% {
    transform: translateY(-2px);
    opacity: 1;
  }
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

/* VNC Thumbnail scaling */
.vnc-thumbnail :deep(canvas) {
  width: 100% !important;
  height: 100% !important;
  object-fit: contain;
  cursor: pointer !important;
  pointer-events: none;
  margin: 0 !important;
  display: block;
}

.vnc-thumbnail {
  cursor: pointer;
  pointer-events: none;
  border-radius: 12px;
  overflow: hidden;
}

.vnc-thumbnail :deep(.vnc-container) {
  width: 100% !important;
  height: 100% !important;
  margin: 0 !important;
  display: flex !important;
  align-items: center;
  justify-content: center;
  overflow: hidden !important;
  background: #0f0f0f;
}

.vnc-thumbnail :deep(.vnc-container > div) {
  width: 100% !important;
  height: 100% !important;
  margin: 0 !important;
  display: block;
}
</style>
