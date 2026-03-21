<template>
  <div class="canvas-zoom-controls">
    <button
      type="button"
      class="canvas-zoom-controls__settings-btn"
      aria-label="Canvas settings"
      @click="emit('settings-click')"
    >
      <Settings :size="16" />
    </button>

    <div class="canvas-zoom-controls__pill">
      <button
        type="button"
        class="canvas-zoom-controls__btn"
        aria-label="Zoom out"
        @click="emit('zoom-out')"
      >
        <Minus :size="16" />
      </button>

      <span
        class="canvas-zoom-controls__percent"
        role="button"
        tabindex="0"
        aria-label="Reset zoom"
        @click="emit('zoom-reset')"
        @keydown.enter="emit('zoom-reset')"
      >
        {{ displayPercent }}
      </span>

      <button
        type="button"
        class="canvas-zoom-controls__btn"
        aria-label="Zoom in"
        @click="emit('zoom-in')"
      >
        <Plus :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Minus, Plus, Settings } from 'lucide-vue-next'

interface Props {
  zoom: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'zoom-in'): void
  (e: 'zoom-out'): void
  (e: 'zoom-reset'): void
  (e: 'settings-click'): void
}>()

const displayPercent = computed(() => `${Math.round(props.zoom * 100)}%`)
</script>

<style scoped>
.canvas-zoom-controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.canvas-zoom-controls__settings-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-full);
  background: var(--fill-tsp-white-main);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.canvas-zoom-controls__settings-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-zoom-controls__pill {
  display: inline-flex;
  align-items: center;
  height: 36px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-full);
  background: var(--fill-tsp-white-main);
  overflow: hidden;
}

.canvas-zoom-controls__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 100%;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.canvas-zoom-controls__btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-zoom-controls__percent {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  padding: 0 var(--space-1);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  user-select: none;
  transition: color 0.18s ease;
}

.canvas-zoom-controls__percent:hover {
  color: var(--text-secondary);
}
</style>
