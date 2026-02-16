<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Pencil path (animated) -->
    <path class="icon-glyph pencil-path"
      d="M9.5 3.5L12.5 6.5M2 14L3 10L11.5 1.5C12.0523 0.947715 12.9477 0.947715 13.5 1.5L14.5 2.5C15.0523 3.05228 15.0523 3.94772 14.5 4.5L6 13L2 14Z"
      stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />

    <!-- Writing dots (animated) -->
    <circle class="writing-dot dot-1" cx="3" cy="11" r="0.4" />
    <circle class="writing-dot dot-2" cx="4.5" cy="9.5" r="0.4" />
    <circle class="writing-dot dot-3" cx="6" cy="8" r="0.4" />
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

/* Pencil subtle movement */
.pencil-path {
  animation: pencil-move 1.5s ease-in-out infinite;
}

@keyframes pencil-move {
  0%, 100% {
    transform: translate(0, 0);
  }
  50% {
    transform: translate(-0.3px, 0.3px);
  }
}

/* Writing dots appearing sequentially */
.writing-dot {
  fill: var(--icon-secondary, #535350);
  opacity: 0;
}

.dot-1 {
  animation: dot-appear 1.5s ease-in-out infinite;
  animation-delay: 0s;
}

.dot-2 {
  animation: dot-appear 1.5s ease-in-out infinite;
  animation-delay: 0.3s;
}

.dot-3 {
  animation: dot-appear 1.5s ease-in-out infinite;
  animation-delay: 0.6s;
}

@keyframes dot-appear {
  0%, 20% {
    opacity: 0;
    transform: scale(0);
  }
  30%, 80% {
    opacity: 0.6;
    transform: scale(1);
  }
  90%, 100% {
    opacity: 0;
    transform: scale(0.5);
  }
}
</style>
