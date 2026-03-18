<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Monitor frame -->
    <rect
      class="monitor-frame"
      x="2"
      y="3"
      width="20"
      height="14"
      rx="2"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    />

    <!-- Monitor stand -->
    <path class="monitor-stand" d="M8 21h8" stroke-width="2" stroke-linecap="round" />
    <path class="monitor-stand" d="M12 17v4" stroke-width="2" stroke-linecap="round" />

    <!-- Scanning lines inside monitor (animated) -->
    <g class="scan-area" clip-path="url(#monitor-clip)">
      <line class="scan-line scan-line-1" x1="4" y1="6" x2="20" y2="6" stroke-width="1" />
      <line class="scan-line scan-line-2" x1="4" y1="9" x2="20" y2="9" stroke-width="1" />
      <line class="scan-line scan-line-3" x1="4" y1="12" x2="20" y2="12" stroke-width="1" />
      <line class="scan-line scan-line-4" x1="4" y1="15" x2="20" y2="15" stroke-width="1" />
    </g>

    <!-- Activity indicator dot (animated) -->
    <circle class="activity-dot" cx="19" cy="5" r="1.5" />

    <!-- Clip path for scan lines -->
    <defs>
      <clipPath id="monitor-clip">
        <rect x="3" y="4" width="18" height="12" rx="1" />
      </clipPath>
    </defs>
  </svg>
</template>

<script setup lang="ts">
defineProps({
  size: { type: Number, default: 21 },
});
</script>

<style scoped>
.monitor-frame,
.monitor-stand {
  stroke: var(--icon-secondary, #535350);
  fill: none;
}

/* Scanning lines animation */
.scan-line {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
}

.scan-line-1 {
  animation: scan-sweep 2s ease-in-out infinite;
  animation-delay: 0s;
}

.scan-line-2 {
  animation: scan-sweep 2s ease-in-out infinite;
  animation-delay: 0.15s;
}

.scan-line-3 {
  animation: scan-sweep 2s ease-in-out infinite;
  animation-delay: 0.3s;
}

.scan-line-4 {
  animation: scan-sweep 2s ease-in-out infinite;
  animation-delay: 0.45s;
}

@keyframes scan-sweep {
  0%, 20% {
    opacity: 0;
    transform: translateY(-2px);
  }
  40% {
    opacity: 0.6;
    transform: translateY(0);
  }
  60% {
    opacity: 0.6;
    transform: translateY(0);
  }
  80%, 100% {
    opacity: 0;
    transform: translateY(2px);
  }
}

/* Activity indicator */
.activity-dot {
  fill: var(--icon-secondary, #535350);
  animation: activity-pulse 1.5s ease-in-out infinite;
}

@keyframes activity-pulse {
  0%, 100% {
    opacity: 0.3;
    r: 1;
  }
  50% {
    opacity: 1;
    r: 1.5;
  }
}
</style>
