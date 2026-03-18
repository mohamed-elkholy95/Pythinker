<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Chat bubble body -->
    <path class="icon-glyph"
      d="M2 3C2 2.44772 2.44772 2 3 2H13C13.5523 2 14 2.44772 14 3V10C14 10.5523 13.5523 11 13 11H5L2.5 13.5V11H3C2.44772 11 2 10.5523 2 10V3Z"
      stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />

    <!-- Typing indicator dots (animated) -->
    <circle class="typing-dot typing-dot-1" cx="5.5" cy="6.5" r="0.9" />
    <circle class="typing-dot typing-dot-2" cx="8" cy="6.5" r="0.9" />
    <circle class="typing-dot typing-dot-3" cx="10.5" cy="6.5" r="0.9" />

    <!-- Message send pulse (subtle outward ring) -->
    <path class="send-pulse"
      d="M2 3C2 2.44772 2.44772 2 3 2H13C13.5523 2 14 2.44772 14 3V10C14 10.5523 13.5523 11 13 11H5L2.5 13.5V11H3C2.44772 11 2 10.5523 2 10V3Z"
      stroke-width="0.8" stroke-linecap="round" stroke-linejoin="round" fill="none" />
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

/* Typing dots bounce animation */
.typing-dot {
  fill: var(--icon-secondary, #535350);
  opacity: 0.4;
}

.typing-dot-1 {
  animation: typing-bounce 1.4s ease-in-out infinite;
  animation-delay: 0s;
}

.typing-dot-2 {
  animation: typing-bounce 1.4s ease-in-out infinite;
  animation-delay: 0.2s;
}

.typing-dot-3 {
  animation: typing-bounce 1.4s ease-in-out infinite;
  animation-delay: 0.4s;
}

@keyframes typing-bounce {
  0%, 60%, 100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  30% {
    opacity: 0.85;
    transform: translateY(-1.5px);
  }
}

/* Subtle outward pulse on the bubble silhouette */
.send-pulse {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
  animation: pulse-ring 3s ease-out infinite;
}

@keyframes pulse-ring {
  0% {
    opacity: 0;
    transform: scale(1);
  }
  15% {
    opacity: 0.25;
    transform: scale(1);
  }
  50% {
    opacity: 0;
    transform: scale(1.06);
  }
  100% {
    opacity: 0;
    transform: scale(1);
  }
}
</style>
