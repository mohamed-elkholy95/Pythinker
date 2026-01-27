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
   */
  animation?: 'globe' | 'search' | 'file' | 'terminal' | 'code' | 'spinner';

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
  background: linear-gradient(
    to bottom,
    var(--background-gray-main),
    var(--fill-white)
  );
  padding: var(--space-12);
}

:global(.dark) .loading-state {
  background: linear-gradient(to bottom, #1a1a2e, #16213e);
}

.loading-animation {
  margin-bottom: var(--space-6);
}

.loading-text {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-secondary);
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
  color: var(--text-tertiary);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
  .loading-animation {
    animation: none;
  }
}
</style>
