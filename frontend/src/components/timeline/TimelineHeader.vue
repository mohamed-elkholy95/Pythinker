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
    <span class="text-[var(--text-tertiary)]">|</span>

    <!-- Resource Name -->
    <span class="text-sm text-[var(--text-primary)] truncate max-w-[300px]" :title="resourceName">
      {{ resourceName }}
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
import {
  Edit3,
  FileText,
  Globe,
  Terminal,
  Search,
  Code,
  Settings,
  Zap,
  Eye,
  Minus,
  Square,
  X,
} from 'lucide-vue-next'

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

// Map tool names to icons
const toolIcon = computed(() => {
  const name = props.toolName?.toLowerCase() || ''
  const funcName = props.functionName?.toLowerCase() || ''

  if (name.includes('browser') || name.includes('playwright')) {
    return Globe
  }
  if (name.includes('file') || funcName.includes('write') || funcName.includes('read')) {
    return FileText
  }
  if (name.includes('shell') || name.includes('terminal') || funcName.includes('execute')) {
    return Terminal
  }
  if (name.includes('search')) {
    return Search
  }
  if (name.includes('code') || funcName.includes('code')) {
    return Code
  }
  if (funcName.includes('edit')) {
    return Edit3
  }
  if (name.includes('mcp')) {
    return Zap
  }
  if (name.includes('vision') || funcName.includes('screenshot')) {
    return Eye
  }

  return Settings
})

// Generate status text
const statusText = computed(() => {
  const tool = props.toolName || 'Agent'
  const func = props.functionName

  if (func) {
    // Convert function names to readable format
    const readable = func
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .trim()

    return `${tool} is using ${readable}...`
  }

  return `${tool} is working...`
})
</script>

<style scoped>
.timeline-header {
  user-select: none;
}
</style>
