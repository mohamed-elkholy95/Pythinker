<template>
  <div class="w-full h-full flex flex-col overflow-hidden" :class="isWriting ? 'writing-active' : ''">
    <section class="flex-1 min-h-0 relative w-full h-full">
      <MonacoEditor
        :value="content"
        :filename="filename"
        :read-only="true"
        theme="vs"
        :line-numbers="'off'"
        :word-wrap="'on'"
        :minimap="false"
        :scroll-beyond-last-line="false"
        :automatic-layout="true"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import MonacoEditor from '@/components/ui/MonacoEditor.vue';

defineProps<{
  content: string;
  filename?: string;
  isWriting?: boolean;
}>();
</script>

<style scoped>
/* Subtle pulsing effect when file is being written */
.writing-active {
  position: relative;
}

.writing-active::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid transparent;
  border-radius: 0 0 12px 12px;
  pointer-events: none;
  animation: writing-pulse 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes writing-pulse {
  0%, 100% {
    border-color: rgba(59, 130, 246, 0.1);
  }
  50% {
    border-color: rgba(59, 130, 246, 0.3);
  }
}
</style>
