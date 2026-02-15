<template>
  <div class="thinking-block">
    <!-- Connector Line -->
    <div class="connector">
      <div class="connector-line">
        <div class="connector-line-inner"></div>
      </div>
      <div class="connector-spacer"></div>
    </div>

    <!-- Main Content -->
    <div class="thinking-content">
      <!-- Indicator -->
      <div class="indicator-wrapper">
        <div class="indicator-glow"></div>
        <div class="indicator-container">
          <ThinkingIndicator :showText="false" />
        </div>
      </div>

      <!-- Text Content -->
      <div class="text-wrapper">
        <!-- Header -->
        <div class="thinking-header">
          <span class="thinking-label">Thinking</span>
          <div class="thinking-dots">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </div>
        </div>

        <!-- Thinking Text Container -->
        <div
          v-if="displayText"
          class="thinking-text-container"
        >
          <div
            ref="thinkingTextRef"
            class="thinking-text"
          >
            <span class="text-content">{{ displayText }}</span>
            <span class="cursor"></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import ThinkingIndicator from './ThinkingIndicator.vue'

const props = defineProps<{
  text: string
  maxLines?: number
}>()

const thinkingTextRef = ref<HTMLDivElement | null>(null)

const displayText = computed(() => {
  const maxLines = props.maxLines ?? 8
  const lines = props.text.split('\n')
  if (lines.length <= maxLines) {
    return props.text
  }
  return '...\n' + lines.slice(-maxLines).join('\n')
})

const scrollThinkingToBottom = async () => {
  await nextTick()
  if (!thinkingTextRef.value) return
  thinkingTextRef.value.scrollTop = thinkingTextRef.value.scrollHeight
}

watch(
  () => displayText.value,
  () => {
    scrollThinkingToBottom()
  },
  { immediate: true }
)
</script>

<style scoped>
/* Base Container */
.thinking-block {
  display: flex;
  flex-direction: column;
  font-family: var(--font-sans, system-ui, -apple-system, sans-serif);
}

/* Connector Styles */
.connector {
  display: flex;
  height: 20px;
}

.connector-line {
  width: 28px;
  position: relative;
  display: flex;
  justify-content: center;
}

.connector-line-inner {
  width: 2px;
  height: 100%;
  background: linear-gradient(
    to bottom,
    transparent,
    var(--border-color, rgba(148, 163, 184, 0.3)) 20%,
    var(--border-color, rgba(148, 163, 184, 0.3)) 80%,
    transparent
  );
  border-radius: 1px;
}

.connector-spacer {
  flex: 1;
}

/* Main Content */
.thinking-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

/* Indicator Styles */
.indicator-wrapper {
  position: relative;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.indicator-glow {
  position: absolute;
  inset: -4px;
  background: radial-gradient(
    circle,
    var(--accent-glow, rgba(59, 130, 246, 0.15)) 0%,
    transparent 70%
  );
  border-radius: 50%;
  animation: pulse-glow 2s ease-in-out infinite;
}

.indicator-container {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--indicator-bg, rgba(59, 130, 246, 0.1));
  border-radius: 8px;
  border: 1px solid var(--indicator-border, rgba(59, 130, 246, 0.2));
  box-shadow:
    0 2px 8px rgba(59, 130, 246, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

/* Text Wrapper */
.text-wrapper {
  flex: 1;
  min-width: 0;
  padding-top: 2px;
}

/* Header */
.thinking-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.thinking-label {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
  background: linear-gradient(
    135deg,
    var(--label-color-1, #000000) 0%,
    var(--label-color-2, #ffffff) 50%,
    var(--label-color-1, #000000) 100%
  );
  background-size: 200% 200%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: gradient-shift 3s ease infinite;
}

/* Animated Dots */
.thinking-dots {
  display: flex;
  gap: 3px;
  align-items: center;
}

.dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--dot-color, #000000);
  opacity: 0.6;
  animation: dot-bounce 1.4s ease-in-out infinite;
}

.dot:nth-child(1) { animation-delay: 0s; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

/* Thinking Text Container */
.thinking-text-container {
  position: relative;
  background: var(--text-container-bg, rgba(248, 250, 252, 0.6));
  border: 1px solid var(--text-container-border, rgba(226, 232, 240, 0.8));
  border-radius: 12px;
  backdrop-filter: blur(8px);
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.04),
    0 4px 12px rgba(0, 0, 0, 0.02);
}

.thinking-text {
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-color, #475569);
  max-height: 180px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar-thumb, rgba(148, 163, 184, 0.3)) transparent;
}

.thinking-text::-webkit-scrollbar {
  width: 6px;
}

.thinking-text::-webkit-scrollbar-track {
  background: transparent;
}

.thinking-text::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb, rgba(148, 163, 184, 0.3));
  border-radius: 3px;
}

.thinking-text::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover, rgba(148, 163, 184, 0.5));
}

.text-content {
  opacity: 0.85;
}

/* Cursor */
.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--cursor-color, #000000);
  margin-left: 2px;
  vertical-align: text-bottom;
  border-radius: 1px;
  animation: cursor-blink 1s ease-in-out infinite;
  box-shadow: 0 0 8px var(--cursor-glow, rgba(0, 0, 0, 0.4));
}

/* Fade Overlay */
/* Animations */
@keyframes pulse-glow {
  0%, 100% {
    opacity: 0.5;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}

@keyframes gradient-shift {
  0%, 100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
}

@keyframes dot-bounce {
  0%, 80%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  40% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

@keyframes cursor-blink {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

/* Dark Mode */
:global(.dark) .thinking-block {
  --border-color: rgba(71, 85, 105, 0.4);
  --accent-glow: rgba(255, 255, 255, 0.2);
  --indicator-bg: rgba(255, 255, 255, 0.15);
  --indicator-border: rgba(255, 255, 255, 0.25);
  --label-color-1: #ffffff;
  --label-color-2: #e5e5e5;
  --dot-color: #ffffff;
  --text-container-bg: rgba(30, 41, 59, 0.6);
  --text-container-border: rgba(71, 85, 105, 0.5);
  --text-color: #e2e8f0;
  --cursor-color: #ffffff;
  --cursor-glow: rgba(255, 255, 255, 0.4);
  --scrollbar-thumb: rgba(100, 116, 139, 0.4);
  --scrollbar-thumb-hover: rgba(100, 116, 139, 0.6);
}

/* Reduced Motion */
@media (prefers-reduced-motion: reduce) {
  .indicator-glow,
  .thinking-label,
  .dot,
  .cursor {
    animation: none;
  }

  .indicator-glow {
    opacity: 0.7;
  }

  .dot {
    opacity: 0.6;
  }

  .cursor {
    opacity: 1;
  }
}

/* Mobile Responsive */
@media (max-width: 480px) {
  .thinking-text {
    font-size: 12px;
    padding: 10px 12px;
    max-height: 150px;
  }

  .thinking-label {
    font-size: 12px;
  }
}
</style>
