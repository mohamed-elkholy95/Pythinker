<template>
  <div v-if="isVisible" class="task-progress-bar" :class="{ 'is-expanded': isExpanded }">
    <!-- Expanded View - positioned absolutely to overlay upward -->
    <Transition name="expand-up">
      <div v-if="isExpanded" class="progress-bar-expanded">
        <!-- Header (hidden when panel is open above) -->
        <div v-if="!hideExpandedHeader" class="expanded-header">
          <div class="flex items-start gap-4">
            <!-- Tool/Live Mini Preview -->
            <LiveMiniPreview
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
              :is-summary-streaming="props.isSummaryStreaming"
              :summary-stream-text="props.summaryStreamText"
              :final-report-text="props.finalReportText"
              :is-session-complete="props.isSessionComplete"
              :replay-screenshot-url="props.replayScreenshotUrl"
              :plan-presentation-text="props.planPresentationText"
              :is-plan-streaming="props.isPlanStreaming"
              size="lg"
              @click="emit('openPanel')"
            />

            <!-- Title and Tool Info -->
            <div class="flex-1 min-w-0">
              <h2 class="text-[16px] font-semibold text-gray-900 dark:text-[var(--text-primary)] mb-2.5">
                {{ $t("Pythinker's computer") }}
              </h2>

              <div class="flex items-center gap-2.5">
                <div class="tool-icon-badge">
                  <component :is="currentToolIcon" class="w-3.5 h-3.5" />
                </div>
                <span class="text-[13px] text-gray-500 dark:text-[var(--text-secondary)]">
                  Using <span class="text-gray-800 dark:text-[var(--text-primary)] font-medium">{{ currentToolDisplayName }}</span>
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
            <h3 class="text-[13px] font-semibold text-gray-700 dark:text-[var(--text-secondary)] uppercase tracking-wide">{{ $t('Task progress') }}</h3>
            <div class="flex items-center gap-2">
              <div class="progress-pill-lg">
                <span class="text-[13px] font-semibold tabular-nums">{{ currentCount }}</span>
                <span class="text-[11px] text-gray-400 dark:text-[var(--text-tertiary)] mx-0.5">/</span>
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
              <div class="task-left-rail">
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
                      >
                        <span class="indicator-running-dot" aria-hidden="true"></span>
                      </div>
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

                <div
                  v-if="index < steps.length - 1"
                  class="task-timeline-line"
                  :class="{ 'connector-active': step.status === 'completed' }"
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
              <span class="text-[11px] text-gray-500 dark:text-[var(--text-tertiary)] uppercase tracking-wider">Elapsed</span>
            </div>
            <span class="timer-value">{{ formattedElapsedTime }}</span>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Collapsed View - always in DOM to maintain space -->
    <div class="collapsed-wrapper" :class="[showCollapsedThumbnail && sessionId ? 'has-thumbnail' : '', { 'invisible': isExpanded }]">
      <!-- Floating Live Mini Preview -->
      <div
        v-if="showCollapsedThumbnail && sessionId && !isExpanded"
        class="live-preview-thumbnail-floating"
        @mouseenter="showTooltip"
        @mouseleave="scheduleHideTooltip"
      >
        <LiveMiniPreview
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
          :is-summary-streaming="props.isSummaryStreaming"
          :summary-stream-text="props.summaryStreamText"
          :final-report-text="props.finalReportText"
          :is-session-complete="props.isSessionComplete"
          :replay-screenshot-url="props.replayScreenshotUrl"
          :plan-presentation-text="props.planPresentationText"
          :is-plan-streaming="props.isPlanStreaming"
          size="md"
          @click="emit('openPanel')"
        />
      </div>

      <!-- Compact Progress Bar (Pythinker-style: check + description + counter + chevron) -->
      <div
        class="progress-bar-collapsed"
        :class="[showCollapsedThumbnail && sessionId ? 'has-thumbnail' : '', { 'completed-state': isAllCompleted }]"
        @click="toggleExpand"
      >
        <!-- Status icon -->
        <div
          class="collapsed-status-icon"
          :class="{ 'collapsed-status-icon-complete': isAllCompleted }"
        >
          <Check
            v-if="isAllCompleted"
            class="collapsed-complete-check"
            :size="16"
            :stroke-width="2.5"
          />
          <PlannerActivityIndicator v-else-if="steps.some(s => s.status === 'running')" class="collapsed-thinking-indicator" />
          <span v-else class="collapsed-pending-num">{{ currentCount }}</span>
        </div>

        <!-- Task description -->
        <div class="flex-1 min-w-0">
          <div class="flip-board-container">
            <TransitionGroup name="flip-board" tag="div" class="flip-board-wrapper">
              <span
                :key="currentTaskDescription"
                class="flip-board-text collapsed-task-text"
              >
                {{ currentTaskDescription }}
              </span>
            </TransitionGroup>
          </div>
        </div>

        <!-- Progress counter + chevron -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="collapsed-counter">{{ currentCount }} / {{ totalCount }}</span>
          <button @click.stop="toggleExpand" class="expand-btn" aria-label="Toggle task details">
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
import { ref, computed, onMounted, onUnmounted, watch, nextTick, type Component } from 'vue'
import { ChevronUp, ChevronDown, Check, MonitorPlay, Terminal, Globe, FolderOpen } from 'lucide-vue-next'
import LiveMiniPreview from './LiveMiniPreview.vue'
import PlannerActivityIndicator from '@/components/ui/PlannerActivityIndicator.vue'
import type { PlanEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'
import { useStreamingPresentationState } from '@/composables/useStreamingPresentationState'
import { useElapsedTimer } from '@/composables/useElapsedTimer'
import { extractToolPreview } from '@/utils/toolPreviewFormatter'

interface Props {
  plan?: PlanEventData
  isLoading: boolean
  isThinking: boolean
  /** Whether to show the live preview thumbnail */
  showThumbnail?: boolean
  defaultExpanded?: boolean
  compact?: boolean
  /** Session ID for live mini preview */
  sessionId?: string
  currentTool?: { name: string; function: string; functionArg?: string; status?: string; icon?: Component | null } | null
  toolContent?: ToolContent | null
  /** Hide the expanded header (when panel is already showing above) */
  hideExpandedHeader?: boolean
  /** Whether the sandbox environment is initializing */
  isInitializing?: boolean
  /** Whether summary is currently streaming */
  isSummaryStreaming?: boolean
  /** Live summary stream text */
  summaryStreamText?: string
  /** Persisted final report content shown after summary streaming ends */
  finalReportText?: string
  /** Whether session status is completed/failed */
  isSessionComplete?: boolean
  /** Replay screenshot URL for completed sessions */
  replayScreenshotUrl?: string
  /** Plan presentation text for live-view overlay */
  planPresentationText?: string
  /** Whether plan streaming is in progress */
  isPlanStreaming?: boolean
  /** Shared session start timestamp so all timers stay in sync. */
  sessionStartTime?: number
}

const props = withDefaults(defineProps<Props>(), {
  showThumbnail: false,
  defaultExpanded: false,
  compact: false,
  sessionId: '',
  currentTool: null,
  hideExpandedHeader: false,
  isInitializing: false,
  isSummaryStreaming: false,
  summaryStreamText: '',
  finalReportText: '',
  isSessionComplete: false,
  replayScreenshotUrl: '',
  planPresentationText: '',
  isPlanStreaming: false
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
const showCollapsedThumbnail = computed(() => props.showThumbnail && !props.compact)
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

// Task timer — shared composable replaces local interval logic
const timer = useElapsedTimer()

/** Expose timer start-time as a template-friendly ref for v-if guards. */
const taskStartTime = computed(() => timer.startTime.value)

const isVisible = computed(() => {
  return props.plan && props.plan.steps.length > 0
})

const steps = computed(() => props.plan?.steps ?? [])

// Track recently completed task IDs for flip animation
const recentlyCompletedIds = ref<Set<string>>(new Set())
const previousStepStatuses = ref<Map<string, string>>(new Map())

const completedCount = computed(() => steps.value.filter(s => s.status === 'completed').length)

/** 1-based position of the active task: running index+1, else completed count. */
const currentCount = computed(() => {
  const runningIdx = steps.value.findIndex(s => s.status === 'running')
  if (runningIdx >= 0) return runningIdx + 1
  return completedCount.value
})
const totalCount = computed(() => steps.value.length)

const formattedElapsedTime = timer.formatted

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
  return isToolRunning.value ? 'processing' : 'idle'
})

// Get icon for current tool
const currentToolIcon = computed(() => {
  if (props.currentTool?.icon) return props.currentTool.icon
  const toolName = props.currentTool?.name?.toLowerCase() || ''
  if (toolName.includes('browser') || toolName.includes('web') || toolName.includes('search')) return Globe
  if (toolName.includes('file') || toolName.includes('editor')) return FolderOpen
  return Terminal
})

const formattedToolPreview = computed(() => extractToolPreview(props.toolContent, 500))
const contentPreview = computed(() => formattedToolPreview.value.previewText)
const filePath = computed(() => formattedToolPreview.value.filePath)
const searchResults = computed(() => formattedToolPreview.value.searchResults)
const searchQuery = computed(() => formattedToolPreview.value.searchQuery)

const _streamingPresentation = useStreamingPresentationState({
  isInitializing: computed(() => !!props.isInitializing),
  isSummaryStreaming: computed(() => !!props.isSummaryStreaming),
  summaryStreamText: computed(() => props.summaryStreamText || ''),
  finalReportText: computed(() => props.finalReportText || ''),
  isThinking: computed(() => !!props.isThinking),
  isActiveOperation: computed(() => isToolRunning.value),
  toolDisplayName: computed(() => currentToolDisplayName.value),
  toolDescription: computed(() => currentToolActionLabel.value),
  baseViewType: computed(() => 'generic'),
  isSessionComplete: computed(() => !!props.isSessionComplete),
  replayScreenshotUrl: computed(() => props.replayScreenshotUrl || ''),
  previewText: computed(() => contentPreview.value)
})


const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const startTimer = () => timer.start(props.sessionStartTime || undefined)
const stopTimer = () => timer.stop()

// Start/stop animations based on loading/thinking state
watch(() => props.isLoading, (loading) => {
  if (loading && !isAllCompleted.value) {
    startTimer()
  } else {
    stopTimer()
  }
}, { immediate: true })

// Watch for completion - emit event for parent to capture final screenshot
watch(isAllCompleted, (completed) => {
  if (completed) {
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
    startTimer()
  }
  window.addEventListener('scroll', handleScroll, true)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  stopTimer()
  window.removeEventListener('scroll', handleScroll, true)
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
/* ===== BASE CONTAINER ===== */
.task-progress-bar {
  position: relative;
  z-index: 6;
}

.task-progress-bar.is-expanded {
  position: relative;
}

/* ===== COLLAPSED VIEW ===== */
.collapsed-wrapper {
  position: relative;
}

.collapsed-wrapper.has-thumbnail {
  /* Thumbnail overflows above via position: absolute — no margin needed */
}

.progress-bar-collapsed {
  position: relative;
  z-index: 7;
  background: var(--background-menu-white, #fff);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 16px;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: background-color 0.15s ease;
  box-shadow: 0px 0px 1px 0px rgba(0, 0, 0, 0.05), 0px 8px 32px 0px rgba(0, 0, 0, 0.04);
}

@media (min-width: 640px) {
  .progress-bar-collapsed {
    border-radius: 12px;
  }
}

:global(.dark) .progress-bar-collapsed {
  border-color: var(--border-main);
}

.progress-bar-collapsed:hover {
  background: var(--fill-tsp-gray-main);
}

/* ===== COLLAPSED STATUS ICON ===== */
.collapsed-status-icon {
  width: 22px;
  height: 22px;
  min-width: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: #22c55e;
}

.progress-bar-collapsed:not(.completed-state) .collapsed-status-icon {
  background: var(--fill-tsp-gray-main);
  border: 1.5px solid var(--border-light);
}

.collapsed-thinking-indicator {
  width: 18px !important;
  height: 18px !important;
}

.collapsed-pending-num {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
}

/* ===== TASK TEXT ===== */
.collapsed-task-text {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== COUNTER ===== */
.collapsed-counter {
  font-size: 13px;
  font-weight: 400;
  color: var(--text-tertiary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* ===== COMPLETED STATE ===== */
.progress-bar-collapsed.completed-state {
  /* Clean — no gradient, just the green check icon carries the signal */
}

.progress-bar-collapsed.completed-state .collapsed-status-icon {
  background: transparent;
}

.collapsed-status-icon-complete {
  width: auto;
  height: auto;
  min-width: 0;
  border-radius: 0;
}

.collapsed-complete-check {
  width: 16px;
  height: 16px;
  color: #22c55e;
  display: block;
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

/* ===== LIVE PREVIEW THUMBNAILS ===== */
.live-preview-thumbnail-floating {
  position: absolute;
  left: 12px;
  bottom: 7px;
  z-index: 10;
  width: 56px;
  height: 40px;
  border-radius: 8px;
  overflow: hidden;
}

@media (min-width: 640px) {
  .live-preview-thumbnail-floating {
    position: absolute;
    bottom: 7px;
    left: 12px;
    width: 100px;
    height: 68px;
  }
}

.live-preview-thumbnail-floating :deep(.live-mini-preview) {
  max-width: none;
  height: 100%;
  aspect-ratio: unset;
}

.progress-bar-collapsed.has-thumbnail {
  padding-left: 80px; /* Space for 56px wide preview + gap (mobile) */
}

@media (min-width: 640px) {
  .progress-bar-collapsed.has-thumbnail {
    padding-left: 124px; /* Space for 100px wide preview + gap (desktop) */
  }
}

.live-preview-thumbnail-expanded {
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

.live-preview-thumbnail-expanded:hover {
  border-color: var(--bolt-elements-borderColorActive);
}

.live-preview-thumbnail-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.live-preview-thumbnail-floating:hover .live-preview-thumbnail-overlay,
.live-preview-thumbnail-expanded:hover .live-preview-thumbnail-overlay {
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
  align-items: stretch;
  gap: 10px;
  padding: 4px 0;
  position: relative;
}

.task-item:first-child {
  padding-top: 0;
}

.task-item:last-child {
  padding-bottom: 0;
}

/* Left rail with step node + dotted timeline */
.task-left-rail {
  width: 20px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.task-timeline-line {
  width: 1px;
  min-height: 8px;
  margin-top: 2px;
  flex: 1;
  background: repeating-linear-gradient(
    to bottom,
    var(--bolt-elements-borderColor) 0,
    var(--bolt-elements-borderColor) 4px,
    transparent 4px,
    transparent 8px
  );
}

.task-timeline-line.connector-active {
  background: repeating-linear-gradient(
    to bottom,
    var(--function-success) 0,
    var(--function-success) 4px,
    transparent 4px,
    transparent 8px
  );
}

/* Task indicators */
.task-indicator {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
  perspective: 600px;
}

/* 3D Flip Container */
.indicator-flip-container {
  width: 18px;
  height: 18px;
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
  width: 18px;
  height: 18px;
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
  position: relative;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.indicator-running::before {
  content: "";
  position: absolute;
  inset: 2px;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--bolt-elements-textSecondary) 20%, transparent);
  transform: scale(0.52);
  opacity: 0.16;
  animation: task-running-inner-pulse 1.5s ease-in-out infinite;
}

.indicator-running-dot {
  position: relative;
  z-index: 1;
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  background: var(--bolt-elements-textSecondary);
  animation: task-running-dot-pulse 1.2s ease-in-out infinite;
}

@keyframes task-running-inner-pulse {
  0%, 100% {
    transform: scale(0.52);
    opacity: 0.16;
  }
  50% {
    transform: scale(0.96);
    opacity: 0.3;
  }
}

@keyframes task-running-dot-pulse {
  0%, 100% {
    transform: scale(0.9);
    opacity: 0.85;
  }
  50% {
    transform: scale(1);
    opacity: 1;
  }
}

.indicator-pending {
  width: 18px;
  height: 18px;
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
  font-size: 13px;
  line-height: 1.4;
  padding-top: 1px;
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

:global(.dark) .custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
}

:global(.dark) .custom-scrollbar::-webkit-scrollbar-thumb:hover {
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

/* ── Mobile overrides ── */
@media (max-width: 479px) {
  .live-preview-thumbnail-floating {
    display: none;
  }
  .progress-bar-collapsed.has-thumbnail {
    padding-left: 16px;
  }
}

@media (max-width: 639px) {
  .expanded-header .flex.items-start {
    flex-direction: column;
    gap: 12px;
  }
  .expanded-header .flex.items-center.gap-1.flex-shrink-0 {
    position: absolute;
    top: 12px;
    right: 12px;
  }
  .expanded-header {
    position: relative;
    padding: 14px 16px;
  }
  .action-btn {
    padding: 10px;
    min-width: 44px;
    min-height: 44px;
  }
  .expand-btn {
    padding: 10px;
    min-width: 44px;
    min-height: 44px;
  }
  .task-description {
    font-size: 14px;
    line-height: 1.5;
  }
  .progress-bar-expanded {
    max-height: 80vh;
    border-radius: 12px 12px 0 0;
  }
  .task-list {
    max-height: 55vh;
  }
  .collapsed-task-text {
    font-size: 13px;
  }
  .timer-section {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
