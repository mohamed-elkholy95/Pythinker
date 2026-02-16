<template>
  <svg :width="size" :height="size" viewBox="0 0 16 16" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Pencil path (animated with realistic writing motion) -->
    <g class="pencil-container" style="transform-origin: 6px 13px;">
      <path class="icon-glyph pencil-path"
        d="M9.5 3.5L12.5 6.5M2 14L3 10L11.5 1.5C12.0523 0.947715 12.9477 0.947715 13.5 1.5L14.5 2.5C15.0523 3.05228 15.0523 3.94772 14.5 4.5L6 13L2 14Z"
        stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
    </g>

    <!-- Writing stroke path (animated line being drawn) -->
    <path
      class="writing-stroke"
      d="M2.5 13.5 Q4 11.5 5.5 9.5 T8 7"
      stroke-width="1"
      stroke-linecap="round"
      fill="none"
    />

    <!-- Ink trail effect (fading line segments) -->
    <line class="ink-trail trail-1" x1="3" y1="12.5" x2="4" y2="11" stroke-width="0.8" stroke-linecap="round" />
    <line class="ink-trail trail-2" x1="4" y1="11" x2="5" y2="9.5" stroke-width="0.8" stroke-linecap="round" />
    <line class="ink-trail trail-3" x1="5" y1="9.5" x2="6.5" y2="8" stroke-width="0.8" stroke-linecap="round" />

    <!-- Writing sparkles/particles (animated dots with varied positions) -->
    <circle class="writing-dot dot-1" cx="3" cy="12" r="0.35" />
    <circle class="writing-dot dot-2" cx="4.5" cy="10.5" r="0.4" />
    <circle class="writing-dot dot-3" cx="5.5" cy="9" r="0.3" />
    <circle class="writing-dot dot-4" cx="7" cy="7.5" r="0.35" />

    <!-- Pencil tip glow (subtle emphasis at writing point) -->
    <circle class="pencil-glow" cx="6" cy="13" r="0.8" />
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

/* Pencil realistic writing motion - diagonal strokes with rotation */
.pencil-container {
  animation: pencil-write 2.2s ease-in-out infinite;
}

@keyframes pencil-write {
  0% {
    transform: translate(0, 0) rotate(0deg);
  }
  25% {
    transform: translate(-0.5px, 0.5px) rotate(-1deg);
  }
  50% {
    transform: translate(-0.8px, 0.8px) rotate(-1.5deg);
  }
  75% {
    transform: translate(-0.5px, 0.5px) rotate(-1deg);
  }
  100% {
    transform: translate(0, 0) rotate(0deg);
  }
}

/* Writing stroke - line being drawn */
.writing-stroke {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
  stroke-dasharray: 20;
  stroke-dashoffset: 20;
  animation: draw-stroke 2.2s ease-in-out infinite;
}

@keyframes draw-stroke {
  0%, 15% {
    stroke-dashoffset: 20;
    opacity: 0;
  }
  30% {
    opacity: 0.5;
  }
  65% {
    stroke-dashoffset: 0;
    opacity: 0.5;
  }
  85%, 100% {
    stroke-dashoffset: 0;
    opacity: 0;
  }
}

/* Ink trail segments - fade in as pencil moves */
.ink-trail {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
}

.trail-1 {
  animation: ink-fade 2.2s ease-in-out infinite;
  animation-delay: 0.2s;
}

.trail-2 {
  animation: ink-fade 2.2s ease-in-out infinite;
  animation-delay: 0.4s;
}

.trail-3 {
  animation: ink-fade 2.2s ease-in-out infinite;
  animation-delay: 0.6s;
}

@keyframes ink-fade {
  0%, 10% {
    opacity: 0;
  }
  25% {
    opacity: 0.6;
  }
  50%, 70% {
    opacity: 0.4;
  }
  85%, 100% {
    opacity: 0;
  }
}

/* Writing particles/sparkles */
.writing-dot {
  fill: var(--icon-secondary, #535350);
  opacity: 0;
}

.dot-1 {
  animation: dot-sparkle 2.2s ease-in-out infinite;
  animation-delay: 0.2s;
}

.dot-2 {
  animation: dot-sparkle 2.2s ease-in-out infinite;
  animation-delay: 0.4s;
}

.dot-3 {
  animation: dot-sparkle 2.2s ease-in-out infinite;
  animation-delay: 0.6s;
}

.dot-4 {
  animation: dot-sparkle 2.2s ease-in-out infinite;
  animation-delay: 0.8s;
}

@keyframes dot-sparkle {
  0%, 15% {
    opacity: 0;
    transform: scale(0) translate(0, 0);
  }
  30% {
    opacity: 0.7;
    transform: scale(1.2) translate(0, -1px);
  }
  50% {
    opacity: 0.5;
    transform: scale(1) translate(0.5px, -0.5px);
  }
  70%, 100% {
    opacity: 0;
    transform: scale(0.3) translate(1px, -1px);
  }
}

/* Pencil tip glow - subtle emphasis */
.pencil-glow {
  fill: var(--icon-secondary, #535350);
  opacity: 0;
  animation: glow-pulse 2.2s ease-in-out infinite;
}

@keyframes glow-pulse {
  0%, 20% {
    opacity: 0;
    r: 0.5;
  }
  40% {
    opacity: 0.15;
    r: 1.2;
  }
  60% {
    opacity: 0.1;
    r: 1;
  }
  80%, 100% {
    opacity: 0;
    r: 0.5;
  }
}
</style>
