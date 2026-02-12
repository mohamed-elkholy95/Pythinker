<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <circle class="icon-glyph" cx="6.5" cy="6.5" r="5.5" stroke-width="1.3" />
    <path class="icon-glyph" d="M10.5 10.5L15 15" stroke-width="1.3" stroke-linecap="round" />
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
