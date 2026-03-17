<template>
  <div class="timeline-header flex items-center gap-2 px-4 py-2 bg-[var(--background-menu-white)] border-b border-black/8 dark:border-[var(--border-main)]">
    <!-- Tool Icon -->
    <component
      :is="toolIcon"
      class="w-4 h-4 text-[var(--icon-primary)]"
    />

    <!-- Status Text -->
    <span class="text-sm text-[var(--text-secondary)]">
      {{ statusText }}
    </span>

    <!-- Separator -->
    <span v-if="displayResource" class="text-[var(--text-tertiary)]">|</span>

    <!-- Resource Name -->
    <span v-if="displayResource" class="text-sm text-[var(--text-primary)] truncate max-w-[300px]" :title="displayResource">
      {{ displayResource }}
    </span>

    <!-- Spacer -->
    <div class="flex-1" />

    <!-- Window Controls (optional, for modal mode) -->
    <div v-if="showWindowControls" class="flex items-center gap-1">
      <button
        @click="$emit('minimize')"
        class="p-1 rounded hover:bg-[var(--fill-tsp-gray-main)] transition-colors"
      >
        <Minus class="w-3 h-3 text-[var(--icon-primary)]" />
      </button>
      <button
        @click="$emit('maximize')"
        class="p-1 rounded hover:bg-[var(--fill-tsp-gray-main)] transition-colors"
      >
        <Square class="w-3 h-3 text-[var(--icon-primary)]" />
      </button>
      <button
        @click="$emit('close')"
        class="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
      >
        <X class="w-3 h-3 text-[var(--icon-primary)] hover:text-red-500" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Minus, Square, X, Settings } from 'lucide-vue-next'
import { getToolDisplay } from '@/utils/toolDisplay'

interface Props {
  toolName?: string
  functionName?: string
  resourceName?: string
  showWindowControls?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  toolName: '',
  functionName: '',
  resourceName: '',
  showWindowControls: false,
})

defineEmits<{
  minimize: []
  maximize: []
  close: []
}>()

const toolDisplay = computed(() => getToolDisplay({
  name: props.toolName,
  function: props.functionName
}))

const toolIcon = computed(() => toolDisplay.value.icon || Settings)

const displayResource = computed(() => {
  return props.resourceName || toolDisplay.value.description
})

// Generate status text
const statusText = computed(() => {
  return toolDisplay.value.displayName || 'Tool'
})
</script>

<style scoped>
.timeline-header {
  user-select: none;
}
</style>
