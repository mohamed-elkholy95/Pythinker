<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <path class="icon-glyph"
      d="M9.5 3.5L12.5 6.5M2 14L3 10L11.5 1.5C12.0523 0.947715 12.9477 0.947715 13.5 1.5L14.5 2.5C15.0523 3.05228 15.0523 3.94772 14.5 4.5L6 13L2 14Z"
      stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
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
</style>
