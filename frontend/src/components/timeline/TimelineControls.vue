<template>
  <div
    ref="controlsRef"
    class="timeline-controls timeline-controls--deck px-4 py-3 bg-[var(--background-menu-white)] border-t border-black/8 dark:border-[var(--border-main)]"
    tabindex="0"
    @keydown="handleKeydown"
  >
    <!-- Jump to Live Button (shown when not in live mode, hidden in replay mode) -->
    <div
      v-if="!isLive && !isReplayMode"
      class="flex items-center justify-center mb-3"
    >
      <button
        @click="$emit('jumpToLive')"
        class="timeline-controls__jump flex items-center gap-1.5 px-3 py-1 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-md transition-colors"
      >
        <Play class="w-3 h-3" />
        <span>Jump to live</span>
      </button>
    </div>

    <!-- Timestamp Display (static for non-hover mode) -->
    <div
      v-if="showTimestamp && !showTimestampOnInteract"
      class="flex items-center justify-center mb-3"
    >
      <div class="px-3 py-1 bg-blue-500 text-white text-xs font-medium rounded-full">
        {{ formattedTimestamp }}
      </div>
    </div>

    <!-- Main Controls Row -->
    <div class="timeline-controls__deck-row flex items-center gap-3">
      <!-- Step Controls -->
      <div class="timeline-controls__transport flex items-center gap-1">
        <!-- Step Backward -->
        <button
          @click="$emit('stepBackward')"
          :disabled="!canStepBackward"
          class="timeline-controls__transport-btn p-1.5 rounded hover:bg-[var(--fill-tsp-gray-main)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Previous action (←)"
        >
          <SkipBack class="w-4 h-4 text-[var(--icon-primary)]" />
        </button>

        <!-- Step Forward -->
        <button
          @click="$emit('stepForward')"
          :disabled="!canStepForward"
          class="timeline-controls__transport-btn p-1.5 rounded hover:bg-[var(--fill-tsp-gray-main)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Next action (→)"
        >
          <SkipForward class="w-4 h-4 text-[var(--icon-primary)]" />
        </button>
      </div>

      <!-- Timeline Scrubber -->
      <div
        class="timeline-controls__scrubber-frame flex-1 relative"
        data-test="timeline-scrubber-frame"
      >
        <div
          ref="scrubberRef"
          class="scrubber-track relative h-1 bg-[var(--fill-tsp-gray-main)] rounded-full cursor-pointer group overflow-visible"
          @click="handleScrubberClick"
          @mousedown="startDragging"
          @mouseenter="handleMouseEnter"
          @mouseleave="handleMouseLeave"
          @mousemove="handleMouseMove"
        >
          <!-- Floating Tooltip (timestamp + tool name on hover/drag) -->
          <div
            v-if="tooltipVisible"
            class="timeline-controls__tooltip absolute -translate-x-1/2 text-white text-[10px] font-medium px-2 py-1 pointer-events-none whitespace-nowrap z-20 flex flex-col items-center gap-0.5"
            :style="{ left: `${tooltipPosition}%`, bottom: '12px' }"
          >
            <span v-if="tooltipToolLabel" class="text-[10px] font-semibold">{{ tooltipToolLabel }}</span>
            <span v-if="tooltipTimestamp" class="text-[9px] opacity-75">{{ tooltipTimestamp }}</span>
          </div>

          <!-- Tool-Type Markers -->
          <div
            v-for="marker in toolMarkers"
            :key="`tool-${marker.index}`"
            class="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full pointer-events-none z-10"
            :class="marker.colorClass"
            :style="{ left: `${marker.position}%` }"
            :title="marker.label"
          />

          <!-- Progress Fill -->
          <div
            class="timeline-controls__fill absolute h-full rounded-full transition-[width] duration-100"
            :style="{ width: `${progress}%` }"
          />

          <!-- Scrubber Thumb -->
          <div
            class="scrubber-thumb timeline-controls__thumb absolute w-3 h-3 rounded-full -top-1 transform -translate-x-1/2 shadow-md transition-transform hover:scale-125"
            :style="{ left: `${progress}%` }"
          />
        </div>
      </div>

      <!-- Live / Replay Indicator -->
      <div
        class="timeline-controls__mode-badge flex items-center gap-1.5 justify-end"
        data-test="timeline-mode-badge"
      >
        <span
          class="timeline-controls__mode-dot w-2 h-2 rounded-full"
          :class="isReplayMode ? 'bg-gray-400' : isLive ? 'bg-blue-500 animate-pulse' : 'bg-gray-400'"
        />
        <span
          class="text-xs font-medium"
          :class="isReplayMode ? 'text-[var(--text-tertiary)]' : isLive ? 'text-blue-600 dark:text-blue-400' : 'text-[var(--text-tertiary)]'"
        >
          {{ modeLabel }}
        </span>
      </div>
    </div>

    <div
      v-if="totalSteps > 0"
      class="timeline-controls__step-footer mt-2 flex items-center justify-between gap-3"
    >
      <span class="timeline-controls__counter text-[11px] font-mono tabular-nums text-[var(--text-quaternary)] select-none">
        {{ currentStepDisplay }} / {{ totalSteps }}
      </span>
      <span v-if="showTimestamp && showTimestampOnInteract" class="text-[11px] text-[var(--text-quaternary)] truncate">
        {{ formattedTimestamp }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { SkipBack, SkipForward, Play } from 'lucide-vue-next'
import type { ToolContent } from '../../types/message'
import { normalizeTimestampSeconds } from '../../utils/time'
import { TOOL_TIMELINE_COLORS, TOOL_TIMELINE_DEFAULT_COLOR } from '../../constants/tool'
import { getToolDisplay } from '../../utils/toolDisplay'

interface Props {
  progress: number
  currentTimestamp?: number
  isLive: boolean
  isReplayMode?: boolean
  canStepForward: boolean
  canStepBackward: boolean
  showTimestampOnInteract?: boolean
  /** Tool timeline entries for markers and hover labels */
  toolTimeline?: ToolContent[]
  /** 1-based current step index (0 if nothing selected) */
  currentStep?: number
  /** Total number of steps in the tool timeline */
  totalSteps?: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  jumpToLive: []
  stepForward: []
  stepBackward: []
  seekByProgress: [progress: number]
}>()

const controlsRef = ref<HTMLElement | null>(null)
const scrubberRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const isHovering = ref(false)
const hoverPercent = ref(0)

// ── Keyboard navigation ──
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    if (props.canStepBackward) emit('stepBackward')
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    if (props.canStepForward) emit('stepForward')
  } else if (event.key === 'Home') {
    event.preventDefault()
    emit('seekByProgress', 0)
  } else if (event.key === 'End') {
    event.preventDefault()
    emit('seekByProgress', 100)
  }
}

// ── Timestamp formatting ──
const formatTimestamp = (ts: number | undefined): string => {
  const normalized = normalizeTimestampSeconds(ts ?? Number.NaN)
  if (normalized === null) return ''
  const date = new Date(normalized * 1000)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
}

const formattedTimestamp = computed(() => formatTimestamp(props.currentTimestamp))

const showTimestamp = computed(() => {
  if (normalizeTimestampSeconds(props.currentTimestamp ?? Number.NaN) === null) return false
  if (props.showTimestampOnInteract) return isHovering.value || isDragging.value
  return true
})

// ── Tool-type markers on scrubber track ──
const toolMarkers = computed(() => {
  const tools = props.toolTimeline ?? []
  if (tools.length <= 1) return []
  const maxIdx = tools.length - 1
  return tools.map((tool, i) => ({
    index: i,
    position: (i / maxIdx) * 100,
    colorClass: TOOL_TIMELINE_COLORS[tool.name] ?? TOOL_TIMELINE_DEFAULT_COLOR,
    label: getToolDisplay({
      name: tool.name,
      function: tool.function,
      args: tool.args,
      display_command: tool.display_command,
    }).displayName,
  }))
})

// ── Hover tooltip (tool name + timestamp) ──
const hoveredToolIndex = computed(() => {
  const tools = props.toolTimeline ?? []
  if (tools.length === 0) return -1
  const maxIdx = tools.length - 1
  return Math.round((hoverPercent.value / 100) * maxIdx)
})

const hoveredTool = computed(() => {
  const tools = props.toolTimeline ?? []
  const idx = hoveredToolIndex.value
  if (idx < 0 || idx >= tools.length) return null
  return tools[idx]
})

const tooltipVisible = computed(() => {
  if (!props.showTimestampOnInteract) return showTimestamp.value
  return (isHovering.value || isDragging.value) && hoveredTool.value !== null
})

const tooltipPosition = computed(() => {
  if (isDragging.value) return progress.value
  return hoverPercent.value
})

const tooltipToolLabel = computed(() => {
  if (!hoveredTool.value) return ''
  const display = getToolDisplay({
    name: hoveredTool.value.name,
    function: hoveredTool.value.function,
    args: hoveredTool.value.args,
    display_command: hoveredTool.value.display_command,
  })
  return display.displayName
})

const tooltipTimestamp = computed(() => {
  if (!hoveredTool.value) return ''
  return formatTimestamp(hoveredTool.value.timestamp)
})

const progress = computed(() => props.progress)
const modeLabel = computed(() => (props.isReplayMode ? 'replay' : 'live'))
const currentStepDisplay = computed(() => {
  if (!props.totalSteps || props.totalSteps <= 0) return 0
  if (props.currentStep && props.currentStep > 0) return props.currentStep
  return props.isLive ? props.totalSteps : 0
})

// ── Mouse interaction ──
const handleMouseEnter = () => {
  isHovering.value = true
}

const handleMouseLeave = () => {
  isHovering.value = false
}

const handleMouseMove = (event: MouseEvent) => {
  if (!scrubberRef.value) return
  const rect = scrubberRef.value.getBoundingClientRect()
  const x = event.clientX - rect.left
  hoverPercent.value = Math.max(0, Math.min(100, (x / rect.width) * 100))
}

// Handle click on scrubber
const handleScrubberClick = (event: MouseEvent) => {
  if (!scrubberRef.value) return

  const rect = scrubberRef.value.getBoundingClientRect()
  const clickX = event.clientX - rect.left
  const percentage = Math.max(0, Math.min(100, (clickX / rect.width) * 100))

  emit('seekByProgress', percentage)
}

// Drag handling
const startDragging = (event: MouseEvent) => {
  isDragging.value = true
  handleDrag(event)
}

const handleDrag = (event: MouseEvent) => {
  if (!isDragging.value || !scrubberRef.value) return

  const rect = scrubberRef.value.getBoundingClientRect()
  const clickX = event.clientX - rect.left
  hoverPercent.value = Math.max(0, Math.min(100, (clickX / rect.width) * 100))

  emit('seekByProgress', hoverPercent.value)
}

const stopDragging = () => {
  isDragging.value = false
}

onMounted(() => {
  document.addEventListener('mousemove', handleDrag)
  document.addEventListener('mouseup', stopDragging)
})

onUnmounted(() => {
  document.removeEventListener('mousemove', handleDrag)
  document.removeEventListener('mouseup', stopDragging)
})
</script>

<style scoped>
.timeline-controls {
  user-select: none;
  position: relative;
  background: var(--background-menu-white);
  box-shadow: none;
}

.timeline-controls:focus {
  outline: none;
}

.timeline-controls:focus-visible {
  outline: 2px solid var(--focus-ring, #3b82f6);
  outline-offset: -2px;
  border-radius: 4px;
}

.timeline-controls__jump {
  padding: 8px 14px;
  border-radius: 12px;
  border: 1px solid var(--border-light, #e5e7eb);
  background: var(--background-white-main, #ffffff);
  box-shadow: none;
}

.timeline-controls__deck-row {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid var(--border-light, #e5e7eb);
  background: var(--background-white-main, #ffffff);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
}

.timeline-controls__transport {
  padding: 3px;
  border-radius: 12px;
  border: 1px solid var(--border-light, #e5e7eb);
  background: var(--fill-tsp-gray-main, #f3f4f6);
  box-shadow: none;
}

.timeline-controls__transport-btn {
  min-width: 32px;
  min-height: 32px;
  border-radius: 10px;
}

.timeline-controls__transport-btn:hover:not(:disabled) {
  transform: none;
  box-shadow: none;
}

.timeline-controls__counter {
  padding: 0;
}

.timeline-controls__step-footer {
  padding: 0 4px;
}

.timeline-controls__scrubber-frame {
  padding: 10px 6px;
  border-radius: 12px;
  border: none;
  background: transparent;
  box-shadow: none;
}

.scrubber-track {
  touch-action: none;
  height: 4px;
  background: var(--fill-tsp-gray-main, #e5e7eb);
}

.timeline-controls__fill {
  background: linear-gradient(90deg, #2563eb, #60a5fa);
}

.scrubber-thumb {
  cursor: grab;
}

.timeline-controls__thumb {
  top: -5px;
  width: 14px;
  height: 14px;
  background: var(--background-white-main, #ffffff);
  border: 2px solid #2563eb;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.2);
}

.scrubber-thumb:active {
  cursor: grabbing;
}

.timeline-controls__tooltip {
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--Tooltips-main);
  border: 1px solid color-mix(in srgb, var(--border-white) 72%, transparent);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.18);
  backdrop-filter: blur(14px);
}

.timeline-controls__mode-badge {
  min-width: auto;
  padding: 0 2px;
  border: none;
  background: transparent;
  box-shadow: none;
}

.timeline-controls__mode-dot {
  box-shadow: none;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.animate-pulse {
  animation: pulse 1.5s ease-in-out infinite;
}
</style>
