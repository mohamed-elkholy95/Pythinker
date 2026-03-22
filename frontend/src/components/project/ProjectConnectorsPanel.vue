<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-header-left">
        <Plug :size="16" class="panel-icon" />
        <span class="panel-title">Connectors</span>
        <span v-if="connectedCount > 0" class="panel-count">{{ connectedCount }}</span>
      </div>
      <button class="panel-add-btn" type="button" @click="openConnectorDialog('apps')">
        <Plus :size="14" />
        <span>Add</span>
      </button>
    </div>
    <!-- Show connected connector names -->
    <div v-if="connectedConnectors.length > 0" class="panel-items">
      <div v-for="uc in connectedConnectors.slice(0, 4)" :key="uc.id" class="panel-item">
        <span class="panel-item-dot" />
        <span class="panel-item-name">{{ uc.name }}</span>
      </div>
      <button v-if="connectedConnectors.length > 4" class="panel-more" type="button" @click="openConnectorDialog('apps')">
        +{{ connectedConnectors.length - 4 }} more
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plug, Plus } from 'lucide-vue-next'
import { useConnectors } from '@/composables/useConnectors'
import { useConnectorDialog } from '@/composables/useConnectorDialog'

const { connectedConnectors, connectedCount } = useConnectors()
const { openConnectorDialog } = useConnectorDialog()
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

.panel-items {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.panel-item-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
  flex-shrink: 0;
}

.panel-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-more {
  font-size: 12px;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 0;
  text-align: left;
}
.panel-more:hover {
  color: var(--text-secondary);
}
</style>
