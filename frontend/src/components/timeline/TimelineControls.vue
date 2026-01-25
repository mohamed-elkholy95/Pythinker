<template>
  <div class="timeline-controls px-4 py-3 bg-[var(--background-menu-white)] border-t border-black/8 dark:border-[var(--border-main)]">
    <!-- Jump to Live Button (shown when not in live mode) -->
    <div
      v-if="!isLive"
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

    <!-- Timestamp Display -->
    <div
      v-if="currentTimestamp"
      class="flex items-center justify-center mb-3"
    >
      <div class="px-3 py-1 bg-blue-500 text-white text-xs font-medium rounded-full">
        {{ formattedTimestamp }}
      </div>
    </div>

    <!-- Main Controls Row -->
    <div class="flex items-center gap-3">
      <!-- Step Controls -->
      <div class="flex items-center gap-1">
        <!-- Step Backward -->
        <button
          @click="$emit('stepBackward')"
          :disabled="!canStepBackward"
          class="p-1.5 rounded hover:bg-[var(--fill-tsp-gray-main)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Previous action"
        >
          <SkipBack class="w-4 h-4 text-[var(--icon-primary)]" />
        </button>

        <!-- Step Forward -->
        <button
          @click="$emit('stepForward')"
          :disabled="!canStepForward"
          class="p-1.5 rounded hover:bg-[var(--fill-tsp-gray-main)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Next action"
        >
          <SkipForward class="w-4 h-4 text-[var(--icon-primary)]" />
        </button>
      </div>

      <!-- Timeline Scrubber -->
      <div class="flex-1 relative">
        <div
          ref="scrubberRef"
          class="scrubber-track relative h-1 bg-[var(--fill-tsp-gray-main)] rounded-full cursor-pointer group"
          @click="handleScrubberClick"
          @mousedown="startDragging"
        >
          <!-- Progress Fill -->
          <div
            class="absolute h-full bg-blue-500 rounded-full transition-[width] duration-100"
            :style="{ width: `${progress}%` }"
          />

          <!-- Scrubber Thumb -->
          <div
            class="scrubber-thumb absolute w-3 h-3 bg-blue-500 rounded-full -top-1 transform -translate-x-1/2 shadow-md transition-transform hover:scale-125"
            :style="{ left: `${progress}%` }"
          />
        </div>
      </div>

      <!-- Live Indicator -->
      <div class="flex items-center gap-1.5 min-w-[50px] justify-end">
        <span
          class="w-2 h-2 rounded-full"
          :class="isLive ? 'bg-green-500 animate-pulse' : 'bg-gray-400'"
        />
        <span
          class="text-xs font-medium"
          :class="isLive ? 'text-green-600 dark:text-green-400' : 'text-[var(--text-tertiary)]'"
        >
          live
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
  canStepForward: boolean
  canStepBackward: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  jumpToLive: []
  stepForward: []
  stepBackward: []
  seekByProgress: [progress: number]
}>()

const scrubberRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)

// Format timestamp for display
const formattedTimestamp = computed(() => {
  if (!props.currentTimestamp) return ''

  const date = new Date(props.currentTimestamp * 1000)
  return date.toLocaleString('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
})

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
  const percentage = Math.max(0, Math.min(100, (clickX / rect.width) * 100))

  emit('seekByProgress', percentage)
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

.scrubber-track {
  touch-action: none;
}

.scrubber-thumb {
  cursor: grab;
}

.scrubber-thumb:active {
  cursor: grabbing;
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
