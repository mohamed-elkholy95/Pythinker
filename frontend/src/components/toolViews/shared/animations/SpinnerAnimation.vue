<template>
  <div class="spinner-animation">
    <svg class="spinner" viewBox="0 0 50 50">
      <circle
        class="spinner-path"
        cx="25"
        cy="25"
        r="20"
        fill="none"
        stroke-width="4"
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
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  animation: rotate 2s linear infinite;
  width: 50px;
  height: 50px;
}

.spinner-path {
  stroke: var(--text-brand);
  stroke-linecap: round;
  animation: dash 1.5s ease-in-out infinite;
}

@keyframes rotate {
  100% {
    transform: rotate(360deg);
  }
}

@keyframes dash {
  0% {
    stroke-dasharray: 1, 150;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -35;
  }
  100% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -124;
  }
}

/* Accessibility: Reduce motion */
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
  .spinner-path {
    animation: none;
    stroke-dasharray: 90, 150;
  }
}
</style>
