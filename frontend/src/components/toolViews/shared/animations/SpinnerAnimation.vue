<template>
  <div class="spinner-animation" role="status" aria-label="Loading">
    <svg class="spinner spinner-outer" viewBox="0 0 50 50">
      <circle
        class="spinner-path spinner-path-outer"
        cx="25"
        cy="25"
        r="20"
        fill="none"
        stroke-width="3.5"
      ></circle>
    </svg>
    <svg class="spinner spinner-inner" viewBox="0 0 50 50">
      <circle
        class="spinner-path spinner-path-inner"
        cx="25"
        cy="25"
        r="12"
        fill="none"
        stroke-width="3"
      ></circle>
    </svg>
  </div>
</template>

<script setup lang="ts">
// Generic spinner animation for loading states
</script>

<style scoped>
.spinner-animation {
  width: 80px;
  height: 80px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  position: absolute;
  width: 52px;
  height: 52px;
  transform-origin: 50% 50%;
}

.spinner-outer {
  animation: rotate-cw 1.8s linear infinite;
}

.spinner-inner {
  width: 32px;
  height: 32px;
  animation: rotate-ccw 1.2s linear infinite;
}

.spinner-path {
  stroke-linecap: round;
  fill: none;
}

.spinner-path-outer {
  stroke: var(--text-brand);
  opacity: 0.9;
  animation: dash-outer 1.4s ease-in-out infinite;
}

.spinner-path-inner {
  stroke: color-mix(in srgb, var(--text-brand) 70%, white 30%);
  opacity: 0.8;
  animation: dash-inner 1s ease-in-out infinite;
}

@keyframes rotate-cw {
  100% {
    transform: rotate(360deg);
  }
}

@keyframes rotate-ccw {
  100% {
    transform: rotate(-360deg);
  }
}

@keyframes dash-outer {
  0% {
    stroke-dasharray: 6, 160;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 70, 160;
    stroke-dashoffset: -24;
  }
  100% {
    stroke-dasharray: 70, 160;
    stroke-dashoffset: -120;
  }
}

@keyframes dash-inner {
  0% {
    stroke-dasharray: 5, 90;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 42, 90;
    stroke-dashoffset: 18;
  }
  100% {
    stroke-dasharray: 42, 90;
    stroke-dashoffset: 70;
  }
}

/* Dark mode: ensure full visibility */
:global(.dark) .spinner-path-outer {
  opacity: 1;
}

:global(.dark) .spinner-path-inner {
  stroke: color-mix(in srgb, var(--text-brand) 60%, white 40%);
  opacity: 0.9;
}

/* Accessibility: Reduce motion */
@media (prefers-reduced-motion: reduce) {
  .spinner-outer,
  .spinner-inner,
  .spinner-path-outer,
  .spinner-path-inner {
    animation: none;
  }

  .spinner-path-outer {
    stroke-dasharray: 70, 160;
  }

  .spinner-path-inner {
    stroke-dasharray: 42, 90;
  }
}
</style>
