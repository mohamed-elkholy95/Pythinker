<template>
  <div class="export-dialog-backdrop" @click.self="emit('close')">
    <div class="export-dialog">
      <div class="export-header">
        <div class="export-title">
          <Download :size="16" />
          <span>Export</span>
        </div>
        <button class="export-close" @click="emit('close')" aria-label="Close">
          <X :size="14" />
        </button>
      </div>
      <div class="export-options">
        <button class="export-option" @click="emit('export-png')">
          <Image :size="16" />
          <div class="export-option-text">
            <span class="export-option-title">Export as PNG</span>
            <span class="export-option-subtitle">High-quality image</span>
          </div>
        </button>
        <button class="export-option" @click="emit('export-json')">
          <FileJson :size="16" />
          <div class="export-option-text">
            <span class="export-option-title">Export as JSON</span>
            <span class="export-option-subtitle">Editable project data</span>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download, Image, FileJson, X } from 'lucide-vue-next'
import type { CanvasProject } from '@/types/canvas'

defineProps<{
  project: CanvasProject | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'export-png'): void
  (e: 'export-json'): void
}>()
</script>

<style scoped>
.export-dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.export-dialog {
  width: 320px;
  background: var(--background-white-main, #ffffff);
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 14px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.18);
  padding: 12px;
}

.export-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 4px 8px;
}

.export-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1a1a1a);
}

.export-close {
  display: inline-flex;
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

.export-close:hover {
  background: var(--fill-tsp-gray-main, #f0f0f0);
  color: var(--text-primary, #1a1a1a);
}

.export-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.export-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 10px;
  background: var(--background-white-main, #ffffff);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
  text-align: left;
}

.export-option:hover {
  background: var(--fill-tsp-gray-main, #f5f5f5);
  border-color: var(--text-tertiary, #999999);
  transform: translateY(-1px);
}

.export-option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.export-option-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a1a);
}

.export-option-subtitle {
  font-size: 11px;
  color: var(--text-tertiary, #999999);
}
</style>
