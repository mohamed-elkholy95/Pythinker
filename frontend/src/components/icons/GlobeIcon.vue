<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <circle class="icon-glyph" cx="8" cy="8" r="7" stroke-width="1.3" />
    <ellipse class="icon-glyph" cx="8" cy="8" rx="3" ry="7" stroke-width="1.1" />
    <path class="icon-glyph" d="M1 6H15" stroke-width="1" />
    <path class="icon-glyph" d="M1 10H15" stroke-width="1" />
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
