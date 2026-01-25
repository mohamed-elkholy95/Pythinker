<template>
  <div class="flex flex-col">
    <div class="flex">
      <div class="w-[24px] relative h-4">
        <div class="border-l border-dashed border-[var(--border-dark)] absolute start-[8px] top-0 bottom-0"></div>
      </div>
      <div class="flex-1"></div>
    </div>
    <div class="flex items-start">
      <div class="w-[24px] flex items-center justify-center flex-shrink-0" style="padding-left: 3px; padding-top: 4px;">
        <div class="thinking-shape-wrapper">
          <ThinkingIndicator :showText="false" />
        </div>
      </div>
      <div class="flex-1 min-w-0">
        <span class="text-sm font-medium text-black dark:text-white">Thinking</span>
        <div v-if="displayText" class="mt-1 text-sm text-[var(--text-secondary)] whitespace-pre-wrap thinking-text">
          {{ displayText }}<span class="cursor-blink">|</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ThinkingIndicator from './ThinkingIndicator.vue'

const props = defineProps<{
  text: string
  maxLines?: number
}>()

// Auto-truncate to last N lines for long thinking text
const displayText = computed(() => {
  const maxLines = props.maxLines ?? 8
  const lines = props.text.split('\n')
  if (lines.length <= maxLines) {
    return props.text
  }
  return '...\n' + lines.slice(-maxLines).join('\n')
})
</script>

<style scoped>
.thinking-text {
  line-height: 1.5;
  max-height: 200px;
  overflow-y: auto;
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  color: var(--text-primary);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
