<template>
  <div
    ref="controlsRef"
    class="timeline-controls px-4 py-2.5 bg-transparent"
    tabindex="0"
    @keydown="handleKeydown"
  >
    <!-- Jump to Live Button (shown when not in live mode, hidden in replay mode) -->
    <div
      v-if="!isLive && !isReplayMode"
      class="flex items-center justify-center mb-2"
    >
      <button
        @click="$emit('jumpToLive')"
        class="flex items-center gap-1.5 px-3 py-1 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-md transition-colors"
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
    <div class="flex items-center gap-3">
      <!-- Step Controls -->
      <div class="flex items-center gap-0.5">
        <button
          @click="$emit('stepBackward')"
          :disabled="!canStepBackward"
          class="timeline-step-btn"
          title="Previous action (←)"
        >
          <SkipBack class="w-[18px] h-[18px]" />
        </button>
        <button
          @click="$emit('stepForward')"
          :disabled="!canStepForward"
          class="timeline-step-btn"
          title="Next action (→)"
        >
          <SkipForward class="w-[18px] h-[18px]" />
        </button>
      </div>

      <!-- Timeline Scrubber -->
      <div class="flex-1 flex items-center">
        <div
          ref="scrubberRef"
          class="scrubber-track relative w-full h-[7px] rounded-full cursor-pointer group overflow-visible"
          @click="handleScrubberClick"
          @mousedown="startDragging"
          @mouseenter="handleMouseEnter"
          @mouseleave="handleMouseLeave"
          @mousemove="handleMouseMove"
        >
          <!-- Floating Tooltip (timestamp + tool name on hover/drag) -->
          <div
            v-if="tooltipVisible"
            class="absolute -translate-x-1/2 rounded-lg bg-gray-800 dark:bg-gray-700 text-white text-[10px] font-medium px-2 py-1 shadow-md pointer-events-none whitespace-nowrap z-20 flex flex-col items-center gap-0.5"
            :style="{ left: `${tooltipPosition}%`, bottom: '14px' }"
          >
            <span v-if="tooltipToolLabel" class="text-[10px] font-semibold">{{ tooltipToolLabel }}</span>
            <span v-if="tooltipTimestamp" class="text-[9px] opacity-75">{{ tooltipTimestamp }}</span>
          </div>

          <!-- Tool-Type Markers -->
          <div
            v-for="marker in toolMarkers"
            :key="`tool-${marker.index}`"
            class="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full pointer-events-none z-10"
            :class="marker.colorClass"
            :style="{ left: `${marker.position}%` }"
            :title="marker.label"
          />

          <!-- Progress Fill (teal gradient) -->
          <div
            class="scrubber-fill absolute h-full rounded-full transition-[width] duration-100"
            :style="{ width: `${progress}%` }"
          />

          <!-- Scrubber Thumb -->
          <div
            class="scrubber-thumb absolute w-3.5 h-3.5 rounded-full -top-[3.5px] transform -translate-x-1/2 shadow-md transition-transform hover:scale-125"
            :style="{ left: `${progress}%` }"
          />
        </div>
      </div>

      <!-- Live / Replay Indicator -->
      <div class="flex items-center gap-2 min-w-[50px] justify-end">
        <span
          class="timeline-live-dot"
          :class="isReplayMode ? 'bg-gray-400' : isLive ? 'is-live' : 'bg-gray-400'"
        />
        <span
          class="text-[14px] font-semibold"
          :class="isReplayMode ? 'text-[var(--text-tertiary)]' : isLive ? 'text-emerald-500 dark:text-emerald-400' : 'text-[var(--text-tertiary)]'"
        >
          {{ isReplayMode ? 'replay' : 'live' }}
        </span>
      </div>
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
}

.timeline-controls:focus {
  outline: none;
}

.timeline-controls:focus-visible {
  outline: 2px solid var(--focus-ring, #3b82f6);
  outline-offset: -2px;
  border-radius: 4px;
}

/* Step buttons */
.timeline-step-btn {
  padding: 6px;
  border-radius: 6px;
  color: var(--icon-primary);
  transition: all 0.15s ease;
  cursor: pointer;
  background: transparent;
  border: none;
}

.timeline-step-btn:hover {
  background: var(--fill-tsp-gray-main);
}

:global(.dark) .timeline-step-btn {
  color: rgba(255, 255, 255, 0.6);
}

:global(.dark) .timeline-step-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.85);
}

.timeline-step-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Scrubber track */
.scrubber-track {
  touch-action: none;
  background: color-mix(in srgb, var(--text-tertiary) 15%, transparent);
}

:global(.dark) .scrubber-track {
  background: rgba(255, 255, 255, 0.08);
}

/* Teal gradient fill */
.scrubber-fill {
  background: linear-gradient(90deg, #0d9488 0%, #14b8a6 50%, #2dd4bf 100%);
  border-radius: 999px;
}

:global(.dark) .scrubber-fill {
  background: linear-gradient(90deg, #0f766e 0%, #14b8a6 50%, #2dd4bf 100%);
}

/* Teal thumb */
.scrubber-thumb {
  cursor: grab;
  background: #14b8a6;
  box-shadow: 0 0 6px rgba(20, 184, 166, 0.4);
}

:global(.dark) .scrubber-thumb {
  background: #2dd4bf;
  box-shadow: 0 0 8px rgba(45, 212, 191, 0.5);
}

.scrubber-thumb:active {
  cursor: grabbing;
}

/* Live indicator dot */
.timeline-live-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.timeline-live-dot.is-live {
  background: #10b981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.5);
  animation: live-pulse 2s ease-in-out infinite;
}

@keyframes live-pulse {
  0%, 100% {
    box-shadow: 0 0 4px rgba(16, 185, 129, 0.4);
  }
  50% {
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.7);
  }
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
