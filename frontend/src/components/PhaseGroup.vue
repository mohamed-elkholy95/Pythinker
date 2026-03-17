<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { CheckIcon, TargetIcon, SearchIcon, BrainIcon, FileTextIcon, ShieldCheckIcon, SendIcon, MinusIcon } from 'lucide-vue-next'
import type { PhaseContent, ToolContent } from '../types/message'

const props = defineProps<{
  phase: PhaseContent
  activeThinkingStepId?: string
  isLoading?: boolean
}>()

const emit = defineEmits<{
  toolClick: [tool: ToolContent]
}>()

const isExpanded = ref(true)
const userToggled = ref(false)

// Auto-expand active phase, collapse completed (unless user toggled)
watch(
  () => props.phase.status,
  (status) => {
    if (userToggled.value) return
    isExpanded.value = status === 'started'
  },
)

const toggleExpand = () => {
  userToggled.value = true
  isExpanded.value = !isExpanded.value
}

const completedSteps = computed(() =>
  props.phase.steps.filter((s) => s.status === 'completed').length,
)

const totalSteps = computed(() => props.phase.steps.length)

const progressText = computed(() => {
  if (totalSteps.value === 0) return ''
  if (completedSteps.value === totalSteps.value) return `${totalSteps.value} steps`
  return `${completedSteps.value}/${totalSteps.value}`
})

const isActive = computed(() => props.phase.status === 'started')
const isCompleted = computed(() => props.phase.status === 'completed')
const isSkipped = computed(() => props.phase.status === 'skipped')

// Map phase icon names to components
const iconComponent = computed(() => {
  const map: Record<string, unknown> = {
    target: TargetIcon,
    search: SearchIcon,
    brain: BrainIcon,
    'file-text': FileTextIcon,
    'shield-check': ShieldCheckIcon,
    send: SendIcon,
  }
  return map[props.phase.icon] || TargetIcon
})

// Color classes based on phase color
const colorClasses = computed(() => {
  const map: Record<string, { bg: string; border: string; text: string; iconBg: string }> = {
    blue: {
      bg: 'bg-blue-500/5',
      border: 'border-blue-500/20',
      text: 'text-blue-400',
      iconBg: 'bg-blue-500/15',
    },
    purple: {
      bg: 'bg-purple-500/5',
      border: 'border-purple-500/20',
      text: 'text-purple-400',
      iconBg: 'bg-purple-500/15',
    },
    amber: {
      bg: 'bg-amber-500/5',
      border: 'border-amber-500/20',
      text: 'text-amber-400',
      iconBg: 'bg-amber-500/15',
    },
    green: {
      bg: 'bg-green-500/5',
      border: 'border-green-500/20',
      text: 'text-green-400',
      iconBg: 'bg-green-500/15',
    },
    orange: {
      bg: 'bg-orange-500/5',
      border: 'border-orange-500/20',
      text: 'text-orange-400',
      iconBg: 'bg-orange-500/15',
    },
    emerald: {
      bg: 'bg-emerald-500/5',
      border: 'border-emerald-500/20',
      text: 'text-emerald-400',
      iconBg: 'bg-emerald-500/15',
    },
  }
  return map[props.phase.color] || map.blue
})

const handleToolClick = (tool: ToolContent) => {
  emit('toolClick', tool)
}
</script>

<template>
  <div
    class="phase-group"
    :class="[
      isActive ? 'phase-active' : '',
      isCompleted ? 'phase-completed' : '',
      isSkipped ? 'phase-skipped opacity-50' : '',
    ]"
  >
    <!-- Phase Header -->
    <div
      class="phase-header flex items-center gap-3 px-3 py-2.5 cursor-pointer select-none rounded-lg transition-colors duration-150"
      :class="[colorClasses.bg, `hover:${colorClasses.bg}`]"
      @click="toggleExpand"
    >
      <!-- Phase Status Icon -->
      <div
        class="phase-icon w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
        :class="colorClasses.iconBg"
      >
        <CheckIcon
          v-if="isCompleted"
          :size="14"
          :stroke-width="2.5"
          class="text-green-400"
        />
        <MinusIcon
          v-else-if="isSkipped"
          :size="14"
          :stroke-width="2.5"
          class="text-[var(--text-tertiary)]"
        />
        <component
          :is="iconComponent"
          v-else
          :size="14"
          :stroke-width="2"
          :class="[isActive ? colorClasses.text : 'text-[var(--text-tertiary)]']"
        />
      </div>

      <!-- Phase Label -->
      <div class="flex-1 min-w-0">
        <span
          class="phase-label text-sm font-medium truncate"
          :class="[
            isActive ? 'text-[var(--text-primary)]' : '',
            isCompleted ? 'text-[var(--text-secondary)]' : '',
            isSkipped ? 'text-[var(--text-tertiary)] line-through' : '',
            !isActive && !isCompleted && !isSkipped ? 'text-[var(--text-tertiary)]' : '',
          ]"
        >
          {{ phase.label }}
        </span>
      </div>

      <!-- Progress Badge -->
      <div
        v-if="totalSteps > 0"
        class="phase-progress text-xs text-[var(--text-tertiary)] flex-shrink-0"
      >
        {{ progressText }}
      </div>

      <!-- Chevron -->
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="transition-transform duration-200 text-[var(--text-tertiary)] flex-shrink-0"
        :class="{ 'rotate-180': isExpanded }"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>

      <!-- Active pulse indicator -->
      <span
        v-if="isActive"
        class="phase-pulse w-2 h-2 rounded-full flex-shrink-0"
        :class="colorClasses.text.replace('text-', 'bg-')"
      />
    </div>

    <!-- Phase Steps (collapsible) -->
    <div
      class="phase-steps overflow-hidden transition-[max-height,opacity] duration-200 ease-in-out"
      :class="isExpanded ? 'max-h-[100000px] opacity-100' : 'max-h-0 opacity-0'"
    >
      <div class="phase-steps-inner pl-6 pt-1 pb-1">
        <slot
          name="steps"
          :steps="phase.steps"
          :activeThinkingStepId="activeThinkingStepId"
          :isLoading="isLoading"
          :onToolClick="handleToolClick"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.phase-group {
  margin-bottom: 2px;
}

.phase-group + .phase-group {
  margin-top: 2px;
}

.phase-pulse {
  animation: phase-pulse-anim 1.5s ease-in-out infinite;
}

@keyframes phase-pulse-anim {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
</style>
