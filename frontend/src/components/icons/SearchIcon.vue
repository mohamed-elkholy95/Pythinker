<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Clip path to constrain scanning lines inside the circle -->
    <defs>
      <clipPath id="circle-clip">
        <circle cx="6.5" cy="6.5" r="5.3" />
      </clipPath>
    </defs>

    <!-- Search circle -->
    <circle class="icon-glyph" cx="6.5" cy="6.5" r="5.5" stroke-width="1.3" />

    <!-- Scanning lines inside circle (animated) -->
    <g clip-path="url(#circle-clip)" class="scan-lines">
      <line class="scan-line scan-line-1" x1="1" y1="2" x2="12" y2="2" stroke-width="0.8" />
      <line class="scan-line scan-line-2" x1="1" y1="4.5" x2="12" y2="4.5" stroke-width="0.8" />
      <line class="scan-line scan-line-3" x1="1" y1="7" x2="12" y2="7" stroke-width="0.8" />
      <line class="scan-line scan-line-4" x1="1" y1="9.5" x2="12" y2="9.5" stroke-width="0.8" />
      <line class="scan-line scan-line-5" x1="1" y1="12" x2="12" y2="12" stroke-width="0.8" />
    </g>

    <!-- Search handle -->
    <path class="icon-glyph" d="M10.5 10.5L15 15" stroke-width="1.3" stroke-linecap="round" />
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

.scan-line {
  stroke: var(--icon-secondary, #535350);
  stroke-linecap: round;
  opacity: 0;
}

/* Animate scanning lines moving from top to bottom */
.scan-line-1 {
  animation: scan-move 2s ease-in-out infinite;
  animation-delay: 0s;
}

.scan-line-2 {
  animation: scan-move 2s ease-in-out infinite;
  animation-delay: 0.1s;
}

.scan-line-3 {
  animation: scan-move 2s ease-in-out infinite;
  animation-delay: 0.2s;
}

.scan-line-4 {
  animation: scan-move 2s ease-in-out infinite;
  animation-delay: 0.3s;
}

.scan-line-5 {
  animation: scan-move 2s ease-in-out infinite;
  animation-delay: 0.4s;
}

@keyframes scan-move {
  0% {
    transform: translateY(0);
    opacity: 0;
  }
  10% {
    opacity: 0.4;
  }
  50% {
    opacity: 0.6;
  }
  90% {
    opacity: 0.4;
  }
  100% {
    transform: translateY(9px);
    opacity: 0;
  }
}
</style>
