<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Browser window -->
    <rect class="icon-glyph" x="1" y="1" width="14" height="14" rx="2" stroke-width="1.3" />
    <path class="icon-glyph" d="M1 5H15" stroke-width="1.3" />
    <circle class="icon-dot" cx="3.5" cy="3" r="0.75" />
    <circle class="icon-dot" cx="5.75" cy="3" r="0.75" />
    <circle class="icon-dot" cx="8" cy="3" r="0.75" />
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
.icon-dot {
  fill: var(--icon-tertiary, #9b9b97);
}
</style>
