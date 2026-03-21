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

      <!-- Live / Replay Indicator -->
      <div class="timeline-status">
        <span
          class="timeline-live-dot"
          :class="isSessionActive && !isReplayMode ? 'is-live' : 'is-replay'"
        />
        <span class="timeline-status-label" :class="{ 'is-live': isSessionActive && !isReplayMode }">
          {{ isReplayMode ? 'replay' : 'live' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { SkipBack, SkipForward } from 'lucide-vue-next'

interface Props {
  progress: number
  currentTimestamp?: number
  isLive: boolean
  isReplayMode?: boolean
  isSessionActive?: boolean
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
/* ── Reference-style Timeline Controls: 44px, menu-white bg, border-t ── */
.timeline-controls {
  user-select: none;
  height: 44px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  border-top: 1px solid var(--border-main, rgba(0, 0, 0, 0.08));
  background: var(--background-menu-white, var(--panel-surface-bg, var(--background-white-main)));
}

:global(.dark) .timeline-controls,
:global(html[data-theme='dark']) .timeline-controls {
  background: #1e1e1e;
  border-top-color: rgba(255, 255, 255, 0.06);
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
  width: 100%;
}

/* ── Step buttons ── */
.timeline-step-group {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.timeline-step-btn {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  color: var(--icon-secondary, var(--text-tertiary));
  transition: color 0.15s ease;
  cursor: pointer;
  background: transparent;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

.timeline-step-btn:hover {
  color: var(--icon-blue, var(--text-blue, #3b82f6));
}

:global(.dark) .timeline-step-btn {
  color: var(--icon-secondary, rgba(255, 255, 255, 0.45));
}

:global(.dark) .timeline-step-btn:hover {
  color: var(--icon-blue, var(--text-blue, #60a5fa));
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

/* Reference: h-1 (4px) rounded-full track, blue fill, 14px thumb with border */
.scrubber-track {
  position: relative;
  width: 100%;
  height: 4px;
  border-radius: 9999px;
  cursor: pointer;
  overflow: visible;
  touch-action: none;
  background: var(--fill-tsp-gray-dark, rgba(0, 0, 0, 0.08));
}

:global(.dark) .scrubber-track {
  background: var(--fill-tsp-gray-dark, rgba(255, 255, 255, 0.1));
}

.scrubber-fill {
  position: absolute;
  height: 100%;
  border-radius: 9999px;
  background: var(--text-blue, #3b82f6);
  opacity: 1;
  transition: width 100ms ease;
}

:global(.dark) .scrubber-fill {
  background: var(--text-blue, #60a5fa);
  opacity: 1;
}

.scrubber-thumb {
  position: absolute;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  top: -5px;
  transform: translateX(-50%);
  cursor: grab;
  background: var(--text-blue, #3b82f6);
  border: 2px solid var(--fill-input-chat, #ffffff);
  filter: drop-shadow(0px 1px 4px rgba(0, 0, 0, 0.06));
  transition: transform 0.1s ease;
}

.scrubber-thumb:hover {
  transform: translateX(-50%) scale(1.1);
}

.scrubber-thumb:active {
  cursor: grabbing;
}

:global(.dark) .scrubber-thumb {
  background: var(--text-blue, #60a5fa);
  border-color: var(--fill-input-chat, #2a2a2a);
}

/* ── Jump to live (inline button) ── */
/* ── Live / Replay status ── */
.timeline-status {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-inline-start: 2px;
}

.timeline-live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.timeline-live-dot.is-live {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.5);
  animation: live-pulse 2s ease-in-out infinite;
}

.timeline-live-dot.is-replay {
  background: var(--text-tertiary, #9ca3af);
}

@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.timeline-status-label {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.timeline-status-label.is-live {
  color: #22c55e;
}
</style>
