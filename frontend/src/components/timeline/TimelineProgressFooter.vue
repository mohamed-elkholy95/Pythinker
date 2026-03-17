<template>
  <div class="timeline-progress-footer">
    <!-- Main Footer Bar -->
    <div
      class="flex items-center gap-3 px-4 py-2 bg-[var(--background-menu-white)] border-t border-black/8 dark:border-[var(--border-main)] cursor-pointer hover:bg-[var(--fill-tsp-gray-light)] transition-colors"
      @click="isExpanded = !isExpanded"
    >
      <!-- Status Icon -->
      <component
        :is="statusIcon"
        class="w-4 h-4"
        :class="statusIconClass"
      />

      <!-- Task Description -->
      <span class="flex-1 text-sm text-[var(--text-primary)] truncate">
        {{ currentTaskDescription }}
      </span>

      <!-- Progress Counter -->
      <span class="text-sm text-[var(--text-secondary)] font-medium">
        {{ completedSteps }} / {{ totalSteps }}
      </span>

      <!-- Expand Toggle -->
      <ChevronUp
        class="w-4 h-4 text-[var(--icon-primary)] transition-transform"
        :class="{ 'rotate-180': !isExpanded }"
      />
    </div>

    <!-- Expanded Task List -->
    <Transition name="slide">
      <div
        v-if="isExpanded"
        class="task-list px-4 py-3 bg-[var(--background-surface)] border-t border-black/5 dark:border-[var(--border-main)] max-h-[200px] overflow-y-auto"
      >
        <div
          v-for="(step, index) in steps"
          :key="index"
          class="flex items-center gap-2 py-1.5"
          :class="{
            'opacity-50': step.status === 'pending',
            'text-green-600 dark:text-green-400': step.status === 'completed',
          }"
        >
          <!-- Step Status Icon -->
          <component
            :is="getStepIcon(step.status)"
            class="w-3.5 h-3.5 flex-shrink-0"
            :class="getStepIconClass(step.status)"
          />

          <!-- Step Description -->
          <span class="text-sm truncate">
            {{ step.description }}
          </span>
        </div>

        <div v-if="steps.length === 0" class="text-sm text-[var(--text-tertiary)] text-center py-2">
          No steps available
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Check,
  Circle,
  Loader2,
  AlertCircle,
  ChevronUp,
  CheckCircle2,
} from 'lucide-vue-next'

interface Step {
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed'
}

interface Props {
  steps: Step[]
  currentStepIndex?: number
}

const props = withDefaults(defineProps<Props>(), {
  currentStepIndex: -1,
})

const isExpanded = ref(false)

// Computed properties
const completedSteps = computed(() =>
  props.steps.filter(s => s.status === 'completed').length
)

const totalSteps = computed(() => props.steps.length)

const currentStep = computed(() => {
  if (props.currentStepIndex >= 0 && props.currentStepIndex < props.steps.length) {
    return props.steps[props.currentStepIndex]
  }
  // Find first non-completed step
  return props.steps.find(s => s.status !== 'completed') || props.steps[props.steps.length - 1]
})

const currentTaskDescription = computed(() => {
  return currentStep.value?.description || 'No active task'
})

const isAllCompleted = computed(() =>
  props.steps.length > 0 && props.steps.every(s => s.status === 'completed')
)

const hasError = computed(() =>
  props.steps.some(s => s.status === 'failed')
)

// Status icon for main bar
const statusIcon = computed(() => {
  if (hasError.value) return AlertCircle
  if (isAllCompleted.value) return CheckCircle2
  if (currentStep.value?.status === 'running') return Loader2
  return Check
})

const statusIconClass = computed(() => {
  if (hasError.value) return 'text-red-500'
  if (isAllCompleted.value) return 'text-green-500'
  if (currentStep.value?.status === 'running') return 'text-blue-500 animate-spin'
  return 'text-green-500'
})

// Get icon for individual step
const getStepIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return Check
    case 'running':
      return Loader2
    case 'failed':
      return AlertCircle
    default:
      return Circle
  }
}

const getStepIconClass = (status: string) => {
  switch (status) {
    case 'completed':
      return 'text-green-500'
    case 'running':
      return 'text-blue-500 animate-spin'
    case 'failed':
      return 'text-red-500'
    default:
      return 'text-[var(--text-tertiary)]'
  }
}
</script>

<style scoped>
.timeline-progress-footer {
  user-select: none;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
}

.slide-enter-to,
.slide-leave-from {
  max-height: 200px;
  opacity: 1;
}

.task-list::-webkit-scrollbar {
  width: 4px;
}

.task-list::-webkit-scrollbar-track {
  background: transparent;
}

.task-list::-webkit-scrollbar-thumb {
  background: var(--fill-tsp-gray-main);
  border-radius: 2px;
}
</style>
