<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <!-- Top layer (animated) -->
    <path
      class="layer layer-1"
      d="M12 2L2 7L12 12L22 7L12 2Z"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />

    <!-- Middle layer (animated) -->
    <path
      class="layer layer-2"
      d="M2 12L12 17L22 12"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />

    <!-- Bottom layer (animated) -->
    <path
      class="layer layer-3"
      d="M2 17L12 22L22 17"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>

<script setup lang="ts">
defineProps({
  size: {
    type: [Number, String],
    default: 24
  }
})
</script>

<style scoped>
.layer {
  animation: layer-shift 2s ease-in-out infinite;
}

.layer-1 {
  animation-delay: 0s;
}

.layer-2 {
  animation-delay: 0.15s;
}

.layer-3 {
  animation-delay: 0.3s;
}

@keyframes layer-shift {
  0%, 100% {
    opacity: 1;
    transform: translateY(0);
  }
  50% {
    opacity: 0.6;
    transform: translateY(-1px);
  }
}
</style>
