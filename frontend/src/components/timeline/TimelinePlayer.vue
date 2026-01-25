<template>
  <div
    v-if="isVisible"
    class="timeline-player bg-[var(--background-menu-white)] border border-black/8 dark:border-[var(--border-main)] rounded-xl shadow-lg px-4 py-3"
  >
    <!-- Progress Bar -->
    <div class="mb-3">
      <div
        ref="progressBar"
        class="relative h-2 bg-[var(--fill-tsp-gray-main)] rounded-full cursor-pointer group"
        @click="handleProgressClick"
      >
        <!-- Progress Fill -->
        <div
          class="absolute h-full bg-[var(--Button-primary-black)] rounded-full transition-all"
          :style="{ width: `${progress}%` }"
        />
        <!-- Scrubber Handle -->
        <div
          class="absolute w-4 h-4 bg-[var(--Button-primary-black)] rounded-full -top-1 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity shadow-md"
          :style="{ left: `${progress}%` }"
        />
        <!-- Event Markers -->
        <TimelineMarker
          v-for="(marker, index) in eventMarkers"
          :key="index"
          :position="marker.position"
          :type="marker.type"
          :active="index === currentIndex"
          @click.stop="seek(index)"
        />
      </div>
    </div>

    <!-- Controls -->
    <div class="flex items-center justify-between">
      <!-- Left: Time Display -->
      <div class="flex items-center gap-2 text-xs text-[var(--text-tertiary)] font-mono min-w-[100px]">
        <span>{{ formatTime(currentTime) }}</span>
        <span>/</span>
        <span>{{ formatTime(duration) }}</span>
      </div>

      <!-- Center: Playback Controls -->
      <div class="flex items-center gap-2">
        <!-- Step Backward -->
        <button
          @click="stepBackward"
          :disabled="currentIndex === 0"
          class="p-1.5 rounded-md hover:bg-[var(--fill-tsp-gray-main)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <SkipBack class="w-4 h-4 text-[var(--icon-primary)]" />
        </button>

        <!-- Play/Pause -->
        <button
          @click="togglePlay"
          class="p-2 rounded-full bg-[var(--Button-primary-black)] hover:opacity-90 transition-opacity"
        >
          <Pause v-if="isPlaying" class="w-4 h-4 text-white" />
          <Play v-else class="w-4 h-4 text-white" />
        </button>

        <!-- Step Forward -->
        <button
          @click="stepForward"
          :disabled="currentIndex >= totalEvents - 1"
          class="p-1.5 rounded-md hover:bg-[var(--fill-tsp-gray-main)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <SkipForward class="w-4 h-4 text-[var(--icon-primary)]" />
        </button>
      </div>

      <!-- Right: Speed Control -->
      <div class="flex items-center gap-2 min-w-[100px] justify-end">
        <button
          @click="cycleSpeed"
          class="text-xs px-2 py-1 rounded-md bg-[var(--fill-tsp-gray-main)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-gray-dark)] transition-colors"
        >
          {{ playbackSpeed }}x
        </button>
        <span class="text-xs text-[var(--text-tertiary)]">
          {{ currentIndex + 1 }} / {{ totalEvents }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Play, Pause, SkipBack, SkipForward } from 'lucide-vue-next'
import TimelineMarker from './TimelineMarker.vue'
import { formatTime } from '@/composables/useTimeline'
import type { AgentSSEEvent } from '@/types/event'

interface Props {
  events: AgentSSEEvent[]
  currentIndex: number
  isPlaying: boolean
  playbackSpeed: number
  currentTime: number
  duration: number
  progress: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  play: []
  pause: []
  seek: [index: number]
  seekByTime: [time: number]
  setSpeed: [speed: number]
  stepForward: []
  stepBackward: []
}>()

const progressBar = ref<HTMLElement | null>(null)

// Compute visibility based on events
const isVisible = computed(() => props.events.length > 0)

const totalEvents = computed(() => props.events.length)

// Calculate event markers for the progress bar
const eventMarkers = computed(() => {
  if (props.duration === 0) return []

  const startTime = props.events.length > 0
    ? Math.min(...props.events.map(e => e.data.timestamp || 0))
    : 0

  return props.events.map((event, index) => {
    const eventTime = (event.data.timestamp || 0) - startTime
    const position = props.duration > 0 ? (eventTime / props.duration) * 100 : 0

    return {
      position,
      type: event.event,
      index,
    }
  })
})

// Speed options
const speedOptions = [0.5, 1.0, 1.5, 2.0, 4.0]

// Toggle play/pause
const togglePlay = () => {
  if (props.isPlaying) {
    emit('pause')
  } else {
    emit('play')
  }
}

// Cycle through speed options
const cycleSpeed = () => {
  const currentIndex = speedOptions.indexOf(props.playbackSpeed)
  const nextIndex = (currentIndex + 1) % speedOptions.length
  emit('setSpeed', speedOptions[nextIndex])
}

// Handle click on progress bar
const handleProgressClick = (event: MouseEvent) => {
  if (!progressBar.value) return

  const rect = progressBar.value.getBoundingClientRect()
  const clickX = event.clientX - rect.left
  const percentage = clickX / rect.width
  const targetTime = props.duration * percentage

  emit('seekByTime', targetTime)
}

// Step controls
const stepForward = () => emit('stepForward')
const stepBackward = () => emit('stepBackward')

// Seek to specific index
const seek = (index: number) => emit('seek', index)
</script>

<style scoped>
.timeline-player {
  user-select: none;
}
</style>
