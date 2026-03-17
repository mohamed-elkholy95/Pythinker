<template>
  <div
    :class="[
      'absolute w-1.5 h-1.5 rounded-full transform -translate-x-1/2 top-0.5 cursor-pointer transition-all',
      markerClass,
      active ? 'scale-150 ring-2 ring-offset-1 ring-[var(--Button-primary-black)]' : ''
    ]"
    :style="{ left: `${position}%` }"
    :title="markerTitle"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  position: number
  type: string
  active?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  active: false,
})

// Map event types to colors
const markerClass = computed(() => {
  switch (props.type) {
    case 'message':
      return 'bg-blue-500'
    case 'tool':
      return 'bg-purple-500'
    case 'step':
      return 'bg-green-500'
    case 'plan':
      return 'bg-orange-500'
    case 'error':
      return 'bg-red-500'
    case 'done':
      return 'bg-emerald-500'
    default:
      return 'bg-gray-400'
  }
})

// Tooltip text
const markerTitle = computed(() => {
  const typeLabels: Record<string, string> = {
    message: 'Message',
    tool: 'Tool Call',
    step: 'Step',
    plan: 'Plan',
    error: 'Error',
    done: 'Complete',
    wait: 'Waiting',
    title: 'Title Update',
    stream: 'Stream',
    attachments: 'Attachments',
    mode_change: 'Mode Change',
    suggestion: 'Suggestion',
    report: 'Report',
  }
  return typeLabels[props.type] || props.type
})
</script>
