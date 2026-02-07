<template>
  <div v-if="isVisible" class="task-progress-bar" :class="{ 'is-expanded': isExpanded }">
    <!-- Expanded View - positioned absolutely to overlay upward -->
    <Transition name="expand-up">
      <div v-if="isExpanded" class="progress-bar-expanded">
        <!-- Header (hidden when panel is open above) -->
        <div v-if="!hideExpandedHeader" class="expanded-header">
          <div class="flex items-start gap-4">
            <!-- Tool/VNC Mini Preview -->
            <VncMiniPreview
              v-if="showExpandedThumbnail && sessionId"
              :session-id="sessionId"
              :enabled="true"
              :tool-name="props.currentTool?.name"
              :tool-function="props.currentTool?.function"
              :is-active="isToolRunning"
              :content-preview="contentPreview"
              :file-path="filePath"
              :is-initializing="props.isInitializing"
              :tool-content="props.toolContent || undefined"
              :search-results="searchResults"
              :search-query="searchQuery"
              :generic-result="genericResult"
              size="lg"
              @click="emit('openPanel')"
            />

            <!-- Title and Tool Info -->
            <div class="flex-1 min-w-0">
              <h2 class="text-[16px] font-semibold text-gray-900 dark:text-[#f0f0f0] mb-2.5">
                {{ $t("Pythinker's computer") }}
              </h2>

              <div class="flex items-center gap-2.5">
                <div class="tool-icon-badge">
                  <component :is="currentToolIcon" class="w-3.5 h-3.5" />
                </div>
                <span class="text-[13px] text-gray-500 dark:text-[#909090]">
                  Using <span class="text-gray-800 dark:text-[#d0d0d0] font-medium">{{ currentToolDisplayName }}</span>
                </span>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex items-center gap-1 flex-shrink-0">
              <button
                type="button"
                @click.stop="emit('openPanel')"
                class="action-btn"
              >
                <MonitorPlay class="w-4 h-4" />
              </button>
              <button @click="toggleExpand" class="action-btn">
                <ChevronDown class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <!-- Task Progress Section -->
        <div class="expanded-content">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-[13px] font-semibold text-gray-700 dark:text-[#a0a0a0] uppercase tracking-wide">{{ $t('Task progress') }}</h3>
            <div class="flex items-center gap-2">
              <div class="progress-pill-lg">
                <span class="text-[13px] font-semibold tabular-nums">{{ completedCount }}</span>
                <span class="text-[11px] text-gray-400 dark:text-[#505050] mx-0.5">/</span>
                <span class="text-[13px] font-semibold tabular-nums">{{ totalCount }}</span>
              </div>
              <button v-if="hideExpandedHeader" @click="toggleExpand" class="action-btn">
                <ChevronDown class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Task List -->
          <div class="task-list custom-scrollbar">
            <div
              v-for="(step, index) in steps"
              :key="step.id"
              class="task-item"
              :class="{
                'task-completed': step.status === 'completed',
                'task-running': step.status === 'running',
                'task-pending': step.status === 'pending'
              }"
            >
              <!-- Connector line -->
              <div v-if="index < steps.length - 1" class="task-connector" :class="{ 'connector-active': step.status === 'completed' }"></div>

              <div class="task-indicator">
                <!-- 3D Flip Container for completion animation -->
                <div
                  class="indicator-flip-container"
                  :class="{
                    'is-flipped': step.status === 'completed',
                    'just-completed': recentlyCompletedIds.has(step.id)
                  }"
                >
                  <!-- Front face: running/pending state -->
                  <div class="indicator-face indicator-front">
                    <div
                      v-if="step.status === 'running'"
                      class="indicator-running"
                      :class="`shape-${currentShape}`"
                    ></div>
                    <div v-else class="indicator-pending">
                      <span class="text-[10px] font-medium">{{ index + 1 }}</span>
                    </div>
                  </div>
                  <!-- Back face: completed checkmark -->
                  <div class="indicator-face indicator-back">
                    <div class="indicator-complete">
                      <Check class="w-3 h-3 text-white" :stroke-width="3" />
                    </div>
                  </div>
                </div>
                <!-- Celebration ring effect -->
                <div
                  v-if="recentlyCompletedIds.has(step.id)"
                  class="celebration-ring"
                ></div>
              </div>

              <span class="task-description">
                {{ step.description }}
              </span>
            </div>
          </div>

          <!-- Timer -->
          <div v-if="taskStartTime" class="timer-section">
            <div class="flex items-center gap-2">
              <div class="timer-icon">
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
              </div>
              <span class="text-[11px] text-gray-500 dark:text-[#707070] uppercase tracking-wider">Elapsed</span>
            </div>
            <span class="timer-value">{{ formattedElapsedTime }}</span>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Collapsed View - always in DOM to maintain space -->
    <div class="collapsed-wrapper" :class="[showCollapsedThumbnail && sessionId ? 'has-thumbnail' : '', { 'invisible': isExpanded }]">
      <!-- Floating Live VNC Mini Preview -->
      <div
        v-if="showCollapsedThumbnail && sessionId"
        class="vnc-thumbnail-floating"
        @mouseenter="showTooltip"
        @mouseleave="scheduleHideTooltip"
      >
        <VncMiniPreview
          :session-id="sessionId"
          :enabled="true"
          :tool-name="props.currentTool?.name"
          :tool-function="props.currentTool?.function"
          :is-active="isToolRunning"
          :content-preview="contentPreview"
          :file-path="filePath"
          :is-initializing="props.isInitializing"
          :tool-content="props.toolContent || undefined"
          :search-results="searchResults"
          :search-query="searchQuery"
          :generic-result="genericResult"
          size="md"
          @click="emit('openPanel')"
        />
      </div>

      <!-- Compact Progress Bar -->
      <div
        class="progress-bar-collapsed"
        :class="showCollapsedThumbnail && sessionId ? 'has-thumbnail' : ''"
        @click="toggleExpand"
      >
        <!-- Status indicator -->
        <div class="flex-shrink-0">
          <div v-if="isAllCompleted" class="status-complete">
            <Check class="w-3.5 h-3.5 text-white" :stroke-width="2.5" />
          </div>
          <div
            v-else
            class="status-morph"
            :class="[
              isIdle ? 'status-morph-idle' : 'status-morph-active',
              `shape-${currentShape}`
            ]"
          ></div>
        </div>

        <!-- Content -->
        <div class="flex-1 min-w-0 flex flex-col gap-0.5">
          <!-- Flip Board Animation for Task Description -->
          <div class="flip-board-container">
            <TransitionGroup name="flip-board" tag="div" class="flip-board-wrapper">
              <span
                :key="currentTaskDescription"
                class="flip-board-text text-[13px] font-medium text-gray-900 dark:text-[#f0f0f0] truncate"
              >
                {{ currentTaskDescription }}
              </span>
            </TransitionGroup>
          </div>
          <div class="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-[#808080]">
            <span v-if="taskStartTime" class="font-mono tabular-nums">{{ formattedElapsedTime }}</span>
            <span v-if="taskStartTime && (currentToolDisplayName || props.isThinking || props.isLoading)" class="text-gray-300 dark:text-[#404040]">·</span>
            <span v-if="isToolRunning" class="truncate">{{ currentToolActionLabel.toLowerCase() }}</span>
            <span v-else-if="props.isThinking" class="text-blue-500 dark:text-blue-400">Thinking</span>
            <span v-else-if="props.currentTool && currentToolDisplayName && !isAllCompleted" class="truncate">{{ currentToolActionLabel.toLowerCase() }}</span>
            <span v-else-if="props.isLoading && !isAllCompleted">processing</span>
          </div>
        </div>

        <!-- Progress pill & expand -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <div class="progress-pill">
            <span class="text-[12px] font-medium tabular-nums">{{ completedCount }}</span>
            <span class="text-[10px] text-gray-400 dark:text-[#606060]">/</span>
            <span class="text-[12px] font-medium tabular-nums">{{ totalCount }}</span>
          </div>
          <button @click.stop="toggleExpand" class="expand-btn">
            <ChevronUp class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>


    <Teleport to="body">
      <Transition name="tooltip">
        <div
          v-if="tooltipVisible"
          ref="tooltipRef"
          class="tooltip-badge tooltip-clickable"
          :style="tooltipStyle"
          @mouseenter="cancelHideTooltip"
          @mouseleave="scheduleHideTooltip"
          @click="handleTooltipClick"
        >
          {{ $t("View Pythinker's computer") }}
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ChevronUp, ChevronDown, Check, MonitorPlay, Terminal, Globe, FolderOpen } from 'lucide-vue-next'
import VncMiniPreview from './VncMiniPreview.vue'
import type { PlanEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'

interface Props {
  plan?: PlanEventData
  isLoading: boolean
  isThinking: boolean
  /** Whether to show the VNC thumbnail */
  showThumbnail?: boolean
  defaultExpanded?: boolean
  compact?: boolean
  /** Session ID for live VNC mini preview */
  sessionId?: string
  currentTool?: { name: string; function: string; functionArg?: string; status?: string; icon?: any } | null
  toolContent?: ToolContent | null
  /** Hide the expanded header (when panel is already showing above) */
  hideExpandedHeader?: boolean
  /** Whether the sandbox environment is initializing */
  isInitializing?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showThumbnail: false,
  defaultExpanded: false,
  compact: false,
  sessionId: '',
  currentTool: null,
  hideExpandedHeader: false,
  isInitializing: false
})

const emit = defineEmits<{
  (e: 'openPanel'): void
  /** Emitted when tasks complete to request a final screenshot capture */
  (e: 'requestRefresh'): void
}>()

const isToolRunning = computed(() => {
  return props.currentTool?.status === 'calling' || props.currentTool?.status === 'running'
})

// Computed: show thumbnails in collapsed/expanded view
const showCollapsedThumbnail = computed(() => props.showThumbnail)
const showExpandedThumbnail = computed(() => props.showThumbnail)

// Check if all tasks are completed
const isAllCompleted = computed(() => {
  if (!props.plan?.steps) return false
  return props.plan.steps.every(step => step.status === 'completed')
})


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

  // Always position above the element with consistent spacing
  const tooltipHeight = tooltipRect?.height || 36
  const spacing = 8
  let top = rect.top - tooltipHeight - spacing

  // Ensure tooltip stays within viewport
  if (tooltipRect) {
    const halfWidth = tooltipRect.width / 2
    left = Math.min(window.innerWidth - padding - halfWidth, Math.max(padding + halfWidth, left))
    // If tooltip would go above viewport, position below element instead
    if (top < padding) {
      top = rect.bottom + spacing
    }
  }

  tooltipTop.value = top
  tooltipLeft.value = left
}

const showTooltip = (event: MouseEvent) => {
  cancelHideTooltip()
  const target = event.currentTarget as HTMLElement | null
  if (!target) return
  const rect = target.getBoundingClientRect()
  tooltipAnchor.value = rect
  // Initial position - will be refined by updateTooltipPosition
  tooltipTop.value = rect.top - 44
  tooltipLeft.value = rect.left + rect.width / 2
  tooltipVisible.value = true
  nextTick(updateTooltipPosition)
}

let hideTooltipTimeout: ReturnType<typeof setTimeout> | null = null

const hideTooltip = () => {
  tooltipVisible.value = false
}

const scheduleHideTooltip = () => {
  hideTooltipTimeout = setTimeout(() => {
    hideTooltip()
  }, 100)
}

const cancelHideTooltip = () => {
  if (hideTooltipTimeout) {
    clearTimeout(hideTooltipTimeout)
    hideTooltipTimeout = null
  }
}

const handleTooltipClick = () => {
  hideTooltip()
  emit('openPanel')
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

// Track recently completed task IDs for flip animation
const recentlyCompletedIds = ref<Set<string>>(new Set())
const previousStepStatuses = ref<Map<string, string>>(new Map())

const completedCount = computed(() => steps.value.filter(s => s.status === 'completed').length)
const totalCount = computed(() => steps.value.length)

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

// Get current tool name for display (use friendly names from mapping)
const currentToolDisplayName = computed(() => {
  if (props.currentTool?.name) return props.currentTool.name
  if (isAllCompleted.value) return 'Terminal'
  return 'Tool'
})

const currentToolActionLabel = computed(() => {
  if (props.currentTool?.function) return props.currentTool.function
  return isToolRunning.value ? 'Working' : 'Idle'
})

// Get icon for current tool
const currentToolIcon = computed(() => {
  if (props.currentTool?.icon) return props.currentTool.icon
  const toolName = props.currentTool?.name?.toLowerCase() || ''
  if (toolName.includes('browser') || toolName.includes('web') || toolName.includes('search')) return Globe
  if (toolName.includes('file') || toolName.includes('editor')) return FolderOpen
  return Terminal
})

// Extract content preview from toolContent (for mini preview)
const contentPreview = computed(() => {
  if (!props.toolContent) return ''

  const toolName = props.toolContent?.name || ''
  const toolFunc = props.toolContent?.function || ''
  const isShellOrCode = toolName.includes('shell') || toolName.includes('code') ||
                        toolFunc.includes('shell') || toolFunc.includes('code')

  // Shell/Code output - check multiple sources
  if (isShellOrCode) {
    // Get command
    const command = props.toolContent.args?.command || props.toolContent.command || ''

    // Check for stdout/stderr output first
    const stdout = props.toolContent.stdout || props.toolContent.content?.stdout || ''
    const stderr = props.toolContent.stderr || props.toolContent.content?.stderr || ''

    // Check for console output (array format)
    const consoleOutput = props.toolContent.content?.console
    if (consoleOutput && Array.isArray(consoleOutput)) {
      return consoleOutput.map((e: any) => {
        const ps1 = e.ps1 ? `${e.ps1} ` : '$ '
        return `${ps1}${e.command || ''}\n${e.output || ''}`
      }).join('\n').slice(0, 500)
    }

    // Build output from available sources
    let output = ''
    if (command) output += `$ ${command}\n`
    if (stdout) output += stdout
    if (stderr) output += `\n[stderr]\n${stderr}`

    if (output.trim()) {
      return output.slice(0, 500)
    }

    // Show command during execution
    if (command) {
      return `$ ${command}`
    }
  }

  // File content
  if (props.toolContent.args?.content) {
    return String(props.toolContent.args.content).slice(0, 500)
  }
  if (props.toolContent.content?.content) {
    return String(props.toolContent.content.content).slice(0, 500)
  }

  // Generic stdout output
  if (props.toolContent.stdout) {
    return String(props.toolContent.stdout).slice(0, 500)
  }
  if (props.toolContent.content?.console) {
    const console = props.toolContent.content.console
    if (typeof console === 'string') {
      return String(console).slice(0, 500)
    }
  }

  return ''
})

// Extract file path from toolContent
const filePath = computed(() => {
  if (!props.toolContent) return ''
  return props.toolContent.args?.file || props.toolContent.file_path || ''
})

// Extract search results from toolContent (for search/info tools)
const searchResults = computed(() => {
  if (!props.toolContent) return []
  return props.toolContent.content?.results || []
})

// Extract search query from toolContent
const searchQuery = computed(() => {
  if (!props.toolContent) return ''
  return props.toolContent.args?.query || ''
})

// Extract generic result from toolContent (for MCP/generic tools)
const genericResult = computed(() => {
  if (!props.toolContent) return undefined
  const toolName = props.toolContent.name || ''
  // Return result for MCP tools or tools without specific view
  if (toolName === 'mcp' || toolName.includes('mcp')) {
    return props.toolContent.content?.result || props.toolContent.content
  }
  return undefined
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

// Watch for completion - emit event for parent to capture final screenshot
watch(isAllCompleted, (completed) => {
  if (completed) {
    stopShapeAnimation()
    stopTimer()
    emit('requestRefresh')
  }
})

// Watch for individual task completions to trigger flip animation
watch(
  () => props.plan?.steps,
  (newSteps) => {
    if (!newSteps) return

    newSteps.forEach((step) => {
      const prevStatus = previousStepStatuses.value.get(step.id)
      const currentStatus = step.status

      // Detect transition to completed
      if (currentStatus === 'completed' && prevStatus !== 'completed') {
        recentlyCompletedIds.value.add(step.id)

        // Remove from recently completed after animation duration
        setTimeout(() => {
          recentlyCompletedIds.value.delete(step.id)
        }, 1200) // Match animation duration
      }

      // Update tracked status
      previousStepStatuses.value.set(step.id, currentStatus)
    })
  },
  { deep: true, immediate: true }
)

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
/* ===== BASE CONTAINER ===== */
.task-progress-bar {
  position: relative;
}

.task-progress-bar.is-expanded {
  position: relative;
}

/* ===== COLLAPSED VIEW ===== */
.collapsed-wrapper {
  position: relative;
}

.collapsed-wrapper.has-thumbnail {
  margin-top: 100px; /* Space for floating VNC preview (144px width @ 16:10 = 90px height + gap) */
}

.progress-bar-collapsed {
  background: var(--bolt-elements-bg-depth-1);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 14px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.progress-bar-collapsed:hover {
  background: var(--bolt-elements-bg-depth-2);
  border-color: var(--bolt-elements-borderColorActive);
}

/* ===== STATUS INDICATORS ===== */
.status-complete {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.35);
}

.status-morph {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  transition: all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative;
}

.status-morph-active {
  background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%);
  box-shadow:
    0 0 0 1.5px rgba(59, 130, 246, 0.15),
    0 1px 6px rgba(59, 130, 246, 0.3);
  animation: morph-pulse 2s ease-in-out infinite;
}

.status-morph-idle {
  border: 2px solid var(--bolt-elements-borderColor);
  background: transparent;
}

/* Shape transformations */
.status-morph.shape-circle {
  border-radius: 50%;
  transform: rotate(0deg) scale(1);
}

.status-morph.shape-square {
  border-radius: 3px;
  transform: rotate(0deg) scale(0.9);
}

.status-morph.shape-diamond {
  border-radius: 3px;
  transform: rotate(45deg) scale(0.75);
}

.status-morph.shape-cube {
  border-radius: 4px;
  transform: rotate(90deg) scale(0.85);
}

@keyframes morph-pulse {
  0%, 100% {
    box-shadow:
      0 0 0 1.5px rgba(59, 130, 246, 0.15),
      0 1px 6px rgba(59, 130, 246, 0.3);
  }
  50% {
    box-shadow:
      0 0 0 3px rgba(59, 130, 246, 0.1),
      0 3px 12px rgba(59, 130, 246, 0.25);
  }
}

/* ===== PROGRESS PILL ===== */
.progress-pill {
  display: flex;
  align-items: baseline;
  gap: 1px;
  padding: 4px 10px;
  background: var(--bolt-elements-bg-depth-4);
  border-radius: 20px;
  color: var(--bolt-elements-textSecondary);
}

.progress-pill-lg {
  display: flex;
  align-items: baseline;
  padding: 5px 12px;
  background: var(--bolt-elements-item-backgroundAccent);
  border: 1px solid var(--bolt-elements-borderColorActive);
  border-radius: 20px;
  color: var(--bolt-elements-item-contentAccent);
}

/* ===== EXPAND BUTTON ===== */
.expand-btn {
  padding: 6px;
  border-radius: 8px;
  color: var(--bolt-elements-textTertiary);
  transition: all 0.15s ease;
}

.expand-btn:hover {
  background: var(--bolt-elements-item-backgroundActive);
  color: var(--bolt-elements-textSecondary);
}

/* ===== VNC THUMBNAILS ===== */
.vnc-thumbnail-floating {
  position: absolute;
  left: 12px;
  bottom: 8px;
  z-index: 10;
}

.progress-bar-collapsed.has-thumbnail {
  padding-left: 160px; /* Space for 144px wide VNC preview + gap */
}

.vnc-thumbnail-expanded {
  flex-shrink: 0;
  width: 150px;
  height: 86px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.vnc-thumbnail-expanded:hover {
  border-color: var(--bolt-elements-borderColorActive);
}

.vnc-thumbnail-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.vnc-thumbnail-floating:hover .vnc-thumbnail-overlay,
.vnc-thumbnail-expanded:hover .vnc-thumbnail-overlay {
  opacity: 1;
}

/* ===== EXPANDED VIEW ===== */
.progress-bar-expanded {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  border: 1px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-1);
  overflow: hidden;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.12);
  max-height: 70vh;
}

.expanded-header {
  padding: 16px 18px;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
}

.expanded-content {
  padding: 16px 18px;
}

/* ===== TOOL ICON BADGE ===== */
.tool-icon-badge {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--bolt-elements-item-backgroundAccent);
  border: 1px solid var(--bolt-elements-borderColorActive);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bolt-elements-item-contentAccent);
}

/* ===== ACTION BUTTONS ===== */
.action-btn {
  padding: 8px;
  border-radius: 8px;
  color: var(--bolt-elements-textTertiary);
  transition: all 0.15s ease;
}

.action-btn:hover {
  background: var(--bolt-elements-item-backgroundActive);
  color: var(--bolt-elements-textSecondary);
}

/* ===== TASK LIST ===== */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow-y: auto;
  max-height: 50vh;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  position: relative;
}

.task-item:first-child {
  padding-top: 0;
}

.task-item:last-child {
  padding-bottom: 0;
}

/* Connector line between tasks */
.task-connector {
  position: absolute;
  left: 11px;
  top: 32px;
  bottom: -10px;
  width: 2px;
  background: var(--bolt-elements-borderColor);
  border-radius: 1px;
}

.task-connector.connector-active {
  background: linear-gradient(to bottom, var(--function-success), var(--bolt-elements-borderColor));
}

/* Task indicators */
.task-indicator {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
  perspective: 600px;
}

/* 3D Flip Container */
.indicator-flip-container {
  width: 22px;
  height: 22px;
  position: relative;
  transform-style: preserve-3d;
  transition: transform 0.6s cubic-bezier(0.4, 0.0, 0.2, 1);
}

.indicator-flip-container.is-flipped {
  transform: rotateY(180deg);
}

/* Celebration bounce when just completed */
.indicator-flip-container.just-completed {
  animation: completion-bounce 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) 0.5s;
}

@keyframes completion-bounce {
  0% { transform: rotateY(180deg) scale(1); }
  40% { transform: rotateY(180deg) scale(1.25); }
  70% { transform: rotateY(180deg) scale(0.95); }
  100% { transform: rotateY(180deg) scale(1); }
}

/* Flip faces */
.indicator-face {
  position: absolute;
  inset: 0;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.indicator-front {
  transform: rotateY(0deg);
}

.indicator-back {
  transform: rotateY(180deg);
}

/* Celebration ring effect */
.celebration-ring {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  pointer-events: none;
  animation: celebration-pulse 0.8s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

@keyframes celebration-pulse {
  0% {
    box-shadow:
      0 0 0 0 rgba(34, 197, 94, 0.6),
      0 0 0 0 rgba(34, 197, 94, 0.4);
    opacity: 1;
  }
  50% {
    box-shadow:
      0 0 0 6px rgba(34, 197, 94, 0.3),
      0 0 0 12px rgba(34, 197, 94, 0.1);
    opacity: 0.8;
  }
  100% {
    box-shadow:
      0 0 0 10px rgba(34, 197, 94, 0),
      0 0 0 18px rgba(34, 197, 94, 0);
    opacity: 0;
  }
}

.indicator-complete {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(34, 197, 94, 0.3);
}

/* Add glow to completed indicator when just flipped */
.indicator-flip-container.just-completed .indicator-complete {
  animation: complete-glow 1s ease-out forwards;
}

@keyframes complete-glow {
  0% {
    box-shadow:
      0 2px 6px rgba(34, 197, 94, 0.3),
      0 0 20px rgba(34, 197, 94, 0.5);
  }
  100% {
    box-shadow: 0 2px 6px rgba(34, 197, 94, 0.3);
  }
}

.indicator-running {
  width: 22px;
  height: 22px;
  background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%);
  transition: all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow:
    0 0 0 3px rgba(59, 130, 246, 0.12),
    0 2px 8px rgba(59, 130, 246, 0.3);
  animation: indicator-pulse 2s ease-in-out infinite;
}

.indicator-running.shape-circle {
  border-radius: 50%;
}

.indicator-running.shape-square {
  border-radius: 5px;
}

.indicator-running.shape-diamond {
  border-radius: 5px;
  transform: rotate(45deg) scale(0.85);
}

.indicator-running.shape-cube {
  border-radius: 6px;
  transform: rotate(90deg) scale(0.9);
}

@keyframes indicator-pulse {
  0%, 100% {
    box-shadow:
      0 0 0 3px rgba(59, 130, 246, 0.12),
      0 2px 8px rgba(59, 130, 246, 0.3);
  }
  50% {
    box-shadow:
      0 0 0 5px rgba(59, 130, 246, 0.08),
      0 4px 12px rgba(59, 130, 246, 0.25);
  }
}

.indicator-pending {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bolt-elements-textTertiary);
}

/* Task description */
.task-description {
  font-size: 14px;
  line-height: 1.5;
  padding-top: 2px;
  flex: 1;
}

.task-completed .task-description {
  color: var(--bolt-elements-textSecondary);
}

.task-running .task-description {
  color: var(--bolt-elements-textPrimary);
  font-weight: 500;
}

.task-pending .task-description {
  color: var(--bolt-elements-textTertiary);
}

/* ===== TIMER SECTION ===== */
.timer-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--bolt-elements-borderColor);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.timer-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--bolt-elements-bg-depth-4);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bolt-elements-textTertiary);
}

.timer-value {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace;
  font-size: 14px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
  letter-spacing: 0.02em;
}

/* ===== TOOLTIP ===== */
.tooltip-badge {
  position: fixed;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--Tooltips-main);
  color: #ffffff;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  z-index: 12000;
  pointer-events: none;
  transform: translateX(-50%);
  will-change: opacity, transform;
}

.tooltip-badge.tooltip-clickable {
  pointer-events: auto;
  cursor: pointer;
  transition: background 0.15s ease;
}

.tooltip-badge.tooltip-clickable:hover {
  background: var(--Tooltips-hover, #333);
}

.tooltip-enter-active,
.tooltip-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}

.tooltip-enter-from,
.tooltip-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(6px);
}

.tooltip-enter-to,
.tooltip-leave-from {
  opacity: 1;
  transform: translateX(-50%);
}

/* ===== CUSTOM SCROLLBAR ===== */
.custom-scrollbar::-webkit-scrollbar {
  width: 5px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.15);
}

:global(.dark) .custom-scrollbar::-webkit-scrollbar-thumb,
:global([data-theme='dark']) .custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
}

:global(.dark) .custom-scrollbar::-webkit-scrollbar-thumb:hover,
:global([data-theme='dark']) .custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.15);
}

/* ===== EXPAND TRANSITION ===== */
.expand-up-enter-active,
.expand-up-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.expand-up-enter-from,
.expand-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

.expand-up-enter-to,
.expand-up-leave-from {
  opacity: 1;
  transform: translateY(0);
}

/* ===== FLIP BOARD ANIMATION ===== */
.flip-board-container {
  position: relative;
  height: 20px;
  overflow: hidden;
  perspective: 400px;
}

.flip-board-wrapper {
  position: relative;
  height: 100%;
  width: 100%;
}

.flip-board-text {
  display: block;
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  width: 100%;
  transform-origin: center bottom;
  backface-visibility: hidden;
}

/* Flip board enter animation - flips down from top */
.flip-board-enter-active {
  animation: flip-board-in 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
  z-index: 2;
}

/* Flip board leave animation - flips down and out */
.flip-board-leave-active {
  animation: flip-board-out 0.4s cubic-bezier(0.55, 0.085, 0.68, 0.53) forwards;
  z-index: 1;
}

@keyframes flip-board-in {
  0% {
    transform: rotateX(-90deg) translateY(-50%);
    opacity: 0;
  }
  40% {
    opacity: 1;
  }
  100% {
    transform: rotateX(0deg) translateY(0);
    opacity: 1;
  }
}

@keyframes flip-board-out {
  0% {
    transform: rotateX(0deg) translateY(0);
    opacity: 1;
  }
  60% {
    opacity: 0.5;
  }
  100% {
    transform: rotateX(90deg) translateY(50%);
    opacity: 0;
  }
}

/* Move animation for absolute positioning */
.flip-board-move {
  transition: none;
}
</style>
