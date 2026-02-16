<template>
  <div class="live-viewer-controls">
    <!-- Zoom controls -->
    <div class="controls-group">
      <button
        class="ctrl-btn"
        title="Zoom Out (Ctrl+Scroll)"
        :disabled="!canZoomOut"
        @click="$emit('zoom-out')"
      >
        <Minus :size="15" />
      </button>
      <span class="zoom-label">{{ zoomPercent }}%</span>
      <button
        class="ctrl-btn"
        title="Zoom In (Ctrl+Scroll)"
        :disabled="!canZoomIn"
        @click="$emit('zoom-in')"
      >
        <Plus :size="15" />
      </button>
      <div class="divider" />
      <button class="ctrl-btn" title="Fit to Screen" @click="$emit('fit')">
        <Maximize2 :size="15" />
      </button>
      <button class="ctrl-btn" title="Reset to 100%" @click="$emit('reset')">
        <RotateCcw :size="13" />
      </button>
    </div>

    <!-- Annotation toggle -->
    <div class="controls-group">
      <div class="divider" />
      <button
        class="ctrl-btn"
        :class="{ active: annotationMode }"
        title="Annotation Mode"
        @click="$emit('toggle-annotations')"
      >
        <Pencil :size="15" />
      </button>

      <!-- Agent action overlay toggle -->
      <button
        class="ctrl-btn"
        :class="{ active: showAgentActions }"
        title="Agent Action Overlay"
        @click="$emit('toggle-agent-actions')"
      >
        <Eye :size="15" />
      </button>
    </div>

    <!-- Annotation tools (visible when annotation mode is active) -->
    <template v-if="annotationMode">
      <div class="controls-group annotation-tools">
        <div class="divider" />
        <button
          v-for="tool in annotationTools"
          :key="tool.type"
          class="ctrl-btn"
          :class="{ active: activeTool === tool.type }"
          :title="tool.label"
          @click="$emit('set-tool', tool.type)"
        >
          <component :is="tool.icon" :size="15" />
        </button>
        <div class="divider" />
        <!-- Color picker -->
        <label class="color-picker-wrapper" title="Annotation Color">
          <input
            type="color"
            :value="annotationColor"
            class="color-input"
            @input="$emit('set-color', ($event.target as HTMLInputElement).value)"
          />
          <span class="color-swatch" :style="{ background: annotationColor }" />
        </label>
        <div class="divider" />
        <!-- Undo/Redo/Clear -->
        <button
          class="ctrl-btn"
          title="Undo (Ctrl+Z)"
          :disabled="!canUndo"
          @click="$emit('undo')"
        >
          <Undo2 :size="14" />
        </button>
        <button
          class="ctrl-btn"
          title="Redo (Ctrl+Shift+Z)"
          :disabled="!canRedo"
          @click="$emit('redo')"
        >
          <Redo2 :size="14" />
        </button>
        <button
          class="ctrl-btn danger"
          title="Clear All"
          :disabled="annotationCount === 0"
          @click="$emit('clear-annotations')"
        >
          <Trash2 :size="14" />
        </button>
      </div>
    </template>

    <!-- Stats overlay -->
    <template v-if="showStats && hasFrame">
      <div class="stats-badge">
        <span>{{ fps.toFixed(1) }} FPS</span>
        <span class="stats-sep">|</span>
        <span>{{ formatBytes(bytesPerSec) }}/s</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Plus,
  Minus,
  Maximize2,
  RotateCcw,
  Pencil,
  Eye,
  Undo2,
  Redo2,
  Trash2,
  PenTool,
  Square,
  Circle,
  ArrowRight,
  Type,
  Eraser,
} from 'lucide-vue-next'
import type { AnnotationToolType } from '@/types/liveViewer'

defineProps<{
  zoomPercent: number
  canZoomIn: boolean
  canZoomOut: boolean
  annotationMode: boolean
  activeTool: AnnotationToolType
  annotationColor: string
  canUndo: boolean
  canRedo: boolean
  annotationCount: number
  showAgentActions: boolean
  showStats: boolean
  hasFrame: boolean
  fps: number
  bytesPerSec: number
}>()

defineEmits<{
  (e: 'zoom-in'): void
  (e: 'zoom-out'): void
  (e: 'fit'): void
  (e: 'reset'): void
  (e: 'toggle-annotations'): void
  (e: 'toggle-agent-actions'): void
  (e: 'set-tool', tool: AnnotationToolType): void
  (e: 'set-color', color: string): void
  (e: 'undo'): void
  (e: 'redo'): void
  (e: 'clear-annotations'): void
}>()

const annotationTools = computed(() => [
  { type: 'pen' as const, label: 'Pen (P)', icon: PenTool },
  { type: 'rectangle' as const, label: 'Rectangle (R)', icon: Square },
  { type: 'ellipse' as const, label: 'Ellipse (E)', icon: Circle },
  { type: 'arrow' as const, label: 'Arrow (A)', icon: ArrowRight },
  { type: 'text' as const, label: 'Text (T)', icon: Type },
  { type: 'eraser' as const, label: 'Eraser (X)', icon: Eraser },
])

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes.toFixed(0)} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.live-viewer-controls {
  position: absolute;
  bottom: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 4px;
  z-index: 20;
  pointer-events: auto;
}

.controls-group {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px 5px;
  background: var(--background-white-main, #ffffff);
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.ctrl-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--icon-secondary, #666666);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.ctrl-btn:hover:not(:disabled) {
  background: var(--fill-tsp-gray-main, #f0f0f0);
  color: var(--text-primary, #1a1a1a);
}

.ctrl-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.ctrl-btn.active {
  background: var(--background-black-main, #1a1a1a);
  color: var(--text-white, #ffffff);
}

.ctrl-btn.active:hover {
  background: var(--background-black-main, #1a1a1a);
  color: var(--text-white, #ffffff);
}

.ctrl-btn.danger:hover:not(:disabled) {
  background: var(--function-error-tsp, rgba(239, 68, 68, 0.1));
  color: var(--function-error, #ef4444);
}

.zoom-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary, #666666);
  min-width: 36px;
  text-align: center;
  user-select: none;
}

.divider {
  width: 1px;
  height: 14px;
  background: var(--border-light, #e5e5e5);
  margin: 0 2px;
}

.color-picker-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  cursor: pointer;
}

.color-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
  width: 100%;
  height: 100%;
}

.color-swatch {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 2px solid var(--border-light, #e5e5e5);
  pointer-events: none;
}

.annotation-tools {
  animation: slideIn 0.15s ease-out;
}

.stats-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: var(--background-mask, rgba(0, 0, 0, 0.6));
  border-radius: 6px;
  font-size: 10px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--function-success, #22c55e);
  user-select: none;
}

.stats-sep {
  opacity: 0.5;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
