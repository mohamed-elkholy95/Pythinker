<template>
  <div class="canvas-image-action-bar">
    <div class="canvas-image-action-bar__text-group">
      <button
        type="button"
        class="canvas-image-action-bar__btn is-disabled"
        disabled
        aria-label="HD Upscale"
      >
        <span class="canvas-image-action-bar__label">HD Upscale</span>
      </button>

      <button
        type="button"
        class="canvas-image-action-bar__btn is-disabled"
        disabled
        aria-label="Remove background"
      >
        <span class="canvas-image-action-bar__label">Remove bg</span>
      </button>

      <button
        type="button"
        class="canvas-image-action-bar__btn is-disabled"
        disabled
        aria-label="Edit text"
      >
        <span class="canvas-image-action-bar__label">Edit text</span>
      </button>
    </div>

    <div class="canvas-image-action-bar__separator" />

    <div class="canvas-image-action-bar__icon-group">
      <button
        type="button"
        class="canvas-image-action-bar__icon-btn"
        aria-label="Download image"
        @click="emit('download')"
      >
        <Download :size="16" />
      </button>

      <button
        type="button"
        class="canvas-image-action-bar__icon-btn"
        aria-label="More options"
      >
        <MoreHorizontal :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download, MoreHorizontal } from 'lucide-vue-next'

const emit = defineEmits<{
  (e: 'download'): void
}>()
</script>

<style scoped>
.canvas-image-action-bar {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  box-shadow: 0 8px 24px var(--shadow-XS);
}

:global(.dark) .canvas-image-action-bar {
  background: #2a2a2a;
  border-color: rgba(255, 255, 255, 0.1);
}

.canvas-image-action-bar__text-group {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.canvas-image-action-bar__separator {
  width: 1px;
  height: 24px;
  margin: 0 var(--space-1);
  background: var(--border-light);
  flex-shrink: 0;
}

.canvas-image-action-bar__icon-group {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.canvas-image-action-bar__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.canvas-image-action-bar__btn:hover:not(:disabled) {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-image-action-bar__btn.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.canvas-image-action-bar__label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
}

.canvas-image-action-bar__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.canvas-image-action-bar__icon-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}
</style>
