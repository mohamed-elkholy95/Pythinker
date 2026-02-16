<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Clock circle -->
    <circle class="icon-glyph" cx="8" cy="8" r="7" stroke-width="1.3" />

    <!-- Clock hand (animated) -->
    <g class="clock-hand" style="transform-origin: 8px 8px;">
      <path class="icon-glyph" d="M8 4V8L11 11" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
    </g>
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

/* Rotating clock hand */
.clock-hand {
  animation: clock-rotate 4s linear infinite;
}

@keyframes clock-rotate {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
