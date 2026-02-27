<template>
  <div class="mcp-settings">
    <!-- Status Panel -->
    <McpStatusPanel />

    <!-- Separator -->
    <div class="section-divider" />

    <!-- Tool Browser -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Wrench class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Tool Browser</h4>
          <p class="section-desc">Browse all tools exposed by connected MCP servers</p>
        </div>
      </div>
      <McpToolBrowser />
    </div>

    <!-- Add Server CTA -->
    <div class="add-server-cta">
      <button class="add-btn" @click="openConnectors">
        <Plus class="w-4 h-4" />
        Add MCP Server
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Wrench } from 'lucide-vue-next'
import McpStatusPanel from '@/components/mcp/McpStatusPanel.vue'
import McpToolBrowser from '@/components/mcp/McpToolBrowser.vue'

const emit = defineEmits<{
  openConnectors: []
}>()

function openConnectors() {
  emit('openConnectors')
}
</script>

<style scoped>
.mcp-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-divider {
  height: 1px;
  background: var(--border-main);
  margin: 4px 0;
}

.section-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--fill-tsp-gray-main);
  color: var(--icon-tertiary);
}

.section-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-desc {
  font-size: 12px;
  color: var(--text-tertiary);
}

.add-server-cta {
  display: flex;
  justify-content: center;
  padding-top: 4px;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px dashed var(--border-main);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.add-btn:hover {
  border-color: var(--ring);
  color: var(--text-primary);
  background: var(--fill-tsp-gray-main);
}
</style>
