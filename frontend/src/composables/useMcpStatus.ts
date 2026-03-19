import { computed, onScopeDispose, ref } from 'vue'
import type { McpHealthEventData, McpServerStatus, McpToolInfo } from '@/api/mcp'
import { getMcpServers, getMcpServerTools, getMcpStatus } from '@/api/mcp'

// Module-level singleton refs (shared across components)
const servers = ref<McpServerStatus[]>([])
const overallStatus = ref<string>('unknown')
const totalTools = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const toolCache = ref<Record<string, McpToolInfo[]>>({})
let pollTimer: ReturnType<typeof setInterval> | null = null

// Computed
const isAnyUnhealthy = computed(() => servers.value.some((s) => !s.healthy))
const healthyCount = computed(() => servers.value.filter((s) => s.healthy && !s.degraded).length)

async function refreshStatus(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const status = await getMcpStatus()
    servers.value = status.servers
    overallStatus.value = status.overall_status
    totalTools.value = status.total_tools
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to fetch MCP status'
  } finally {
    loading.value = false
  }
}

async function refreshServers(): Promise<void> {
  try {
    servers.value = await getMcpServers()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to fetch servers'
  }
}

async function fetchServerTools(name: string): Promise<McpToolInfo[]> {
  if (toolCache.value[name]) return toolCache.value[name]
  try {
    const result = await getMcpServerTools(name)
    toolCache.value[name] = result.tools
    return result.tools
  } catch {
    return []
  }
}

function startPolling(intervalMs = 30_000): void {
  stopPolling()
  pollTimer = setInterval(() => {
    refreshStatus()
  }, intervalMs)
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function handleHealthEvent(data: McpHealthEventData): void {
  const idx = servers.value.findIndex((s) => s.name === data.server_name)
  if (idx !== -1) {
    servers.value[idx] = {
      ...servers.value[idx],
      healthy: data.healthy,
      degraded: data.degraded,
      tools_count: data.tools_available || servers.value[idx].tools_count,
      avg_response_time_ms: data.avg_response_time_ms,
      success_rate: data.success_rate,
      last_error: data.error,
      last_check: data.last_check,
    }
  } else if (data.server_name) {
    // New server appeared — add it
    servers.value.push({
      name: data.server_name,
      healthy: data.healthy,
      degraded: data.degraded,
      transport: null,
      tools_count: data.tools_available,
      avg_response_time_ms: data.avg_response_time_ms,
      success_rate: data.success_rate,
      last_error: data.error,
      last_check: data.last_check,
      consecutive_failures: 0,
    })
  }
}

export function useMcpStatus() {
  // Auto-cleanup polling when the calling scope is disposed
  onScopeDispose(() => {
    stopPolling()
  })

  return {
    // State
    servers,
    overallStatus,
    totalTools,
    loading,
    error,
    // Computed
    isAnyUnhealthy,
    healthyCount,
    // Actions
    refreshStatus,
    refreshServers,
    fetchServerTools,
    startPolling,
    stopPolling,
    handleHealthEvent,
  }
}
