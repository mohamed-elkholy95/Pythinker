<template>
  <div class="content-container" :class="containerClasses">
    <div class="content-inner" :class="innerClasses">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

export interface ContentContainerProps {
  /**
   * Whether content should be scrollable
   */
  scrollable?: boolean;

  /**
   * Whether to center content (for loading/empty states)
   */
  centered?: boolean;

  /**
   * Whether to constrain content width
   * - true: max-width 640px
   * - 'medium': max-width 960px
   * - 'wide': max-width 1200px
   */
  constrained?: boolean | 'medium' | 'wide';

  /**
   * Additional padding
   */
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

const props = withDefaults(defineProps<ContentContainerProps>(), {
  scrollable: true,
  centered: false,
  constrained: false,
  padding: 'md'
});

const containerClasses = computed(() => ({
  'scrollable': props.scrollable,
  'centered': props.centered
}));

const innerClasses = computed(() => {
  const classes: Record<string, boolean> = {};

  // Constrained width
  if (props.constrained === true) {
    classes['constrained'] = true;
  } else if (props.constrained === 'medium') {
    classes['constrained-medium'] = true;
  } else if (props.constrained === 'wide') {
    classes['constrained-wide'] = true;
  }

  // Padding
  if (props.padding !== 'none') {
    classes[`padding-${props.padding}`] = true;
  }

  return classes;
});
</script>

<style scoped>
.content-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.content-container.scrollable {
  overflow: auto;
}

.content-container.centered {
  align-items: center;
  justify-content: center;
}

.content-inner {
  flex: 1;
  width: 100%;
}

/* Width constraints */
.content-inner.constrained {
  max-width: 640px;
  margin: 0 auto;
}

.content-inner.constrained-medium {
  max-width: 960px;
  margin: 0 auto;
}

.content-inner.constrained-wide {
  max-width: 1200px;
  margin: 0 auto;
}

/* Padding variants */
.content-inner.padding-sm {
  padding: var(--space-2) var(--space-3);
}

.content-inner.padding-md {
  padding: var(--space-3) var(--space-4);
}

.content-inner.padding-lg {
  padding: var(--space-6) var(--space-8);
}

/* Scrollbar styling */
.content-container.scrollable::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.content-container.scrollable::-webkit-scrollbar-track {
  background: transparent;
}

.content-container.scrollable::-webkit-scrollbar-thumb {
  background: var(--border-main);
  border-radius: 4px;
}

.content-container.scrollable::-webkit-scrollbar-thumb:hover {
  background: var(--border-dark);
}
</style>
