<template>
  <div class="loading-state">
    <div class="loading-animation">
      <component :is="animationComponent" />
    </div>
    <div class="loading-text">
      <span class="loading-label">{{ label }}</span>
      <LoadingDots v-if="isActive" />
    </div>
    <div v-if="detail" class="loading-detail">
      {{ detail }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import LoadingDots from './LoadingDots.vue';
import GlobeAnimation from './animations/GlobeAnimation.vue';
import SearchAnimation from './animations/SearchAnimation.vue';
import FileAnimation from './animations/FileAnimation.vue';
import TerminalAnimation from './animations/TerminalAnimation.vue';
import CodeAnimation from './animations/CodeAnimation.vue';
import SpinnerAnimation from './animations/SpinnerAnimation.vue';
import CheckAnimation from './animations/CheckAnimation.vue';

export interface LoadingStateProps {
  /**
   * Main loading message
   */
  label: string;

  /**
   * Optional detail text (e.g., URL, filename, query)
   */
  detail?: string;

  /**
   * Animation type to display
   * - globe: Browser/network operations
   * - search: Search operations
   * - file: File operations
   * - terminal: Shell/command operations
   * - code: Code execution
   * - spinner: Generic loading
   * - check: Completed/success state
   */
  animation?: 'globe' | 'search' | 'file' | 'terminal' | 'code' | 'spinner' | 'check';

  /**
   * Whether to show animated dots after label
   */
  isActive?: boolean;
}

const props = withDefaults(defineProps<LoadingStateProps>(), {
  animation: 'spinner',
  isActive: true
});

const animationComponent = computed(() => {
  switch (props.animation) {
    case 'globe':
      return GlobeAnimation;
    case 'search':
      return SearchAnimation;
    case 'file':
      return FileAnimation;
    case 'terminal':
      return TerminalAnimation;
    case 'code':
      return CodeAnimation;
    case 'check':
      return CheckAnimation;
    default:
      return SpinnerAnimation;
  }
});
</script>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: var(--background-white-main);
  padding: var(--space-12);
}

.loading-animation {
  margin-bottom: var(--space-6);
}

.loading-text {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-primary);
}

.loading-label {
  font-size: var(--text-base);
  font-weight: var(--font-medium);
}

.loading-detail {
  max-width: 280px;
  margin-top: var(--space-2);
  padding: 0 var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Dark mode enhancements */
:global(.dark) .loading-detail {
  /* Use secondary instead of muted for better visibility in dark mode */
  color: var(--text-secondary);
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
  .loading-animation {
    animation: none;
  }
}
</style>
