<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
    <!-- Terminal window frame -->
    <rect
      class="terminal-frame"
      x="2"
      y="4"
      width="20"
      height="16"
      rx="2"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    />

    <!-- Terminal header dots -->
    <circle class="header-dot" cx="5" cy="7.5" r="0.8" />
    <circle class="header-dot" cx="7.5" cy="7.5" r="0.8" />
    <circle class="header-dot" cx="10" cy="7.5" r="0.8" />

    <!-- Command prompt (animated) -->
    <g class="command-prompt">
      <path
        class="prompt-symbol"
        d="M6 13l3 2-3 2"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <!-- Command line (animated) -->
      <line class="command-line" x1="11" y1="15" x2="18" y2="15" stroke-width="2" stroke-linecap="round" />
    </g>

    <!-- Code execution indicators (animated lines) -->
    <line class="code-line line-1" x1="6" y1="11" x2="14" y2="11" stroke-width="1" stroke-linecap="round" />
    <line class="code-line line-2" x1="6" y1="18" x2="12" y2="18" stroke-width="1" stroke-linecap="round" />

    <!-- Cursor blink (animated) -->
    <rect class="terminal-cursor" x="18.5" y="13.5" width="1.5" height="3" rx="0.3" />

    <!-- Activity indicator (animated pulse) -->
    <circle class="activity-pulse" cx="19" cy="7" r="1" />
  </svg>
</template>

<script setup lang="ts">
defineProps({
  size: { type: Number, default: 21 },
});
</script>

<style scoped>
.terminal-frame {
  stroke: var(--icon-secondary, #535350);
  fill: none;
}

.header-dot {
  fill: var(--icon-secondary, #535350);
  opacity: 0.5;
}

/* Command prompt animation */
.prompt-symbol {
  stroke: var(--icon-secondary, #535350);
  animation: prompt-flash 2s ease-in-out infinite;
}

@keyframes prompt-flash {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

/* Command line drawing animation */
.command-line {
  stroke: var(--icon-secondary, #535350);
  stroke-dasharray: 7;
  stroke-dashoffset: 7;
  animation: line-draw 2.5s ease-in-out infinite;
}

@keyframes line-draw {
  0%, 20% {
    stroke-dashoffset: 7;
    opacity: 0;
  }
  40% {
    opacity: 0.7;
  }
  60% {
    stroke-dashoffset: 0;
    opacity: 0.7;
  }
  80%, 100% {
    stroke-dashoffset: 0;
    opacity: 0.3;
  }
}

/* Code execution lines */
.code-line {
  stroke: var(--icon-secondary, #535350);
  opacity: 0;
}

.line-1 {
  animation: code-execute 2.5s ease-in-out infinite;
  animation-delay: 0.3s;
}

.line-2 {
  animation: code-execute 2.5s ease-in-out infinite;
  animation-delay: 0.6s;
}

@keyframes code-execute {
  0%, 30% {
    opacity: 0;
    transform: translateX(-2px);
  }
  50% {
    opacity: 0.5;
    transform: translateX(0);
  }
  70%, 100% {
    opacity: 0;
    transform: translateX(2px);
  }
}

/* Blinking cursor */
.terminal-cursor {
  fill: var(--icon-secondary, #535350);
  animation: cursor-blink 1.2s step-end infinite;
}

@keyframes cursor-blink {
  0%, 49% {
    opacity: 1;
  }
  50%, 100% {
    opacity: 0;
  }
}

/* Activity pulse indicator */
.activity-pulse {
  fill: var(--icon-secondary, #535350);
  animation: activity-beat 2s ease-in-out infinite;
}

@keyframes activity-beat {
  0%, 100% {
    opacity: 0.3;
    r: 0.8;
  }
  50% {
    opacity: 1;
    r: 1.3;
  }
}
</style>
