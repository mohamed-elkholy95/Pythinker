<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Arrow/chevron (animated) -->
    <path class="icon-glyph arrow-path" d="M2 2L7.5 8L2 14" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />

    <!-- Terminal line -->
    <path class="icon-glyph" d="M9 14H13.5" stroke-width="1.3" stroke-linecap="round" />

    <!-- Breathing animated dash -->
    <line class="terminal-dash" x1="14" y1="14" x2="15" y2="14" stroke-width="1.3" stroke-linecap="round" />
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

/* Arrow slide animation - smooth slide in */
.arrow-path {
  animation: arrow-slide 1.5s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  transform-origin: center;
}

@keyframes arrow-slide {
  0%, 100% {
    transform: translateX(0);
    opacity: 1;
  }
  50% {
    transform: translateX(2px);
    opacity: 0.6;
  }
}

/* Breathing dash animation - organic pulse */
.terminal-dash {
  stroke: var(--icon-secondary, #535350);
  animation: dash-breathe 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  transform-origin: center;
}

@keyframes dash-breathe {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.3;
    transform: scale(0.8);
  }
}

/* Reduce motion for accessibility */
@media (prefers-reduced-motion: reduce) {
  .arrow-path,
  .terminal-dash {
    animation: none;
    opacity: 1;
    transform: none;
  }
}
</style>
