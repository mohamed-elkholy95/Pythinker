<template>
  <div class="canvas-bottom-toolbar">
    <div class="canvas-bottom-toolbar__group">
      <button
        type="button"
        class="canvas-bottom-toolbar__btn"
        :class="{ 'is-active': activeTool === 'select' }"
        aria-label="Select tool"
        @click="emit('tool-change', 'select')"
      >
        <MousePointer2 :size="18" />
        <ChevronDown :size="12" class="canvas-bottom-toolbar__chevron" />
      </button>
    </div>

    <div class="canvas-bottom-toolbar__separator" />

    <div class="canvas-bottom-toolbar__group">
      <button
        type="button"
        class="canvas-bottom-toolbar__btn"
        aria-label="Image"
      >
        <ImageIcon :size="18" />
      </button>
    </div>

    <div class="canvas-bottom-toolbar__separator" />

    <div class="canvas-bottom-toolbar__group">
      <button
        type="button"
        class="canvas-bottom-toolbar__btn"
        :class="{ 'is-active': activeTool === 'hand' }"
        aria-label="Hand tool"
        @click="emit('tool-change', 'hand')"
      >
        <FileText :size="18" />
        <ChevronDown :size="12" class="canvas-bottom-toolbar__chevron" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronDown, FileText, ImageIcon, MousePointer2 } from 'lucide-vue-next'

interface Props {
  activeTool: 'select' | 'hand'
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'tool-change', tool: 'select' | 'hand'): void
}>()
</script>

<style scoped>
.canvas-bottom-toolbar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2);
  border-radius: var(--radius-2xl);
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  backdrop-filter: blur(12px);
  box-shadow: 0 14px 34px var(--shadow-XS);
  z-index: 10;
}

:global(.dark) .canvas-bottom-toolbar {
  background: #2a2a2a;
  border-color: rgba(255, 255, 255, 0.1);
}

.canvas-bottom-toolbar__group {
  display: flex;
  align-items: center;
}

.canvas-bottom-toolbar__separator {
  width: 1px;
  height: 24px;
  background: var(--border-light);
  flex-shrink: 0;
}

.canvas-bottom-toolbar__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 40px;
  height: 40px;
  padding: 0 var(--space-2);
  border: none;
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.canvas-bottom-toolbar__btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-bottom-toolbar__btn.is-active {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-bottom-toolbar__chevron {
  opacity: 0.6;
}
</style>
