<template>
  <div class="mcp-settings">
    <!-- Connected Servers Card -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-servers">
          <Plug class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Connected Servers</h4>
          <p class="section-desc">Monitor health and status of your MCP server connections</p>
        </div>
        <button class="add-server-btn" @click="openConnectors">
          <Plus class="w-3.5 h-3.5" />
          <span>Add Server</span>
        </button>
      </div>
      <McpStatusPanel />
    </div>

    <!-- Tool Browser Card -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-tools">
          <Wrench class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Tool Browser</h4>
          <p class="section-desc">Browse and search tools exposed by connected MCP servers</p>
        </div>
      </div>
      <McpToolBrowser />
    </div>

    <!-- Info Footer -->
    <div class="info-card">
      <Info class="w-4 h-4 info-icon" />
      <p>MCP servers extend your agent with additional capabilities. Add custom servers or
        use pre-configured connectors to get started.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Plug, Wrench, Info } from 'lucide-vue-next'
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
  gap: 20px;
  width: 100%;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Add Server Button (inline in header) */
.add-server-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 12px;
  background: var(--text-primary);
  color: var(--background-white-main);
  border: 1px solid var(--text-primary);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 2px;
}
.add-server-btn:hover {
  opacity: 0.85;
}

/* Section Card */
.section-card {
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 1px 3px var(--shadow-XS);
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.section-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  flex-shrink: 0;
}

.section-icon-servers {
  background: #3b82f6;
  color: white;
}

.section-icon-tools {
  background: #8b5cf6;
  color: white;
}

.section-info {
  flex: 1;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.section-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* Info Footer */
.info-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 10px;
}

.info-icon {
  color: var(--icon-tertiary);
  flex-shrink: 0;
  margin-top: 1px;
}

.info-card p {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.5;
}
</style>
