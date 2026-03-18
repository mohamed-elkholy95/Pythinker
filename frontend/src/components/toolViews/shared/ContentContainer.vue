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
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  --scrollbar-thumb: var(--fill-tsp-white-dark);
  --scrollbar-thumb-hover: var(--fill-tsp-gray-dark);
  --scrollbar-thumb-active: var(--border-dark);
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
  min-height: 0;
  box-sizing: border-box;
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

/* ===== Enhanced Scrollbar ===== */
.content-container.scrollable {
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
  transition: scrollbar-color 0.3s ease;
}

.content-container.scrollable:hover {
  scrollbar-color: var(--scrollbar-thumb) transparent;
}

.content-container.scrollable::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.content-container.scrollable::-webkit-scrollbar-track {
  background: transparent;
  margin: 4px;
}

.content-container.scrollable::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 10px;
  border: 2px solid transparent;
  background-clip: padding-box;
  transition: background-color 0.2s ease, border-width 0.15s ease;
}

.content-container.scrollable:hover::-webkit-scrollbar-thumb {
  background-color: var(--scrollbar-thumb);
}

.content-container.scrollable::-webkit-scrollbar-thumb:hover {
  background-color: var(--scrollbar-thumb-hover);
  border-width: 1px;
}

.content-container.scrollable::-webkit-scrollbar-thumb:active {
  background-color: var(--scrollbar-thumb-active);
}

/* Corner piece */
.content-container.scrollable::-webkit-scrollbar-corner {
  background: transparent;
}

/* Dark theme */
:global(.dark) .content-container {
  --scrollbar-thumb: var(--fill-tsp-white-main);
  --scrollbar-thumb-hover: var(--fill-tsp-white-dark);
  --scrollbar-thumb-active: var(--border-dark);
}
</style>
