<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Click indicator lines (animated) -->
    <g class="click-indicators">
      <path class="click-line click-line-1" d="M14 4.1 12 6" stroke-width="2" stroke-linecap="round" />
      <path class="click-line click-line-2" d="m5.1 8-2.9-.8" stroke-width="2" stroke-linecap="round" />
      <path class="click-line click-line-3" d="m6 12-1.9 2" stroke-width="2" stroke-linecap="round" />
      <path class="click-line click-line-4" d="M7.2 2.2 8 5.1" stroke-width="2" stroke-linecap="round" />
    </g>

    <!-- Mouse pointer (animated) -->
    <path
      class="mouse-pointer"
      d="M9.037 9.69a.498.498 0 0 1 .653-.653l11 4.5a.5.5 0 0 1-.074.949l-4.349 1.041a1 1 0 0 0-.74.739l-1.04 4.35a.5.5 0 0 1-.95.074z"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    />

    <!-- Click ripple effect (animated) -->
    <circle class="click-ripple" cx="10" cy="10.5" r="2" stroke-width="1.5" fill="none" />
  </svg>
</template>

<script setup lang="ts">
defineProps({
  size: { type: Number, default: 21 },
});
</script>

<style scoped>
.mouse-pointer {
  stroke: var(--icon-secondary, #535350);
  fill: var(--icon-secondary, #535350);
  animation: pointer-click 1.5s ease-in-out infinite;
}

/* Click animation - slight movement */
@keyframes pointer-click {
  0%, 100% {
    transform: translate(0, 0);
  }
  50% {
    transform: translate(1px, 1px);
  }
}

/* Click indicator lines */
.click-line {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
}

.click-line-1 {
  animation: click-indicator 1.5s ease-in-out infinite;
  animation-delay: 0s;
}

.click-line-2 {
  animation: click-indicator 1.5s ease-in-out infinite;
  animation-delay: 0.1s;
}

.click-line-3 {
  animation: click-indicator 1.5s ease-in-out infinite;
  animation-delay: 0.2s;
}

.click-line-4 {
  animation: click-indicator 1.5s ease-in-out infinite;
  animation-delay: 0.3s;
}

@keyframes click-indicator {
  0%, 60% {
    opacity: 0;
    transform: scale(0.8);
  }
  40% {
    opacity: 0.7;
    transform: scale(1);
  }
  70%, 100% {
    opacity: 0;
    transform: scale(1.1);
  }
}

/* Ripple effect on click */
.click-ripple {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
  animation: ripple-expand 1.5s ease-out infinite;
}

@keyframes ripple-expand {
  0% {
    r: 1;
    opacity: 0;
  }
  30% {
    opacity: 0.5;
  }
  100% {
    r: 8;
    opacity: 0;
  }
}
</style>
