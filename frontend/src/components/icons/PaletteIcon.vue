<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Palette body -->
    <path class="icon-glyph"
      d="M8 1C4.13 1 1 4.13 1 8c0 3.87 3.13 7 7 7 0.55 0 1-0.45 1-1 0-0.25-0.1-0.48-0.25-0.66C8.58 13.13 8.5 12.88 8.5 12.5c0-0.55 0.45-1 1-1H11c2.21 0 4-1.79 4-4 0-3.31-3.13-6.5-7-6.5Z"
      stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />

    <!-- Color dots on palette -->
    <circle class="color-dot dot-red" cx="4.5" cy="6" r="1.1" />
    <circle class="color-dot dot-yellow" cx="6.5" cy="4" r="1.1" />
    <circle class="color-dot dot-green" cx="9.5" cy="4" r="1.1" />
    <circle class="color-dot dot-blue" cx="11.5" cy="6" r="1.1" />

    <!-- Brush stroke trail (animated) -->
    <path
      class="brush-stroke"
      d="M4 10 Q6 8 8 9 T12 7.5"
      stroke-width="0.9"
      stroke-linecap="round"
      fill="none"
    />

    <!-- Sparkle particles -->
    <circle class="sparkle spark-1" cx="5" cy="9" r="0.35" />
    <circle class="sparkle spark-2" cx="7.5" cy="8" r="0.3" />
    <circle class="sparkle spark-3" cx="10" cy="7" r="0.35" />
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

/* Color dots pulse in sequence */
.color-dot {
  fill: var(--icon-secondary, #535350);
  opacity: 0.45;
}

.dot-red {
  animation: dot-pulse 3s ease-in-out infinite;
  animation-delay: 0s;
}

.dot-yellow {
  animation: dot-pulse 3s ease-in-out infinite;
  animation-delay: 0.4s;
}

.dot-green {
  animation: dot-pulse 3s ease-in-out infinite;
  animation-delay: 0.8s;
}

.dot-blue {
  animation: dot-pulse 3s ease-in-out infinite;
  animation-delay: 1.2s;
}

@keyframes dot-pulse {
  0%, 100% {
    opacity: 0.4;
    r: 1.1;
  }
  50% {
    opacity: 0.8;
    r: 1.3;
  }
}

/* Brush stroke draw animation */
.brush-stroke {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
  stroke-dasharray: 18;
  stroke-dashoffset: 18;
  animation: brush-draw 3s ease-in-out infinite;
}

@keyframes brush-draw {
  0%, 10% {
    stroke-dashoffset: 18;
    opacity: 0;
  }
  25% {
    opacity: 0.5;
  }
  60% {
    stroke-dashoffset: 0;
    opacity: 0.5;
  }
  80%, 100% {
    stroke-dashoffset: 0;
    opacity: 0;
  }
}

/* Sparkle particles */
.sparkle {
  fill: var(--icon-secondary, #535350);
  opacity: 0;
}

.spark-1 {
  animation: spark-pop 3s ease-in-out infinite;
  animation-delay: 0.3s;
}

.spark-2 {
  animation: spark-pop 3s ease-in-out infinite;
  animation-delay: 0.6s;
}

.spark-3 {
  animation: spark-pop 3s ease-in-out infinite;
  animation-delay: 0.9s;
}

@keyframes spark-pop {
  0%, 15% {
    opacity: 0;
    transform: scale(0) translate(0, 0);
  }
  30% {
    opacity: 0.7;
    transform: scale(1.3) translate(0, -1px);
  }
  50% {
    opacity: 0.4;
    transform: scale(1) translate(0.5px, -0.5px);
  }
  70%, 100% {
    opacity: 0;
    transform: scale(0.3) translate(1px, -1px);
  }
}
</style>
