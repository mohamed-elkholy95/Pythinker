<template>
  <div class="layer-panel">
    <div class="layer-header">
      <span class="layer-title">Layers</span>
      <div class="layer-actions">
        <button
          class="layer-action-btn"
          title="Bring to Front"
          :disabled="selectedElementIds.length === 0"
          @click="handleBringToFront"
        >
          <ArrowUpToLine :size="14" />
        </button>
        <button
          class="layer-action-btn"
          title="Send to Back"
          :disabled="selectedElementIds.length === 0"
          @click="handleSendToBack"
        >
          <ArrowDownToLine :size="14" />
        </button>
      </div>
    </div>

    <div class="layer-list">
      <div
        v-for="element in reversedElements"
        :key="element.id"
        class="layer-row"
        :class="{ selected: isSelected(element.id) }"
        @click="emit('select', element.id)"
      >
        <button
          class="layer-icon-btn"
          :title="element.visible ? 'Hide' : 'Show'"
          @click.stop="emit('toggle-visibility', element.id, !element.visible)"
        >
          <Eye v-if="element.visible" :size="14" />
          <EyeOff v-else :size="14" />
        </button>
        <button
          class="layer-icon-btn"
          :title="element.locked ? 'Unlock' : 'Lock'"
          @click.stop="emit('toggle-lock', element.id, !element.locked)"
        >
          <Lock v-if="element.locked" :size="14" />
          <Unlock v-else :size="14" />
        </button>
        <component :is="getTypeIcon(element.type)" :size="14" class="type-icon" />
        <span class="layer-name">{{ element.name || element.type }}</span>
      </div>

      <div v-if="elements.length === 0" class="empty-layers">
        <span>No elements</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import {
  Eye,
  EyeOff,
  Lock,
  Unlock,
  ArrowUpToLine,
  ArrowDownToLine,
  Square,
  Circle,
  Type,
  ImageIcon,
  Minus,
  Spline,
} from 'lucide-vue-next'
import type { CanvasElement, ElementType } from '@/types/canvas'

const props = defineProps<{
  elements: CanvasElement[]
  selectedElementIds: string[]
}>()

const emit = defineEmits<{
  (e: 'select', elementId: string): void
  (e: 'toggle-visibility', elementId: string, visible: boolean): void
  (e: 'toggle-lock', elementId: string, locked: boolean): void
  (e: 'bring-to-front', elementId: string): void
  (e: 'send-to-back', elementId: string): void
}>()

const reversedElements = computed(() =>
  [...props.elements].sort((a, b) => b.z_index - a.z_index)
)

const selectedSet = computed(() => new Set(props.selectedElementIds))

function isSelected(id: string): boolean {
  return selectedSet.value.has(id)
}

function getTypeIcon(type: ElementType): Component {
  const iconMap: Record<ElementType, Component> = {
    rectangle: Square,
    ellipse: Circle,
    text: Type,
    image: ImageIcon,
    line: Minus,
    path: Spline,
    group: Square,
  }
  return iconMap[type] || Square
}

function handleBringToFront() {
  if (props.selectedElementIds.length > 0) {
    emit('bring-to-front', props.selectedElementIds[0])
  }
}

function handleSendToBack() {
  if (props.selectedElementIds.length > 0) {
    emit('send-to-back', props.selectedElementIds[0])
  }
}
</script>

<style scoped>
.layer-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background-white-main, #ffffff);
  border-top: 1px solid var(--border-light, #e5e5e5);
}

.layer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light, #e5e5e5);
  flex-shrink: 0;
}

.layer-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary, #999999);
}

.layer-actions {
  display: flex;
  gap: 2px;
}

.layer-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--icon-secondary, #666666);
  cursor: pointer;
  transition: background 0.15s;
}

.layer-action-btn:hover:not(:disabled) {
  background: var(--fill-tsp-gray-main, #f0f0f0);
}

.layer-action-btn:disabled {
  opacity: 0.3;
  cursor: default;
}

.layer-list {
  flex: 1;
  overflow-y: auto;
}

.layer-row {
  display: flex;
  align-items: center;
  height: 32px;
  padding: 0 8px;
  gap: 4px;
  cursor: pointer;
  transition: background 0.1s;
  border-bottom: 1px solid transparent;
}

.layer-row:hover {
  background: var(--fill-tsp-gray-main, #f5f5f5);
}

.layer-row.selected {
  background: var(--fill-tsp-gray-main, #f0f0f0);
  border-bottom-color: var(--border-light, #e5e5e5);
}

.layer-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--icon-secondary, #999999);
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s;
}

.layer-icon-btn:hover {
  color: var(--text-primary, #1a1a1a);
}

.type-icon {
  color: var(--icon-secondary, #999999);
  flex-shrink: 0;
  margin: 0 2px;
}

.layer-name {
  font-size: 12px;
  color: var(--text-primary, #1a1a1a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.empty-layers {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: var(--text-tertiary, #999999);
  font-size: 12px;
}
</style>
