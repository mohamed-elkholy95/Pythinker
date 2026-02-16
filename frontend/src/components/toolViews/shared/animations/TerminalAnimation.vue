<template>
  <div class="terminal-animation">
    <div class="terminal-window">
      <div class="terminal-header">
        <div class="terminal-dot"></div>
        <div class="terminal-dot"></div>
        <div class="terminal-dot"></div>
      </div>
      <div class="terminal-body">
        <div class="terminal-line">
          <span class="prompt">$</span>
          <span class="cursor"></span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Terminal animation for shell operations
</script>

<style scoped>
.terminal-animation {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.terminal-window {
  width: 60px;
  height: 50px;
  background: #1e1e1e;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid transparent;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.terminal-header {
  height: 12px;
  background: #2d2d2d;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 0 6px;
}

.terminal-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.3);
}

.terminal-body {
  padding: 6px;
}

.terminal-line {
  display: flex;
  align-items: center;
  gap: 4px;
}

.prompt {
  color: var(--text-brand);
  font-family: var(--font-mono);
  font-size: 10px;
}

.cursor {
  display: inline-block;
  width: 6px;
  height: 10px;
  background: var(--text-brand);
  animation: cursor-blink 1s step-end infinite;
}

@keyframes cursor-blink {
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
    opacity: 0;
  }
}

/* Dark mode: prevent terminal from blending into dark background */
:global(.dark) .terminal-window {
  background: #252526;
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

:global(.dark) .terminal-header {
  background: #333333;
}

:global(.dark) .terminal-dot {
  background: rgba(255, 255, 255, 0.4);
}

@media (prefers-reduced-motion: reduce) {
  .cursor {
    animation: none;
  }
}
</style>
