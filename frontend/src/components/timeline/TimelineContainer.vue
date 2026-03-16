<template>
  <div class="timeline-container flex flex-col h-full bg-[var(--background-main)] rounded-xl overflow-hidden shadow-xl border border-black/10 dark:border-[var(--border-main)]">
    <!-- Header Bar -->
    <TimelineHeader
      :tool-name="currentToolName"
      :function-name="currentFunctionName"
      :resource-name="currentResourceName"
      :show-window-controls="showWindowControls"
      @minimize="$emit('minimize')"
      @maximize="$emit('maximize')"
      @close="$emit('close')"
    />

    <!-- Content Viewport -->
    <div class="viewport flex-1 overflow-hidden relative">
      <!-- Filename Tab (if showing file) -->
      <div
        v-if="currentResourceName"
        class="filename-tab flex items-center justify-center py-2 border-b border-black/5 dark:border-[var(--border-main)] bg-[var(--background-surface)]"
      >
        <span class="text-xs text-[var(--text-secondary)] font-medium uppercase tracking-wide">
          {{ displayFileName }}
        </span>
      </div>

      <!-- Content Area -->
      <div class="content-area h-full overflow-auto">
        <slot name="content">
          <!-- Default content slot -->
          <div class="flex items-center justify-center h-full text-[var(--text-tertiary)]">
            No content to display
          </div>
        </slot>
      </div>

      <!-- Replay Overlay (when in replay mode) -->
      <div
        v-if="mode === 'replay' && isPlaying"
        class="replay-indicator absolute top-4 right-4 flex items-center gap-2 px-3 py-1.5 bg-black/70 text-white text-xs rounded-full"
      >
        <div class="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
        <span>Replaying {{ playbackSpeed }}x</span>
      </div>
    </div>

    <!-- Timeline Controls -->
    <TimelineControls
      :progress="progress"
      :current-timestamp="currentTimestamp"
      :is-live="isLive"
      :can-step-forward="canStepForward"
      :can-step-backward="canStepBackward"
      @jump-to-live="$emit('jumpToLive')"
      @step-forward="$emit('stepForward')"
      @step-backward="$emit('stepBackward')"
      @seek-by-progress="handleSeekByProgress"
    />

    <!-- Task Progress Footer (optional) -->
    <TimelineProgressFooter
      v-if="steps.length > 0"
      :steps="steps"
      :current-step-index="currentStepIndex"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TimelineHeader from './TimelineHeader.vue'
import TimelineControls from './TimelineControls.vue'
import TimelineProgressFooter from './TimelineProgressFooter.vue'
import type { TimelineMode } from '@/composables/useTimeline'

interface Step {
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed'
}

interface Props {
  // Timeline state
  mode: TimelineMode
  progress: number
  isLive: boolean
  isPlaying: boolean
  playbackSpeed: number
  canStepForward: boolean
  canStepBackward: boolean

  // Current event info
  currentTimestamp?: number
  currentToolName?: string
  currentFunctionName?: string
  currentResourceName?: string

  // Task progress
  steps?: Step[]
  currentStepIndex?: number

  // UI options
  showWindowControls?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  currentTimestamp: undefined,
  currentToolName: '',
  currentFunctionName: '',
  currentResourceName: '',
  steps: () => [],
  currentStepIndex: -1,
  showWindowControls: false,
})

const emit = defineEmits<{
  jumpToLive: []
  stepForward: []
  stepBackward: []
  seekByProgress: [progress: number]
  minimize: []
  maximize: []
  close: []
}>()

// Computed display filename
const displayFileName = computed(() => {
  if (!props.currentResourceName) return ''

  // Extract filename from path
  const parts = props.currentResourceName.split('/')
  return parts[parts.length - 1] || props.currentResourceName
})

// Handle seek by progress
const handleSeekByProgress = (progress: number) => {
  emit('seekByProgress', progress)
}
</script>

<style scoped>
.timeline-container {
  min-height: 400px;
  max-height: 80vh;
}

.viewport {
  min-height: 200px;
}

.content-area {
  scrollbar-width: thin;
  scrollbar-color: var(--fill-tsp-gray-main) transparent;
}

.content-area::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.content-area::-webkit-scrollbar-track {
  background: transparent;
}

.content-area::-webkit-scrollbar-thumb {
  background: var(--fill-tsp-gray-main);
  border-radius: 3px;
}

.content-area::-webkit-scrollbar-thumb:hover {
  background: var(--fill-tsp-gray-dark);
}

.replay-indicator {
  backdrop-filter: blur(4px);
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
