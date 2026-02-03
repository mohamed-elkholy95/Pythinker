<template>
  <div class="step-thought">
    <p class="text-[14px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
      {{ content.text }}
    </p>
  </div>
</template>

<script setup lang="ts">
import type { ThoughtContent } from '../types/message';

defineProps<{
  content: ThoughtContent;
}>();
</script>

<style scoped>
.step-thought {
  padding: 4px 0 8px 0;
}
</style>
