<template>
  <div class="mcp-status-panel">
    <!-- Overall Status Bar (when servers exist) -->
    <div v-if="servers.length > 0" class="status-bar" :class="overallStatusClass">
      <div class="status-bar-left">
        <span class="status-dot" />
        <span class="status-label">{{ overallStatus }}</span>
        <span class="status-divider">&middot;</span>
        <span class="status-meta">{{ healthyCount }}/{{ servers.length }} servers</span>
        <span class="status-divider">&middot;</span>
        <span class="status-meta">{{ totalTools }} tools</span>
      </div>
      <button class="refresh-btn" :disabled="loading" @click.stop="refreshStatus" aria-label="Refresh">
        <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <!-- Server List -->
    <div v-if="servers.length > 0" class="server-list">
      <div
        v-for="server in servers"
        :key="server.name"
        class="server-card"
        :class="{ 'server-unhealthy': !server.healthy }"
        @click="toggleExpanded(server.name)"
      >
        <div class="server-row">
          <div class="server-identity">
            <span class="indicator" :class="serverStatusClass(server)" />
            <span class="server-name">{{ server.name }}</span>
          </div>
          <div class="server-badges">
            <span v-if="server.transport" class="badge badge-transport">{{ server.transport }}</span>
            <span class="badge badge-tools">{{ server.tools_count }} tools</span>
            <span v-if="server.avg_response_time_ms > 0" class="badge badge-latency">
              {{ Math.round(server.avg_response_time_ms) }}ms
            </span>
            <ChevronDown
              class="w-3.5 h-3.5 chevron"
              :class="{ 'chevron-open': expanded[server.name] }"
            />
          </div>
        </div>

        <!-- Expanded Tools -->
        <Transition name="expand">
          <div v-if="expanded[server.name]" class="server-details" @click.stop>
            <div v-if="loadingTools[server.name]" class="detail-loading">
              <RefreshCw class="w-3 h-3 animate-spin" />
              <span>Loading tools...</span>
            </div>
            <div v-else-if="serverTools[server.name]?.length" class="detail-tools">
              <div
                v-for="tool in serverTools[server.name]"
                :key="tool.name"
                class="detail-tool"
              >
                <code class="detail-tool-name">{{ tool.name }}</code>
                <span v-if="tool.description" class="detail-tool-desc">{{ tool.description }}</span>
              </div>
            </div>
            <div v-else class="detail-empty">No tools registered</div>

            <div v-if="server.last_error" class="detail-error">
              <AlertCircle class="w-3.5 h-3.5" />
              <span>{{ server.last_error }}</span>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!loading && servers.length === 0" class="empty-state">
      <div class="empty-visual">
        <div class="empty-icon-ring">
          <Unplug class="w-5 h-5" />
        </div>
      </div>
      <p class="empty-title">No servers connected</p>
      <p class="empty-hint">Connect an MCP server to extend your agent's capabilities</p>
      <button class="empty-refresh" :disabled="loading" @click="refreshStatus">
        <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
        Check again
      </button>
    </div>

    <!-- Global Error Banner -->
    <div v-if="error" class="error-banner">
      <AlertCircle class="w-4 h-4" />
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive } from 'vue'
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

const overallStatusClass = computed(() => {
  if (overallStatus.value === 'healthy') return 'bar-healthy'
  if (overallStatus.value === 'degraded') return 'bar-degraded'
  if (overallStatus.value === 'unhealthy') return 'bar-unhealthy'
  return ''
})

function serverStatusClass(server: McpServerStatus): string {
  if (!server.healthy) return 'indicator-red'
  if (server.degraded) return 'indicator-yellow'
  return 'indicator-green'
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
  gap: 10px;
}

/* ── Status Bar ── */
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  font-size: 12px;
}

.status-bar-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.bar-healthy { background: rgba(34, 197, 94, 0.06); border-color: rgba(34, 197, 94, 0.2); }
.bar-degraded { background: rgba(234, 179, 8, 0.06); border-color: rgba(234, 179, 8, 0.2); }
.bar-unhealthy { background: rgba(239, 68, 68, 0.06); border-color: rgba(239, 68, 68, 0.2); }

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.bar-healthy .status-dot { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
.bar-degraded .status-dot { background: #eab308; box-shadow: 0 0 6px rgba(234, 179, 8, 0.5); }
.bar-unhealthy .status-dot { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.5); }

.status-label {
  font-weight: 600;
  text-transform: capitalize;
  color: var(--text-primary);
}

.status-divider {
  color: var(--text-quaternary);
}

.status-meta {
  color: var(--text-tertiary);
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  border: 1px solid var(--border-light);
  background: transparent;
  color: var(--icon-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}
.refresh-btn:hover { color: var(--text-primary); background: var(--fill-tsp-gray-main); }
.refresh-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Server List ── */
.server-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.server-card {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: all 0.15s;
}
.server-card:hover {
  border-color: var(--border-main);
  box-shadow: 0 1px 4px var(--shadow-XS);
}
.server-unhealthy {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.02);
}

.server-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.server-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.indicator-green { background: #22c55e; box-shadow: 0 0 5px rgba(34, 197, 94, 0.4); }
.indicator-yellow { background: #eab308; box-shadow: 0 0 5px rgba(234, 179, 8, 0.4); }
.indicator-red { background: #ef4444; box-shadow: 0 0 5px rgba(239, 68, 68, 0.4); }

.server-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.server-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.badge {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 7px;
  border-radius: 5px;
  white-space: nowrap;
}

.badge-transport {
  background: rgba(59, 130, 246, 0.08);
  color: #3b82f6;
  font-family: var(--font-mono, monospace);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.badge-tools {
  background: var(--fill-tsp-gray-main);
  color: var(--text-tertiary);
}

.badge-latency {
  background: var(--fill-tsp-gray-main);
  color: var(--text-tertiary);
  font-family: var(--font-mono, monospace);
}

.chevron {
  color: var(--icon-tertiary);
  transition: transform 0.2s ease;
}
.chevron-open { transform: rotate(180deg); }

/* ── Expanded Details ── */
.server-details {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-light);
}

.detail-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 4px 0;
}

.detail-tools {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-tool {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 6px 10px;
  border-radius: 6px;
  transition: background 0.1s;
}
.detail-tool:hover { background: var(--fill-tsp-gray-main); }

.detail-tool-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
}

.detail-tool-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-empty {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 4px 0;
}

.detail-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.12);
  color: #ef4444;
  font-size: 11px;
  line-height: 1.4;
}

/* ── Empty State ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 28px 16px 24px;
}

.empty-visual {
  margin-bottom: 2px;
}

.empty-icon-ring {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
  color: #3b82f6;
}

.empty-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
}

.empty-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
  max-width: 260px;
  line-height: 1.4;
}

.empty-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.empty-refresh:hover { color: var(--text-primary); border-color: var(--border-dark); }
.empty-refresh:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Error Banner ── */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.15);
  color: #ef4444;
  font-size: 12px;
}

/* ── Transitions ── */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.expand-enter-to,
.expand-leave-from {
  max-height: 400px;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
