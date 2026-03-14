<template>
  <div class="mcp-status-panel">
    <!-- Header -->
    <div class="panel-header">
      <h4 class="panel-title">MCP Servers</h4>
      <button class="refresh-btn" :disabled="loading" @click="refreshStatus" aria-label="Refresh MCP server status">
        <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <!-- Overall Status -->
    <div v-if="servers.length > 0" class="overall-status" :class="overallStatusClass">
      <span class="status-dot" />
      <span class="status-text">{{ overallStatus }}</span>
      <span class="status-meta">{{ healthyCount }}/{{ servers.length }} healthy</span>
      <span class="status-meta">&middot; {{ totalTools }} tools</span>
    </div>

    <!-- Empty State -->
    <div v-if="!loading && servers.length === 0" class="empty-state">
      <Unplug class="w-8 h-8 text-[var(--icon-tertiary)]" />
      <p class="empty-text">No MCP servers connected</p>
      <p class="empty-hint">Add servers via the Connectors dialog</p>
    </div>

    <!-- Server List -->
    <div v-if="servers.length > 0" class="server-list">
      <div
        v-for="server in servers"
        :key="server.name"
        class="server-row"
        @click="toggleExpanded(server.name)"
      >
        <div class="server-info">
          <span class="status-dot" :class="serverStatusClass(server)" />
          <span class="server-name">{{ server.name }}</span>
          <span v-if="server.transport" class="transport-badge">{{ server.transport }}</span>
        </div>
        <div class="server-meta">
          <span class="tool-count">{{ server.tools_count }} tools</span>
          <span v-if="server.avg_response_time_ms > 0" class="response-time">
            {{ Math.round(server.avg_response_time_ms) }}ms
          </span>
          <ChevronDown
            class="w-3.5 h-3.5 expand-icon"
            :class="{ 'rotate-180': expanded[server.name] }"
          />
        </div>

        <!-- Expanded Tools -->
        <Transition name="slide">
          <div v-if="expanded[server.name]" class="server-tools" @click.stop>
            <div v-if="loadingTools[server.name]" class="tools-loading">Loading tools...</div>
            <div v-else-if="serverTools[server.name]?.length" class="tools-list">
              <div
                v-for="tool in serverTools[server.name]"
                :key="tool.name"
                class="tool-item"
              >
                <span class="tool-name">{{ tool.name }}</span>
                <span v-if="tool.description" class="tool-desc">{{ tool.description }}</span>
              </div>
            </div>
            <div v-else class="tools-empty">No tools available</div>

            <!-- Error Details -->
            <div v-if="server.last_error" class="server-error">
              <AlertCircle class="w-3.5 h-3.5" />
              <span>{{ server.last_error }}</span>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      <AlertCircle class="w-4 h-4" />
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { AlertCircle, ChevronDown, RefreshCw, Unplug } from 'lucide-vue-next'
import type { McpServerStatus, McpToolInfo } from '@/api/mcp'
import { useMcpStatus } from '@/composables/useMcpStatus'

const {
  servers,
  overallStatus,
  totalTools,
  loading,
  error,
  healthyCount,
  refreshStatus,
  fetchServerTools,
  startPolling,
  stopPolling,
} = useMcpStatus()

const expanded = reactive<Record<string, boolean>>({})
const serverTools = reactive<Record<string, McpToolInfo[]>>({})
const loadingTools = reactive<Record<string, boolean>>({})

const overallStatusClass = ref('')
function updateOverallClass() {
  if (overallStatus.value === 'healthy') overallStatusClass.value = 'status-healthy'
  else if (overallStatus.value === 'degraded') overallStatusClass.value = 'status-degraded'
  else if (overallStatus.value === 'unhealthy') overallStatusClass.value = 'status-unhealthy'
  else overallStatusClass.value = ''
}

function serverStatusClass(server: McpServerStatus): string {
  if (!server.healthy) return 'dot-red'
  if (server.degraded) return 'dot-yellow'
  return 'dot-green'
}

async function toggleExpanded(name: string) {
  expanded[name] = !expanded[name]
  if (expanded[name] && !serverTools[name]) {
    loadingTools[name] = true
    serverTools[name] = await fetchServerTools(name)
    loadingTools[name] = false
  }
}

onMounted(async () => {
  await refreshStatus()
  updateOverallClass()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.mcp-status-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-main);
  background: var(--fill-tsp-gray-main);
  color: var(--icon-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}
.refresh-btn:hover { background: var(--fill-tsp-gray-hover); color: var(--text-primary); }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.overall-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-main);
  font-size: 12px;
}
.status-text { font-weight: 500; text-transform: capitalize; color: var(--text-primary); }
.status-meta { color: var(--text-tertiary); }

.status-healthy { border-left: 3px solid #22c55e; }
.status-degraded { border-left: 3px solid #eab308; }
.status-unhealthy { border-left: 3px solid #ef4444; }

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-tertiary);
  flex-shrink: 0;
}
.dot-green { background: #22c55e; }
.dot-yellow { background: #eab308; }
.dot-red { background: #ef4444; }

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 16px;
}
.empty-text { font-size: 13px; color: var(--text-secondary); font-weight: 500; }
.empty-hint { font-size: 12px; color: var(--text-tertiary); }

.server-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.server-row {
  display: flex;
  flex-direction: column;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-main);
  cursor: pointer;
  transition: background 0.15s;
}
.server-row:hover { background: var(--fill-tsp-gray-hover); }

.server-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.server-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.transport-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-hover);
  color: var(--text-tertiary);
  font-family: var(--font-mono, monospace);
}

.server-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  padding-left: 16px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.expand-icon { transition: transform 0.2s; }

.server-tools {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-main);
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-item {
  display: flex;
  flex-direction: column;
  padding: 4px 8px;
  border-radius: 4px;
}
.tool-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
}
.tool-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tools-loading,
.tools-empty {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 4px 8px;
}

.server-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  background: rgba(239, 68, 68, 0.08);
  color: #ef4444;
  font-size: 11px;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
  color: #ef4444;
  font-size: 12px;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
