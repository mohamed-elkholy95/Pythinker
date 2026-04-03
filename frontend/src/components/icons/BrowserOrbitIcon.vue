<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }"
    aria-hidden="true"
  >
    <circle class="browser-orbit-ring" cx="12" cy="12" r="9" />
    <ellipse class="browser-orbit-globe" cx="12" cy="12" rx="4" ry="9" />
    <path class="browser-orbit-line browser-orbit-line--horizontal" d="M3 12h18" />
    <path class="browser-orbit-line browser-orbit-line--vertical" d="M12 3v18" />
    <g class="browser-orbit-trail">
      <circle class="browser-orbit-dot browser-orbit-dot--one" cx="18" cy="12" r="1" />
      <circle class="browser-orbit-dot browser-orbit-dot--two" cx="12" cy="3" r="1" />
    </g>
  </svg>
</template>

<script setup lang="ts">
defineProps({
  size: { type: Number, default: 16 },
});
</script>

<style scoped>
.browser-orbit-ring,
.browser-orbit-globe,
.browser-orbit-line {
  stroke: var(--icon-secondary, #535350);
  fill: none;
}

.browser-orbit-ring {
  opacity: 0.32;
  stroke-width: 1.6;
}

.browser-orbit-globe {
  opacity: 0.56;
  stroke-width: 1.2;
  transform-origin: center;
  animation: browser-orbit-rotate 5.5s linear infinite;
}

.browser-orbit-line {
  opacity: 0.42;
  stroke-width: 1.1;
  stroke-linecap: round;
  animation: browser-orbit-breathe 2.8s ease-in-out infinite;
}

.browser-orbit-line--vertical {
  animation-delay: 1.4s;
}

.browser-orbit-dot {
  fill: var(--icon-secondary, #535350);
  opacity: 0;
  transform-origin: center;
}

.browser-orbit-dot--one {
  animation: browser-orbit-pulse 2.1s ease-in-out infinite;
}

.browser-orbit-dot--two {
  animation: browser-orbit-pulse 2.1s ease-in-out infinite 1.05s;
}

@keyframes browser-orbit-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes browser-orbit-breathe {
  0%, 100% {
    opacity: 0.28;
  }
  50% {
    opacity: 0.56;
  }
}

@keyframes browser-orbit-pulse {
  0%, 85%, 100% {
    opacity: 0;
    transform: scale(0.5);
  }
  45% {
    opacity: 0.9;
    transform: scale(1.2);
  }
}

@media (prefers-reduced-motion: reduce) {
  .browser-orbit-globe,
  .browser-orbit-line,
  .browser-orbit-dot {
    animation: none;
  }
  .browser-orbit-dot {
    opacity: 0.8;
  }
}
</style>
