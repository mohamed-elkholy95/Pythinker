<template>
  <div class="check-animation">
    <div class="check-circle">
      <svg class="check-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" class="circle-bg"/>
        <path
          d="M7 12.5l3 3 7-7"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="check-mark"
        />
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
// Check animation for completed operations
</script>

<style scoped>
.check-animation {
  position: relative;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.check-circle {
  position: relative;
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.check-circle::before {
  content: '';
  position: absolute;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(34, 197, 94, 0.15) 0%, transparent 70%);
  animation: pulse-success 2s ease-in-out infinite;
}

.check-icon {
  width: 48px;
  height: 48px;
  color: var(--success-green, #22c55e);
}

.circle-bg {
  stroke-opacity: 0.3;
}

.check-mark {
  stroke-dasharray: 20;
  stroke-dashoffset: 20;
  animation: draw-check 0.4s ease-out forwards 0.2s;
}

@keyframes draw-check {
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes pulse-success {
  0%, 100% {
    transform: scale(1);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.8;
  }
}

/* Dark mode: brighter success glow */
:global(.dark) .check-circle::before {
  background: radial-gradient(circle, rgba(34, 197, 94, 0.22) 0%, transparent 70%);
}

/* Accessibility: Reduce motion */
@media (prefers-reduced-motion: reduce) {
  .check-circle::before,
  .check-mark {
    animation: none;
  }
  .check-mark {
    stroke-dashoffset: 0;
  }
}
</style>
