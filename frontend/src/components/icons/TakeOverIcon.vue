<template>
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <!-- Monitor frame -->
    <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" stroke-width="2" />
    <!-- Animated screen lines (typing effect via stroke-dasharray) -->
    <line class="screen-line line-1" x1="5" y1="7" x2="15" y2="7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
    <line class="screen-line line-2" x1="5" y1="10" x2="19" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
    <line class="screen-line line-3" x1="5" y1="13" x2="12" y2="13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
    <!-- Stand -->
    <line x1="12" y1="17" x2="12" y2="21" stroke="currentColor" stroke-width="2" />
    <!-- Base -->
    <line x1="8" y1="21" x2="16" y2="21" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
  </svg>
</template>

<script setup lang="ts">
</script>

<style scoped>
.screen-line {
  stroke-dasharray: 14;
  stroke-dashoffset: 14;
  animation: type-line 2.4s ease-in-out infinite;
}

.line-1 { animation-delay: 0s; }
.line-2 { animation-delay: 0.4s; }
.line-3 { animation-delay: 0.8s; }

@keyframes type-line {
  0% { stroke-dashoffset: 14; opacity: 0.3; }
  40% { stroke-dashoffset: 0; opacity: 1; }
  70% { stroke-dashoffset: 0; opacity: 1; }
  100% { stroke-dashoffset: 14; opacity: 0.3; }
}
</style>
