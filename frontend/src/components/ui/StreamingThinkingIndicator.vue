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
        <span class="thinking-text-shimmer text-sm font-normal">Thinking</span>
        <div
          v-if="displayText"
          ref="thinkingTextRef"
          class="mt-1 text-sm text-[var(--text-secondary)] whitespace-pre-wrap thinking-text"
        >
          {{ displayText }}<span class="cursor-blink">|</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import ThinkingIndicator from './ThinkingIndicator.vue'

const props = defineProps<{
  text: string
  maxLines?: number
}>()

const thinkingTextRef = ref<HTMLDivElement | null>(null)

// Auto-truncate to last N lines for long thinking text
const displayText = computed(() => {
  const maxLines = props.maxLines ?? 8
  const lines = props.text.split('\n')
  if (lines.length <= maxLines) {
    return props.text
  }
  return '...\n' + lines.slice(-maxLines).join('\n')
})

const scrollThinkingToBottom = async () => {
  await nextTick()
  if (!thinkingTextRef.value) return
  thinkingTextRef.value.scrollTop = thinkingTextRef.value.scrollHeight
}

watch(
  () => displayText.value,
  () => {
    scrollThinkingToBottom()
  },
  { immediate: true }
)
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

/* 120-degree diagonal shimmer text effect */
.thinking-text-shimmer {
  background: linear-gradient(
    120deg,
    #1f2937 0%,
    #1f2937 40%,
    #9ca3af 50%,
    #1f2937 60%,
    #1f2937 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2s ease-in-out infinite;
}

/* Dark mode */
:deep(.dark) .thinking-text-shimmer,
.dark .thinking-text-shimmer {
  background: linear-gradient(
    120deg,
    #e5e7eb 0%,
    #e5e7eb 40%,
    #6b7280 50%,
    #e5e7eb 60%,
    #e5e7eb 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

@keyframes text-shimmer {
  0% {
    background-position: 100% 0%;
  }
  100% {
    background-position: 0% 100%;
  }
}
</style>
