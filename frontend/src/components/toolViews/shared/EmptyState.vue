<template>
  <div class="empty-state" :class="{ overlay }">
    <component v-if="icon" :is="iconComponent" class="empty-icon" />
    <p class="empty-message">{{ message }}</p>
    <slot name="action"></slot>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { FileText, Terminal, Search, Globe, Code, Inbox } from 'lucide-vue-next';

export interface EmptyStateProps {
  /**
   * Empty state message
   */
  message: string;

  /**
   * Icon to display (optional)
   * - file: File operations
   * - terminal: Shell operations
   * - search: Search operations
   * - browser: Browser operations
   * - code: Code execution
   * - inbox: Generic empty state
   */
  icon?: 'file' | 'terminal' | 'search' | 'browser' | 'code' | 'inbox';

  /**
   * Whether to display as an overlay
   * (useful for showing empty state over existing content)
   */
  overlay?: boolean;
}

const props = withDefaults(defineProps<EmptyStateProps>(), {
  overlay: false
});

const iconComponent = computed(() => {
  switch (props.icon) {
    case 'file':
      return FileText;
    case 'terminal':
      return Terminal;
    case 'search':
      return Search;
    case 'browser':
      return Globe;
    case 'code':
      return Code;
    case 'inbox':
    default:
      return Inbox;
  }
});
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-4);
  text-align: center;
}

.empty-state.overlay {
  position: absolute;
  inset: 0;
  background: var(--background-surface);
  pointer-events: none;
}

:global(.dark) .empty-state.overlay {
  background: var(--background-mask);
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: var(--space-4);
  color: var(--text-tertiary);
  opacity: 0.6;
}

.empty-message {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin: 0;
  max-width: 320px;
}

/* Action slot styling */
.empty-state :deep(button) {
  margin-top: var(--space-4);
}
</style>
