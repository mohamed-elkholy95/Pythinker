<template>
  <div class="waiting-for-reply">
    <div class="waiting-container">
      <!-- Animated dashed circle -->
      <div class="waiting-circle">
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <circle
            cx="10"
            cy="10"
            r="8"
            stroke="currentColor"
            stroke-width="2"
            stroke-dasharray="4 4"
            fill="none"
            class="rotating-circle"
          />
        </svg>
      </div>
      <!-- Message text -->
      <span class="waiting-text">
        {{ message }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  message?: string;
}>(), {
  message: 'Pythinker will continue working after your reply'
});
</script>

<style scoped>
.waiting-for-reply {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  margin: 8px 0;
}

.waiting-container {
  display: flex;
  align-items: center;
  gap: 10px;
}

.waiting-circle {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #d97706; /* amber-600 */
}

:global(.dark) .waiting-circle {
  color: #fbbf24; /* amber-400 */
}

.rotating-circle {
  animation: rotate 8s linear infinite;
  transform-origin: center;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.waiting-text {
  font-size: 14px;
  font-weight: 500;
  color: #d97706; /* amber-600 */
}

:global(.dark) .waiting-text {
  color: #fbbf24; /* amber-400 */
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
  .rotating-circle {
    animation: none;
  }
}
</style>
