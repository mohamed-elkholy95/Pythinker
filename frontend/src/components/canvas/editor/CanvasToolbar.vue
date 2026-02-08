<template>
  <div class="canvas-toolbar">
    <button
      v-for="tool in tools"
      :key="tool.id"
      class="toolbar-btn"
      :class="{ active: activeTool === tool.id }"
      :title="tool.label"
      @click="emit('tool-change', tool.id)"
    >
      <component :is="tool.icon" :size="20" />
    </button>
  </div>
</template>

<script setup lang="ts">
import {
  MousePointer2,
  Square,
  Circle,
  Type,
  ImageIcon,
  Minus,
  Pen,
  Hand,
} from 'lucide-vue-next'
import type { EditorTool } from '@/types/canvas'
import type { Component } from 'vue'

interface ToolDef {
  id: EditorTool
  label: string
  icon: Component
}

defineProps<{
  activeTool: EditorTool
}>()

const emit = defineEmits<{
  (e: 'tool-change', tool: EditorTool): void
}>()

const tools: ToolDef[] = [
  { id: 'select', label: 'Select (V)', icon: MousePointer2 },
  { id: 'rectangle', label: 'Rectangle (R)', icon: Square },
  { id: 'ellipse', label: 'Ellipse (E)', icon: Circle },
  { id: 'text', label: 'Text (T)', icon: Type },
  { id: 'image', label: 'Image (I)', icon: ImageIcon },
  { id: 'pen', label: 'Pen (P)', icon: Pen },
  { id: 'line', label: 'Line (L)', icon: Minus },
  { id: 'hand', label: 'Hand (H)', icon: Hand },
]
</script>

<style scoped>
.canvas-toolbar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 48px;
  padding: 8px 0;
  height: 100%;
  background: var(--background-white-main, #ffffff);
  border-right: 1px solid var(--border-light, #e5e5e5);
  flex-shrink: 0;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--icon-secondary, #666666);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.toolbar-btn:hover {
  background: var(--fill-tsp-gray-main, #f0f0f0);
  color: var(--text-primary, #1a1a1a);
}

.toolbar-btn.active {
  background: var(--fill-tsp-gray-main, #f0f0f0);
  color: var(--text-primary, #1a1a1a);
  box-shadow: inset 0 0 0 1px var(--border-light, #e5e5e5);
}
</style>
