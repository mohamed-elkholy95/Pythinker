<template>
  <div class="error-state">
    <AlertCircle class="error-icon" />
    <p class="error-message">{{ error }}</p>
    <button
      v-if="retryable"
      @click="emit('retry')"
      class="retry-button"
      aria-label="Retry operation"
    >
      <RefreshCw class="retry-icon" />
      <span>Try Again</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { AlertCircle, RefreshCw } from 'lucide-vue-next';

export interface ErrorStateProps {
  /**
   * Error message to display
   */
  error: string;

  /**
   * Whether to show a retry button
   */
  retryable?: boolean;
}

withDefaults(defineProps<ErrorStateProps>(), {
  retryable: false
});

const emit = defineEmits<{
  retry: [];
}>();
</script>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-4);
  text-align: center;
  width: 100%;
  height: 100%;
  background: var(--background-surface);
  gap: var(--space-2);
}

.error-icon {
  width: 48px;
  height: 48px;
  margin-bottom: var(--space-4);
  color: var(--error-red);
  opacity: 0.9;
}

.error-message {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  max-width: 400px;
  line-height: 1.5;
}

.retry-button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-6);
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.retry-button:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-dark);
}

.retry-button:active {
  transform: scale(0.98);
}

.retry-icon {
  width: 16px;
  height: 16px;
}

/* Focus styles for accessibility */
.retry-button:focus-visible {
  outline: 2px solid var(--text-brand);
  outline-offset: 2px;
}
</style>
