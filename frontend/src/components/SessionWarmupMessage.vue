<template>
  <div class="warmup-message" data-testid="session-warmup">
    <div class="warmup-header">
      <img src="/icon.svg" alt="Pythinker" class="warmup-icon" />
      <PythinkerTextIcon :width="110" :height="20" />
    </div>

    <div class="warmup-body">
      <!-- Use ThinkingIndicator for 'thinking' state -->
      <div v-if="props.state === 'thinking'" class="warmup-thinking-indicator">
        <ThinkingIndicator :showText="true" />
      </div>
      <!-- Fallback to text for other states -->
      <div v-else class="warmup-text-column">
        <div class="warmup-text-wrap">
          <span class="warmup-text">{{ statusText }}</span>
          <span v-if="showBouncingDots" class="warmup-dots" aria-hidden="true">
            <span class="warmup-dot" />
            <span class="warmup-dot" />
            <span class="warmup-dot" />
          </span>
        </div>
      </div>
      <button
        v-if="props.state === 'timed_out'"
        data-testid="warmup-retry"
        type="button"
        class="warmup-retry"
        @click="emit('retry')"
      >
        Retry
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">

import { computed } from 'vue';
import PythinkerTextIcon from './icons/PythinkerTextIcon.vue';
import ThinkingIndicator from './ui/ThinkingIndicator.vue';

const emit = defineEmits<{
  (e: 'retry'): void;
}>();

const props = withDefaults(
  defineProps<{
    state?: 'initializing' | 'thinking' | 'timed_out';
  }>(),
  {
    state: 'initializing',
  }
);

const statusText = computed(() => {
  if (props.state === 'timed_out') {
    return 'Still getting your session ready';
  }
  if (props.state === 'thinking') {
    return 'Thinking';
  }
  return 'Initializing your session';
});

const showBouncingDots = computed(() => props.state !== 'timed_out');
</script>

<style scoped>
.warmup-message {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  margin-top: 12px;
}

.warmup-header {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 28px;
}

.warmup-icon {
  width: 20px;
  height: 20px;
  color: var(--text-primary);
}

.warmup-body {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
  padding-left: 0;
  min-height: 24px;
}

.warmup-text-column {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
}

.warmup-sub {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-tertiary, var(--text-secondary));
  opacity: 0.92;
  max-width: 28rem;
}

.warmup-text-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.warmup-thinking-indicator {
  display: flex;
  align-items: center;
  padding-left: 1px;
}

.warmup-text {
  font-size: 15px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.warmup-dots {
  display: inline-flex;
  align-items: flex-end;
  gap: 4px;
}

.warmup-dot {
  width: 5px;
  height: 5px;
  border-radius: 9999px;
  background: var(--text-secondary);
  opacity: 0.45;
  animation: warmup-dot-bounce 1.1s ease-in-out infinite;
}

.warmup-dot:nth-child(2) {
  animation-delay: 0.14s;
}

.warmup-dot:nth-child(3) {
  animation-delay: 0.28s;
}

@keyframes warmup-dot-bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.35;
  }
  40% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

.warmup-retry {
  border: 1px solid var(--border-main);
  border-radius: 8px;
  padding: 5px 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  background: var(--background-white-main);
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.warmup-retry:hover {
  background: var(--fill-tsp-gray-main);
}

@media (max-width: 768px) {
  .warmup-text {
    font-size: 15px;
  }
}
</style>
