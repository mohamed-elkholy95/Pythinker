<template>
  <div class="mcp-tool-browser">
    <!-- Search -->
    <div class="search-wrapper">
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
        <div class="group-label">
          <span class="group-name">{{ group.server }}</span>
          <span class="group-count">{{ group.tools.length }}</span>
        </div>
        <div class="group-list">
          <div v-for="tool in group.tools" :key="tool.name" class="tool-row">
            <div class="tool-main">
              <code class="tool-name">{{ tool.name }}</code>
              <span v-if="tool.description" class="tool-desc">{{ tool.description }}</span>
            </div>
            <details v-if="tool.parameters" class="tool-params">
              <summary class="params-toggle">Params</summary>
              <pre class="params-json">{{ formatParams(tool.parameters) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-else class="empty-tools">
      <p>{{ query ? 'No matching tools found' : 'No tools available' }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Search } from 'lucide-vue-next'
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
  const toolArrays = await Promise.all(
    servers.value.map((server) => fetchServerTools(server.name)),
  )
  allTools.value = toolArrays.flat()
})
</script>

<style scoped>
.mcp-tool-browser {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Search ── */
.search-wrapper {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--icon-tertiary);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 38px;
  padding: 0 12px 0 34px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: all 0.15s;
}
.search-input:hover { border-color: var(--border-main); }
.search-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1); }
.search-input::placeholder { color: var(--text-quaternary); }

/* ── Tool Groups ── */
.tool-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 380px;
  overflow-y: auto;
  padding-right: 2px;
}

.group-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.group-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.group-count {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.08);
  color: #3b82f6;
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* ── Tool Row ── */
.tool-row {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-light);
  transition: all 0.15s;
}
.tool-row:hover {
  border-color: var(--border-main);
  box-shadow: 0 1px 3px var(--shadow-XS);
}

.tool-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tool-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
}

.tool-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Parameters ── */
.tool-params {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-light);
}

.params-toggle {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  cursor: pointer;
  user-select: none;
}
.params-toggle:hover { color: var(--text-secondary); }

.params-json {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
  padding: 8px 10px;
  border-radius: 6px;
  margin-top: 6px;
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}

/* ── Empty ── */
.empty-tools {
  padding: 20px;
  text-align: center;
}

.empty-tools p {
  font-size: 13px;
  color: var(--text-tertiary);
}
</style>
