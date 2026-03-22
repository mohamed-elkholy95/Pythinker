<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-header-left">
        <Plug :size="16" class="panel-icon" />
        <span class="panel-title">Connectors</span>
        <span v-if="connectorIds.length > 0" class="panel-count">{{ connectorIds.length }}</span>
      </div>
      <button class="panel-add-btn" type="button" @click="emit('add')">
        <Plus :size="14" />
        <span>Add</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plug, Plus } from 'lucide-vue-next'

defineProps<{
  connectorIds: string[]
}>()

const emit = defineEmits<{
  add: []
}>()
</script>

<style scoped>
.panel {
  border-radius: 12px;
  border: 1px solid var(--border-light);
  padding: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-icon {
  color: var(--text-tertiary);
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-count {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main, #f0f0f0);
  padding: 1px 7px;
  border-radius: 10px;
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
  border-radius: 6px;
  transition: background 0.15s ease;
}

.panel-add-btn:hover {
  background: var(--fill-tsp-gray-main);
}
</style>
