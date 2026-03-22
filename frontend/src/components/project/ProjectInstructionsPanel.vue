<template>
  <div class="panel" @click="emit('edit')">
    <div class="panel-header">
      <span class="panel-title">Instructions</span>
      <ChevronRight :size="16" class="panel-chevron" />
    </div>
    <p v-if="instructions" class="panel-preview">{{ instructions }}</p>
    <p v-else class="panel-description">Add custom instructions for all tasks in this project.</p>
    <button class="panel-add-btn" type="button" @click.stop="emit('edit')">
      <Plus :size="14" />
      <span>{{ instructions ? 'Edit' : 'Add' }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Plus } from 'lucide-vue-next'

defineProps<{
  instructions: string
}>()

const emit = defineEmits<{
  edit: []
}>()
</script>

<style scoped>
.panel {
  border-radius: 12px;
  border: 1px solid var(--border-light);
  padding: 16px;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.panel:hover {
  border-color: var(--border-main);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-chevron {
  color: var(--text-tertiary);
}

.panel-preview {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.panel-description {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0 0 12px;
  line-height: 1.5;
}

.panel-add-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  margin-left: -8px;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.panel-add-btn:hover {
  background: var(--fill-tsp-gray-main);
}
</style>
