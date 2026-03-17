<template>
  <div class="zoom-controls">
    <button class="zoom-btn" title="Zoom Out" @click="emit('zoom-out')">
      <Minus :size="16" />
    </button>
    <span class="zoom-label">{{ zoomPercent }}%</span>
    <button class="zoom-btn" title="Zoom In" @click="emit('zoom-in')">
      <Plus :size="16" />
    </button>
    <div class="zoom-divider" />
    <button class="zoom-btn" title="Fit to Screen" @click="emit('fit')">
      <Maximize2 :size="16" />
    </button>
    <button class="zoom-btn" title="Reset to 100%" @click="emit('reset')">
      <RotateCcw :size="14" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Minus, Maximize2, RotateCcw } from 'lucide-vue-next'

const props = defineProps<{
  zoom: number
}>()

const emit = defineEmits<{
  (e: 'zoom-in'): void
  (e: 'zoom-out'): void
  (e: 'fit'): void
  (e: 'reset'): void
}>()

const zoomPercent = computed(() => Math.round(props.zoom * 100))
</script>

<style scoped>
.zoom-controls {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 6px;
  background: var(--background-white-main, #ffffff);
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.zoom-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-secondary, #666666);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.zoom-btn:hover {
  background: var(--fill-tsp-gray-main, #f0f0f0);
  color: var(--text-primary, #1a1a1a);
}

.zoom-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #666666);
  min-width: 40px;
  text-align: center;
  user-select: none;
}

.zoom-divider {
  width: 1px;
  height: 16px;
  background: var(--border-light, #e5e5e5);
  margin: 0 2px;
}
</style>
