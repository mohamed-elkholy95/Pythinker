<template>
  <div class="mcp-tool-browser">
    <!-- Search -->
    <div class="search-bar">
      <Search class="w-3.5 h-3.5 search-icon" />
      <input
        v-model="query"
        type="text"
        class="search-input"
        placeholder="Filter tools..."
      />
    </div>

    <!-- Tool Groups -->
    <div v-if="groupedTools.length > 0" class="tool-groups">
      <div v-for="group in groupedTools" :key="group.server" class="tool-group">
        <div class="group-header">
          <span class="group-name">{{ group.server }}</span>
          <span class="group-count">{{ group.tools.length }}</span>
        </div>
        <div class="group-tools">
          <div v-for="tool in group.tools" :key="tool.name" class="tool-card">
            <div class="tool-header">
              <Wrench class="w-3.5 h-3.5 text-[var(--icon-tertiary)]" />
              <span class="tool-name">{{ tool.name }}</span>
            </div>
            <p v-if="tool.description" class="tool-desc">{{ tool.description }}</p>
            <details v-if="tool.parameters" class="tool-params">
              <summary class="params-toggle">Parameters</summary>
              <pre class="params-json">{{ formatParams(tool.parameters) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-else class="empty-tools">
      <p class="empty-text">{{ query ? 'No matching tools' : 'No tools available' }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Search, Wrench } from 'lucide-vue-next'
import type { McpToolInfo } from '@/api/mcp'
import { useMcpStatus } from '@/composables/useMcpStatus'

const { servers, fetchServerTools } = useMcpStatus()
const query = ref('')
const allTools = ref<McpToolInfo[]>([])

interface ToolGroup {
  server: string
  tools: McpToolInfo[]
}

const groupedTools = computed<ToolGroup[]>(() => {
  const q = query.value.toLowerCase()
  const filtered = q
    ? allTools.value.filter(
        (t) => t.name.toLowerCase().includes(q) || t.description?.toLowerCase().includes(q),
      )
    : allTools.value

  const groups: Record<string, McpToolInfo[]> = {}
  for (const tool of filtered) {
    const key = tool.server_name || 'default'
    if (!groups[key]) groups[key] = []
    groups[key].push(tool)
  }

  return Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([server, tools]) => ({ server, tools }))
})

function formatParams(params: Record<string, unknown> | null): string {
  if (!params) return ''
  return JSON.stringify(params, null, 2)
}

onMounted(async () => {
  const results: McpToolInfo[] = []
  for (const server of servers.value) {
    const tools = await fetchServerTools(server.name)
    results.push(...tools)
  }
  allTools.value = results
})
</script>

<style scoped>
.mcp-tool-browser {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.search-bar {
  position: relative;
  display: flex;
  align-items: center;
}
.search-icon {
  position: absolute;
  left: 10px;
  color: var(--icon-tertiary);
  pointer-events: none;
}
.search-input {
  width: 100%;
  padding: 7px 10px 7px 30px;
  border: 1px solid var(--border-main);
  border-radius: 8px;
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.search-input:focus { border-color: var(--ring); }
.search-input::placeholder { color: var(--text-tertiary); }

.tool-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 400px;
  overflow-y: auto;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.group-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.group-count {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-hover);
  color: var(--text-tertiary);
}

.group-tools {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-card {
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--fill-tsp-gray-main);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
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
  margin-top: 2px;
  padding-left: 22px;
}

.tool-params {
  margin-top: 6px;
  padding-left: 22px;
}
.params-toggle {
  font-size: 11px;
  color: var(--text-tertiary);
  cursor: pointer;
}
.params-json {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-hover);
  padding: 6px 8px;
  border-radius: 4px;
  margin-top: 4px;
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-tools {
  padding: 24px;
  text-align: center;
}
.empty-text { font-size: 13px; color: var(--text-tertiary); }
</style>
