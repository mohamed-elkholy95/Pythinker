<template>
  <div class="canvas-toolbar">
    <div class="canvas-toolbar__eyebrow">Tools</div>
    <button
      v-for="tool in tools"
      :key="tool.id"
      class="toolbar-btn"
      :class="{ active: activeTool === tool.id }"
      :title="tool.label"
      @click="emit('tool-change', tool.id)"
    >
      <component :is="tool.icon" :size="20" />
      <span class="toolbar-shortcut">{{ tool.shortcut }}</span>
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
  shortcut: string
}

defineProps<{
  activeTool: EditorTool
}>()

const emit = defineEmits<{
  (e: 'tool-change', tool: EditorTool): void
}>()

const tools: ToolDef[] = [
  { id: 'select', label: 'Select (V)', icon: MousePointer2, shortcut: 'V' },
  { id: 'rectangle', label: 'Rectangle (R)', icon: Square, shortcut: 'R' },
  { id: 'ellipse', label: 'Ellipse (E)', icon: Circle, shortcut: 'E' },
  { id: 'text', label: 'Text (T)', icon: Type, shortcut: 'T' },
  { id: 'image', label: 'Image (I)', icon: ImageIcon, shortcut: 'I' },
  { id: 'pen', label: 'Pen (P)', icon: Pen, shortcut: 'P' },
  { id: 'line', label: 'Line (L)', icon: Minus, shortcut: 'L' },
  { id: 'hand', label: 'Hand (H)', icon: Hand, shortcut: 'H' },
]
</script>

<style scoped>
.canvas-toolbar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 72px;
  padding: 14px 8px;
  height: 100%;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0.8)),
    var(--background-white-main, #ffffff);
  flex-shrink: 0;
}

.canvas-toolbar__eyebrow {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary, #999999);
}

.toolbar-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  width: 52px;
  min-height: 52px;
  border: 1px solid transparent;
  border-radius: 16px;
  background: transparent;
  color: var(--icon-secondary, #666666);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s, transform 0.15s;
}

.toolbar-btn:hover {
  background: rgba(17, 24, 39, 0.05);
  color: var(--text-primary, #1a1a1a);
  transform: translateY(-1px);
}

.toolbar-btn.active {
  background: rgba(17, 24, 39, 0.08);
  color: var(--text-primary, #1a1a1a);
  border-color: rgba(17, 24, 39, 0.12);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.toolbar-shortcut {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-tertiary, #999999);
}
</style>
