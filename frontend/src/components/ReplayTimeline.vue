<template>
  <div class="replay-timeline">
    <!-- Timeline bar -->
    <div
      ref="timelineBar"
      class="timeline-bar"
      @click="handleTimelineClick"
      @mousedown="startDrag"
    >
      <!-- Progress -->
      <div class="timeline-progress" :style="{ width: progressPercent + '%' }"></div>

      <!-- Event markers -->
      <div
        v-for="event in sortedEvents"
        :key="event.id"
        class="event-marker"
        :class="getEventClass(event)"
        :style="{ left: getEventPosition(event) + '%' }"
        :title="getEventTooltip(event)"
        @click.stop="handleEventClick(event)"
      >
        <div class="marker-dot"></div>
      </div>

      <!-- Playhead -->
      <div class="timeline-playhead" :style="{ left: progressPercent + '%' }"></div>
    </div>

    <!-- Event legend -->
    <div class="timeline-legend">
      <div class="legend-item">
        <span class="legend-dot tool"></span>
        <span>Tool</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot step"></span>
        <span>Step</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot error"></span>
        <span>Error</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot message"></span>
        <span>Message</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface TimelineEvent {
  id: string
  type: string
  name: string
  timestamp: number
  payload?: Record<string, unknown>
}

const props = defineProps<{
  events: TimelineEvent[]
  currentTime: number
  duration: number
}>()

const emit = defineEmits<{
  seek: [time: number]
  eventClick: [event: TimelineEvent]
}>()

const timelineBar = ref<HTMLDivElement | null>(null)
const isDragging = ref(false)

// Sorted events by timestamp
const sortedEvents = computed(() => {
  return [...props.events].sort((a, b) => a.timestamp - b.timestamp)
})

// Progress percentage
const progressPercent = computed(() => {
  if (props.duration === 0) return 0
  return (props.currentTime / props.duration) * 100
})

// Get event position on timeline
function getEventPosition(event: TimelineEvent): number {
  if (props.duration === 0) return 0
  return (event.timestamp / props.duration) * 100
}

// Get event CSS class based on type
function getEventClass(event: TimelineEvent): string {
  const type = event.type.toLowerCase()
  if (type.includes('error') || type.includes('fail')) return 'error'
  if (type.includes('tool')) return 'tool'
  if (type.includes('step')) return 'step'
  if (type.includes('message')) return 'message'
  return 'default'
}

// Get event tooltip text
function getEventTooltip(event: TimelineEvent): string {
  const time = formatTime(event.timestamp)
  return `${event.name} at ${time}`
}

function formatTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

// Handle click on timeline
function handleTimelineClick(e: MouseEvent): void {
  if (!timelineBar.value || props.duration === 0) return

  const rect = timelineBar.value.getBoundingClientRect()
  const percent = (e.clientX - rect.left) / rect.width
  const time = Math.max(0, Math.min(props.duration, percent * props.duration))

  emit('seek', time)
}

// Handle event marker click
function handleEventClick(event: TimelineEvent): void {
  emit('eventClick', event)
}

// Drag handling for scrubbing
function startDrag(e: MouseEvent): void {
  isDragging.value = true
  handleTimelineClick(e)

  const onMouseMove = (moveEvent: MouseEvent) => {
    if (isDragging.value) {
      handleTimelineClick(moveEvent)
    }
  }

  const onMouseUp = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}
</script>

<style scoped>
.replay-timeline {
  padding: 8px 16px 12px;
  background: var(--background-gray-secondary, #222);
}

.timeline-bar {
  position: relative;
  height: 24px;
  background: var(--background-tertiary, #2a2a2a);
  border-radius: 4px;
  cursor: pointer;
  overflow: visible;
}

.timeline-progress {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg, #10b981, #059669);
  border-radius: 4px 0 0 4px;
  pointer-events: none;
}

.timeline-playhead {
  position: absolute;
  top: -2px;
  width: 4px;
  height: 28px;
  background: #10b981;
  border-radius: 2px;
  transform: translateX(-50%);
  pointer-events: none;
  box-shadow: 0 0 4px rgba(16, 185, 129, 0.5);
}

.event-marker {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  cursor: pointer;
  z-index: 1;
  padding: 4px;
}

.marker-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #888;
  transition: all 0.2s;
}

.event-marker:hover .marker-dot {
  transform: scale(1.5);
  box-shadow: 0 0 6px currentColor;
}

.event-marker.tool .marker-dot {
  background: #3b82f6;
}

.event-marker.step .marker-dot {
  background: #8b5cf6;
}

.event-marker.error .marker-dot {
  background: #ef4444;
}

.event-marker.message .marker-dot {
  background: #10b981;
}

.timeline-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color, #333);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted, #888);
}

.legend-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.legend-dot.tool {
  background: #3b82f6;
}

.legend-dot.step {
  background: #8b5cf6;
}

.legend-dot.error {
  background: #ef4444;
}

.legend-dot.message {
  background: #10b981;
}
</style>
