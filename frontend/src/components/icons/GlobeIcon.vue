<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Outer circle (static) -->
    <circle class="icon-glyph" cx="8" cy="8" r="7" stroke-width="1.3" />

    <!-- Rotating globe elements -->
    <g class="rotating-globe" style="transform-origin: 8px 8px;">
      <ellipse class="icon-glyph" cx="8" cy="8" rx="3" ry="7" stroke-width="1.1" />
      <path class="icon-glyph horizontal-line-1" d="M1 6H15" stroke-width="1" />
      <path class="icon-glyph horizontal-line-2" d="M1 10H15" stroke-width="1" />
    </g>

    <!-- Data transfer dots (animated) -->
    <circle class="transfer-dot dot-1" cx="11" cy="8" r="0.5" />
    <circle class="transfer-dot dot-2" cx="5" cy="8" r="0.5" />
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

/* Subtle globe rotation */
.rotating-globe {
  animation: globe-rotate 8s linear infinite;
}

@keyframes globe-rotate {
  0% {
    transform: rotateY(0deg);
  }
  100% {
    transform: rotateY(360deg);
  }
}

/* Horizontal lines fade in/out during rotation */
.horizontal-line-1 {
  animation: line-fade 8s ease-in-out infinite;
}

.horizontal-line-2 {
  animation: line-fade 8s ease-in-out infinite;
  animation-delay: 4s;
}

@keyframes line-fade {
  0%, 100% {
    opacity: 1;
  }
  45%, 55% {
    opacity: 0.3;
  }
}

/* Data transfer dots */
.transfer-dot {
  fill: var(--icon-secondary, #535350);
  opacity: 0;
}

.dot-1 {
  animation: transfer-pulse 2s ease-in-out infinite;
  animation-delay: 0s;
}

.dot-2 {
  animation: transfer-pulse 2s ease-in-out infinite;
  animation-delay: 1s;
}

@keyframes transfer-pulse {
  0%, 90% {
    opacity: 0;
    transform: scale(0);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.5);
  }
}
</style>
