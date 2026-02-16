<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Arrow/chevron (animated) -->
    <path class="icon-glyph arrow-path" d="M2 2L7.5 8L2 14" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />

    <!-- Terminal line -->
    <path class="icon-glyph" d="M9 14H14" stroke-width="1.3" stroke-linecap="round" />

    <!-- Blinking cursor at the end of the line -->
    <rect class="cursor" x="14.2" y="12.5" width="1.2" height="3" rx="0.3" />
  </svg>
</template>

<script setup lang="ts">
defineProps({
  size: { type: Number, default: 21 },
});
</script>

<style scoped>
.icon-glyph {
  stroke: var(--icon-secondary, #535350);
  fill: none;
}

/* Arrow pulse animation */
.arrow-path {
  animation: arrow-pulse 1.5s ease-in-out infinite;
}

@keyframes arrow-pulse {
  0%, 100% {
    opacity: 1;
    transform: translateX(0);
  }
  50% {
    opacity: 0.5;
    transform: translateX(0.5px);
  }
}

/* Blinking cursor */
.cursor {
  fill: var(--icon-secondary, #535350);
  animation: cursor-blink 1.2s step-end infinite;
}

@keyframes cursor-blink {
  0%, 49% {
    opacity: 1;
  }
  50%, 100% {
    opacity: 0;
  }
}
</style>
