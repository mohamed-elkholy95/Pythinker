<template>
  <span class="loading-dots" role="status" aria-label="Loading">
    <span
      v-for="i in 3"
      :key="i"
      class="dot"
      :style="{ animationDelay: `${(i - 1) * 200}ms` }"
    ></span>
  </span>
</template>

<script setup lang="ts">
// Simple animated dots component for loading states
</script>

<style scoped>
.loading-dots {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--text-tertiary);
  animation: bounce-dot 1.4s ease-in-out infinite;
}

@keyframes bounce-dot {
  0%,
  80%,
  100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-6px);
  }
}

/* Accessibility: Reduce motion */
@media (prefers-reduced-motion: reduce) {
  .dot {
    animation: none;
  }
}
</style>
