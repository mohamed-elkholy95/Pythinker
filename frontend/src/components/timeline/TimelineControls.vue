<template>
  <div
    ref="controlsRef"
    class="timeline-controls"
    tabindex="0"
    @keydown="handleKeydown"
  >
    <!-- Main Controls Row -->
    <div class="timeline-row">
      <!-- Step Controls -->
      <div class="timeline-step-group">
        <button
          @click="$emit('stepBackward')"
          :disabled="!canStepBackward"
          class="timeline-step-btn"
          title="Previous action"
        >
          <SkipBack class="w-[16px] h-[16px]" />
        </button>
        <button
          @click="$emit('stepForward')"
          :disabled="!canStepForward"
          class="timeline-step-btn"
          title="Next action"
        >
          <SkipForward class="w-[16px] h-[16px]" />
        </button>
      </div>

      <!-- Timeline Scrubber -->
      <div class="timeline-scrubber-wrap">
        <div
          ref="scrubberRef"
          class="scrubber-track"
          @click="handleScrubberClick"
          @mousedown="startDragging"
        >
          <!-- Progress Fill -->
          <div
            class="scrubber-fill"
            :style="{ width: `${progress}%` }"
          />

          <!-- Scrubber Thumb -->
          <div
            class="scrubber-thumb"
            :style="{ left: `${progress}%` }"
          />
        </div>
      </div>

      <!-- Jump to live (inline, Pythinker-style) -->
      <button
        v-if="!isLive"
        @click="$emit('jumpToLive')"
        class="jump-to-live-btn"
      >
        <Play class="w-3 h-3" />
        <span>Jump to live</span>
      </button>

      <!-- Live / Replay Indicator -->
      <div class="timeline-status">
        <span
          class="timeline-live-dot"
          :class="isReplayMode ? 'is-replay' : isLive ? 'is-live' : 'is-replay'"
        />
        <span class="timeline-status-label" :class="{ 'is-live': isLive && !isReplayMode }">
          {{ isReplayMode ? 'replay' : 'live' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { SkipBack, SkipForward, Play } from 'lucide-vue-next'

interface Props {
  progress: number
  currentTimestamp?: number
  isLive: boolean
  isReplayMode?: boolean
  canStepForward: boolean
  canStepBackward: boolean
  showTimestampOnInteract?: boolean
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

const progress = computed(() => props.progress)

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
  const dragPercent = Math.max(0, Math.min(100, (clickX / rect.width) * 100))

  emit('seekByProgress', dragPercent)
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
/* ── Pythinker-style Timeline Controls ── */
.timeline-controls {
  user-select: none;
  padding: 8px 16px 10px;
}

.timeline-controls:focus {
  outline: none;
}

.timeline-controls:focus-visible {
  outline: 2px solid var(--focus-ring, #3b82f6);
  outline-offset: -2px;
  border-radius: 4px;
}

.timeline-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── Step buttons ── */
.timeline-step-group {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.timeline-step-btn {
  padding: 4px;
  border-radius: 4px;
  color: var(--text-tertiary);
  transition: all 0.12s ease;
  cursor: pointer;
  background: transparent;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

.timeline-step-btn:hover {
  color: var(--text-primary);
  background: var(--fill-tsp-gray-main);
}

:global(.dark) .timeline-step-btn {
  color: rgba(255, 255, 255, 0.45);
}

:global(.dark) .timeline-step-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.8);
}

.timeline-step-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* ── Scrubber ── */
.timeline-scrubber-wrap {
  flex: 1;
  display: flex;
  align-items: center;
}

.scrubber-track {
  position: relative;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  cursor: pointer;
  overflow: visible;
  touch-action: none;
  background: color-mix(in srgb, var(--text-tertiary) 12%, transparent);
}

:global(.dark) .scrubber-track {
  background: rgba(255, 255, 255, 0.08);
}

.scrubber-fill {
  position: absolute;
  height: 100%;
  border-radius: 2px;
  background: var(--text-tertiary);
  opacity: 0.35;
  transition: width 100ms ease;
}

:global(.dark) .scrubber-fill {
  background: rgba(255, 255, 255, 0.2);
}

.scrubber-thumb {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  top: -3px;
  transform: translateX(-50%);
  cursor: grab;
  background: #3b82f6;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.3);
  transition: transform 0.1s ease;
}

.scrubber-thumb:hover {
  transform: translateX(-50%) scale(1.2);
}

.scrubber-thumb:active {
  cursor: grabbing;
}

:global(.dark) .scrubber-thumb {
  background: #60a5fa;
  box-shadow: 0 1px 4px rgba(96, 165, 250, 0.4);
}

/* ── Jump to live (inline button) ── */
.jump-to-live-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.12s ease;
}

.jump-to-live-btn:hover {
  color: var(--text-primary);
  background: var(--fill-tsp-gray-main);
}

/* ── Live / Replay status ── */
.timeline-status {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.timeline-live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.timeline-live-dot.is-live {
  background: #1a1a1a;
}

:global(.dark) .timeline-live-dot.is-live {
  background: #e5e5e5;
}

.timeline-live-dot.is-replay {
  background: #9ca3af;
}

.timeline-status-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
}

.timeline-status-label.is-live {
  color: var(--text-primary);
}
</style>
