<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <path class="icon-glyph" d="M2 2L7.5 8L2 14" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
    <path class="icon-glyph" d="M9 14H14" stroke-width="1.3" stroke-linecap="round" />
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
