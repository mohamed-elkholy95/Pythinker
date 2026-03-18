<template>
  <div class="usage-settings">
    <!-- Error banner -->
    <Transition name="slide-fade">
      <div v-if="overviewError" class="error-banner">
        <AlertCircle class="w-4 h-4 flex-shrink-0" />
        <span>{{ overviewError.message }}</span>
        <button class="error-retry" @click="refreshUsage">Retry</button>
      </div>
    </Transition>

    <!-- Top bar: period selector + refresh -->
    <div class="dashboard-topbar">
      <div class="topbar-left">
        <span v-if="lastUpdated" class="last-updated" aria-live="polite">
          Updated {{ lastUpdated }}
        </span>
      </div>
      <div class="topbar-right">
        <div class="segment-group" role="tablist" aria-label="Time range">
          <button
            v-for="option in rangeOptions"
            :key="option.value"
            role="tab"
            :aria-selected="selectedRange === option.value"
            class="segment"
            :class="{ 'segment-active': selectedRange === option.value }"
            @click="selectedRange = option.value"
          >
            {{ option.label }}
          </button>
        </div>
        <button
          class="refresh-btn"
          :class="{ 'refresh-spinning': loadingOverview }"
          aria-label="Refresh usage data"
          @click="refreshUsage"
        >
          <RefreshCw class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Legacy fallback notice -->
    <div v-if="showLegacyFallback" class="fallback-banner">
      <Info class="w-3.5 h-3.5 flex-shrink-0" />
      <span>Run-level telemetry is not available for this window. Legacy billing totals are shown where possible.</span>
    </div>

    <!-- Hero KPI cards -->
    <div class="kpi-grid">
      <div
        v-for="card in summaryCards"
        :key="card.label"
        class="kpi-card"
        :class="card.tone"
      >
        <div class="kpi-accent" />
        <div class="kpi-body">
          <div class="kpi-top">
            <div class="kpi-icon">
              <component :is="card.icon" class="w-4 h-4" />
            </div>
            <span class="kpi-label">{{ card.label }}</span>
          </div>

          <div v-if="loadingOverview" class="kpi-skeleton">
            <span class="skeleton skeleton-lg" />
            <span class="skeleton skeleton-sm" />
          </div>
          <template v-else>
            <div class="kpi-value">{{ card.value }}</div>
            <div class="kpi-detail">{{ card.detail }}</div>
            <div v-if="card.subdetail" class="kpi-sub">{{ card.subdetail }}</div>
          </template>
        </div>
      </div>
    </div>

    <!-- Usage Trends Chart -->
    <section class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-blue">
          <BarChart3 class="w-[18px] h-[18px]" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Usage Trends</h4>
          <p class="section-desc">Track cost, runs, token volume, and tool activity over time.</p>
        </div>
        <div class="section-actions">
          <div class="segment-group" role="tablist" aria-label="Chart metric">
            <button
              v-for="option in metricOptions"
              :key="option.value"
              role="tab"
              :aria-selected="selectedMetric === option.value"
              class="segment segment-sm"
              :class="{ 'segment-active': selectedMetric === option.value }"
              @click="selectedMetric = option.value"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </div>

      <div class="chart-shell">
        <UsageChart
          v-if="!loadingOverview && chartData.length"
          :data="chartData"
          :metric="selectedMetric"
          :legend-label="chartLegend"
        />
        <div v-else-if="loadingOverview" class="state-placeholder">
          <Loader2 class="w-5 h-5 animate-spin" />
          <span>Loading trends...</span>
        </div>
        <div v-else class="state-placeholder state-empty">
          <BarChart3 class="w-7 h-7" />
          <span>No usage data recorded yet</span>
          <p class="state-hint">Data will appear here once you start using the agent.</p>
        </div>
      </div>
    </section>

    <!-- Two-column: Recent Runs + Breakdown -->
    <div class="panel-grid">
      <!-- Recent Runs / Legacy Activity -->
      <section class="section-card">
        <div class="section-header">
          <div class="section-icon section-icon-green">
            <Clock3 class="w-[18px] h-[18px]" />
          </div>
          <div class="section-info">
            <h4 class="section-title">{{ hasAgentData ? 'Recent Runs' : 'Recent Activity' }}</h4>
            <p class="section-desc">
              {{ hasAgentData ? 'Latest agent executions with cost and timing.' : 'Legacy daily activity totals.' }}
            </p>
          </div>
        </div>

        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr v-if="hasAgentData">
                <th>Status</th>
                <th>Started</th>
                <th class="col-right">Duration</th>
                <th class="col-right">Cost</th>
                <th class="col-right">Tokens</th>
                <th>Model</th>
              </tr>
              <tr v-else>
                <th>Date</th>
                <th class="col-right">Tokens</th>
                <th class="col-right">Cost</th>
                <th class="col-right">Tools</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingOverview">
                <td :colspan="hasAgentData ? 6 : 4" class="table-state">
                  <Loader2 class="w-4 h-4 animate-spin" />
                  <span>Loading...</span>
                </td>
              </tr>
              <tr v-else-if="hasAgentData && !agentRuns.length">
                <td colspan="6" class="table-state">No runs recorded for this window.</td>
              </tr>
              <tr v-else-if="!hasAgentData && !legacyRows.length">
                <td colspan="4" class="table-state">No legacy activity recorded.</td>
              </tr>
              <template v-else-if="hasAgentData">
                <tr v-for="run in agentRuns" :key="run.run_id" class="table-row-hover">
                  <td>
                    <span class="status-badge" :class="statusClass(run.status)">
                      <span class="status-dot" />
                      {{ formatStatus(run.status) }}
                    </span>
                  </td>
                  <td class="cell-muted">{{ formatDateLabel(run.started_at) }}</td>
                  <td class="col-right cell-mono">{{ formatDuration(run.duration_ms) }}</td>
                  <td class="col-right cell-mono">{{ formatCost(run.total_cost) }}</td>
                  <td class="col-right cell-mono">{{ formatTokens(run.total_tokens) }}</td>
                  <td class="cell-truncate">{{ run.primary_model || run.primary_provider || '\u2014' }}</td>
                </tr>
              </template>
              <template v-else>
                <tr v-for="day in legacyRows" :key="day.date" class="table-row-hover">
                  <td class="cell-muted">{{ formatDateLabel(day.date) }}</td>
                  <td class="col-right cell-mono">{{ formatTokens(day.total_prompt_tokens + day.total_completion_tokens) }}</td>
                  <td class="col-right cell-mono">{{ formatCost(day.total_cost) }}</td>
                  <td class="col-right cell-mono">{{ day.tool_call_count }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Breakdown -->
      <section class="section-card">
        <div class="section-header section-header-wrap">
          <div class="section-header-left">
            <div class="section-icon section-icon-purple">
              <Layers3 class="w-[18px] h-[18px]" />
            </div>
            <div class="section-info">
              <h4 class="section-title">Breakdown</h4>
              <p class="section-desc">Cost and usage grouped by dimension.</p>
            </div>
          </div>
          <div class="segment-group" role="tablist" aria-label="Breakdown dimension">
            <button
              v-for="option in breakdownOptions"
              :key="option.value"
              role="tab"
              :aria-selected="selectedBreakdown === option.value"
              class="segment segment-sm"
              :class="{ 'segment-active': selectedBreakdown === option.value }"
              @click="selectedBreakdown = option.value"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <div v-if="!hasAgentData" class="state-placeholder state-empty state-empty-sm">
          <Layers3 class="w-6 h-6" />
          <span>Breakdowns appear once run-level telemetry is available.</span>
        </div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>{{ breakdownHeader }}</th>
                <th class="col-right">Runs</th>
                <th class="col-right">Tokens</th>
                <th class="col-right">Cost</th>
                <th class="col-right">Errors</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingBreakdown">
                <td colspan="5" class="table-state">
                  <Loader2 class="w-4 h-4 animate-spin" />
                  <span>Loading...</span>
                </td>
              </tr>
              <tr v-else-if="!breakdownRows.length">
                <td colspan="5" class="table-state">No grouped usage available.</td>
              </tr>
              <tr v-for="row in breakdownRows" v-else :key="row.key" class="table-row-hover">
                <td class="cell-truncate">
                  <span class="breakdown-key">{{ row.key }}</span>
                </td>
                <td class="col-right cell-mono">{{ row.run_count }}</td>
                <td class="col-right cell-mono">{{ formatTokens(row.input_tokens + row.output_tokens) }}</td>
                <td class="col-right cell-mono">{{ formatCost(row.cost) }}</td>
                <td class="col-right">
                  <span v-if="row.error_rate > 0" class="error-rate" :class="errorRateClass(row.error_rate)">
                    {{ formatPercent(row.error_rate) }}
                  </span>
                  <span v-else class="cell-muted">\u2014</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- Efficiency KPIs -->
    <section class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-amber">
          <Gauge class="w-[18px] h-[18px]" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Efficiency</h4>
          <p class="section-desc">Unit economics and cache behavior.</p>
        </div>
      </div>

      <div class="efficiency-grid">
        <div
          v-for="item in efficiencyCards"
          :key="item.label"
          class="eff-card"
          :style="{ '--accent': item.accent }"
        >
          <span class="eff-label">{{ item.label }}</span>
          <span class="eff-value">{{ item.value }}</span>
          <span class="eff-detail">{{ item.detail }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useDebounceFn } from '@vueuse/core'
import { computed, onMounted, ref, watch } from 'vue'
import {
  AlertCircle,
  BarChart3,
  Clock3,
  Gauge,
  Info,
  Layers3,
  Loader2,
  RefreshCw,
  ShieldCheck,
  TimerReset,
  TrendingUp,
  Wallet,
} from 'lucide-vue-next'

import UsageChart from './UsageChart.vue'
import { useAgentUsage } from '@/composables/useAgentUsage'
import type { AgentUsageBreakdownGroup, AgentUsageRange } from '@/api/usage'

type ChartMetric = 'cost' | 'runs' | 'tokens' | 'tools'

const rangeOptions: Array<{ label: string; value: AgentUsageRange }> = [
  { label: '7 days', value: '7d' },
  { label: '30 days', value: '30d' },
  { label: '90 days', value: '90d' },
]

const metricOptions: Array<{ label: string; value: ChartMetric }> = [
  { label: 'Cost', value: 'cost' },
  { label: 'Runs', value: 'runs' },
  { label: 'Tokens', value: 'tokens' },
  { label: 'Tools', value: 'tools' },
]

const breakdownOptions: Array<{ label: string; value: AgentUsageBreakdownGroup }> = [
  { label: 'Model', value: 'model' },
  { label: 'Provider', value: 'provider' },
  { label: 'Tool', value: 'tool' },
  { label: 'MCP', value: 'mcp_server' },
]

const selectedRange = ref<AgentUsageRange>('30d')
const selectedMetric = ref<ChartMetric>('cost')
const selectedBreakdown = ref<AgentUsageBreakdownGroup>('model')
const lastUpdated = ref<string | null>(null)

const {
  agentBreakdown,
  agentRuns,
  agentSummary,
  agentTimeseries,
  hasAgentData,
  legacyDailyUsage,
  legacySummary,
  loadBreakdown,
  loadOverview,
  loadingBreakdown,
  loadingOverview,
  overviewError,
} = useAgentUsage()

const showLegacyFallback = computed(
  () => !hasAgentData.value && (legacySummary.value?.month.llm_calls ?? 0) > 0,
)

const summaryCards = computed(() => {
  const useAgent = hasAgentData.value
  const summary = useAgent ? agentSummary.value : null
  const legacy = legacySummary.value
  const totalCost = summary?.total_cost ?? legacy?.month.cost ?? 0
  const runCount = summary?.run_count ?? legacy?.month.sessions ?? 0
  const completedRuns = summary?.completed_run_count ?? 0
  const failedRuns = summary?.failed_run_count ?? 0
  const toolCalls = summary?.total_tool_calls ?? legacy?.month.tool_calls ?? 0
  const mcpCalls = summary?.total_mcp_calls ?? 0

  return [
    {
      label: 'Total Cost',
      value: formatCost(totalCost),
      detail: summary
        ? `${formatTokens(summary.total_input_tokens)} in \u00b7 ${formatTokens(summary.total_output_tokens)} out`
        : `${formatCost(legacy?.today.cost ?? 0)} today`,
      subdetail: summary
        ? `${formatTokens(summary.total_cached_input_tokens)} cached \u00b7 ${formatTokens(summary.total_reasoning_tokens)} reasoning`
        : `${legacy?.month.llm_calls ?? 0} LLM calls this month`,
      icon: Wallet,
      tone: 'tone-cost',
    },
    {
      label: 'Agent Runs',
      value: runCount.toLocaleString('en-US'),
      detail: summary
        ? `${completedRuns} completed \u00b7 ${failedRuns} failed`
        : `${legacy?.month.sessions ?? 0} sessions`,
      subdetail: summary
        ? `${toolCalls} tool calls \u00b7 ${mcpCalls} MCP calls`
        : 'Legacy session totals',
      icon: TrendingUp,
      tone: 'tone-runs',
    },
    {
      label: 'Success Rate',
      value: summary ? formatPercent(summary.success_rate) : '\u2014',
      detail: summary ? `${completedRuns} successes in window` : 'Run-level outcomes unavailable',
      subdetail: summary ? `${failedRuns} failed runs` : 'Enable telemetry for tracking',
      icon: ShieldCheck,
      tone: 'tone-success',
    },
    {
      label: 'Avg Duration',
      value: summary ? formatDuration(summary.avg_run_duration_ms) : '\u2014',
      detail: summary ? `${toolCalls} tool calls in range` : 'Duration unavailable',
      subdetail: summary ? `${mcpCalls} MCP calls in range` : 'Legacy data lacks timing',
      icon: TimerReset,
      tone: 'tone-duration',
    },
  ]
})

const chartLegend = computed(() => {
  return {
    cost: hasAgentData.value ? 'Estimated daily agent cost' : 'Legacy daily cost',
    runs: hasAgentData.value ? 'Daily agent runs' : 'Legacy LLM activity',
    tokens: hasAgentData.value ? 'Input + output token volume' : 'Legacy prompt + completion tokens',
    tools: hasAgentData.value ? 'Tool and MCP activity' : 'Legacy tool activity',
  }[selectedMetric.value]
})

const chartData = computed(() => {
  if (hasAgentData.value) {
    return [...agentTimeseries.value]
      .sort((left, right) => new Date(left.date).getTime() - new Date(right.date).getTime())
      .map((point) => {
        if (selectedMetric.value === 'cost') {
          return {
            date: point.date,
            value: point.cost,
            detail: `${point.run_count} runs \u00b7 ${point.success_count} succeeded`,
          }
        }
        if (selectedMetric.value === 'runs') {
          return {
            date: point.date,
            value: point.run_count,
            detail: `${point.success_count} ok \u00b7 ${point.failed_count} failed`,
          }
        }
        if (selectedMetric.value === 'tools') {
          return {
            date: point.date,
            value: point.tool_calls + point.mcp_calls,
            detail: `${point.tool_calls} tools \u00b7 ${point.mcp_calls} MCP`,
          }
        }
        return {
          date: point.date,
          value: point.input_tokens + point.output_tokens,
          detail: `${formatTokens(point.cached_input_tokens)} cached \u00b7 ${formatTokens(point.reasoning_tokens)} reasoning`,
        }
      })
  }

  return [...legacyDailyUsage.value]
    .sort((left, right) => new Date(left.date).getTime() - new Date(right.date).getTime())
    .map((day) => {
      if (selectedMetric.value === 'cost') {
        return { date: day.date, value: day.total_cost, detail: `${day.llm_call_count} calls` }
      }
      if (selectedMetric.value === 'runs') {
        return { date: day.date, value: day.llm_call_count, detail: `${day.tool_call_count} tools` }
      }
      if (selectedMetric.value === 'tools') {
        return {
          date: day.date,
          value: day.tool_call_count,
          detail: `${day.llm_call_count} LLM calls`,
        }
      }
      return {
        date: day.date,
        value: day.total_prompt_tokens + day.total_completion_tokens,
        detail: `${formatTokens(day.total_cached_tokens)} cached`,
      }
    })
})

const legacyRows = computed(() => {
  return [...legacyDailyUsage.value]
    .sort((left, right) => new Date(right.date).getTime() - new Date(left.date).getTime())
    .slice(0, 7)
})

const breakdownHeader = computed(() => {
  return { model: 'Model', provider: 'Provider', tool: 'Tool', mcp_server: 'MCP Server' }[
    selectedBreakdown.value
  ]
})

const breakdownRows = computed(() => agentBreakdown.value.slice(0, 8))

const ACCENT_COLORS = ['#0ea5e9', '#6366f1', '#22c55e', '#f97316'] as const

const efficiencyCards = computed(() => {
  const summary = agentSummary.value
  const legacy = legacySummary.value
  const successfulRuns = summary?.completed_run_count ?? 0
  const runCount = summary?.run_count ?? 0
  const totalTokens = (summary?.total_input_tokens ?? 0) + (summary?.total_output_tokens ?? 0)

  if (summary && runCount > 0) {
    return [
      {
        label: 'Cost / Success',
        value: formatCost(successfulRuns > 0 ? summary.total_cost / successfulRuns : 0),
        detail: `${successfulRuns} successful runs`,
        accent: ACCENT_COLORS[0],
      },
      {
        label: 'Tokens / Run',
        value: formatTokens(Math.round(totalTokens / runCount)),
        detail: `${runCount} runs in range`,
        accent: ACCENT_COLORS[1],
      },
      {
        label: 'Cache Savings',
        value: formatCost(summary.cache_savings_estimate),
        detail: `${formatTokens(summary.total_cached_input_tokens)} cached tokens`,
        accent: ACCENT_COLORS[2],
      },
      {
        label: 'Tools / Run',
        value: formatDecimal(summary.total_tool_calls / runCount),
        detail: `${summary.total_mcp_calls} MCP calls total`,
        accent: ACCENT_COLORS[3],
      },
    ]
  }

  const legacySessions = legacy?.month.sessions ?? 0
  const legacyTokens = legacy?.month.tokens ?? 0
  const legacyCost = legacy?.month.cost ?? 0
  return [
    {
      label: 'Cost / Session',
      value: formatCost(legacySessions > 0 ? legacyCost / legacySessions : 0),
      detail: `${legacySessions} sessions this month`,
      accent: ACCENT_COLORS[0],
    },
    {
      label: 'Tokens / Session',
      value: formatTokens(legacySessions > 0 ? Math.round(legacyTokens / legacySessions) : 0),
      detail: 'Legacy session average',
      accent: ACCENT_COLORS[1],
    },
    {
      label: 'Cache Savings',
      value: '$0.00',
      detail: 'Unavailable in legacy data',
      accent: ACCENT_COLORS[2],
    },
    {
      label: 'Tool Calls',
      value: (legacy?.month.tool_calls ?? 0).toLocaleString('en-US'),
      detail: `${legacy?.month.active_days ?? 0} active days`,
      accent: ACCENT_COLORS[3],
    },
  ]
})

/* ── Formatters ─────────────────────────────────────── */

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}K`
  return tokens.toLocaleString('en-US')
}

function formatCost(cost: number): string {
  if (cost < 0.01 && cost > 0) return '<$0.01'
  return `$${cost.toFixed(2)}`
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

function formatDuration(durationMs: number | null | undefined): string {
  if (!durationMs || durationMs <= 0) return '\u2014'
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`
  const totalSeconds = durationMs / 1000
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = Math.round(totalSeconds % 60)
  return `${minutes}m ${seconds}s`
}

function formatDecimal(value: number): string {
  return value.toFixed(value >= 10 ? 0 : 1)
}

function formatDateLabel(value: string): string {
  const date = new Date(value)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)

  if (date.toDateString() === today.toDateString()) {
    return `Today ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
  }
  if (date.toDateString() === yesterday.toDateString()) {
    return `Yest. ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
  }
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatStatus(status: string): string {
  if (status === 'completed') return 'OK'
  if (status === 'failed') return 'Fail'
  if (status === 'cancelled') return 'Cancel'
  return 'Running'
}

function statusClass(status: string): string {
  if (status === 'completed') return 'badge-ok'
  if (status === 'failed') return 'badge-fail'
  if (status === 'cancelled') return 'badge-cancel'
  return 'badge-running'
}

function errorRateClass(rate: number): string {
  if (rate > 0.25) return 'error-rate-high'
  if (rate > 0.1) return 'error-rate-warn'
  return ''
}

/* ── Data loading ───────────────────────────────────── */

function updateTimestamp() {
  lastUpdated.value = new Date().toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  })
}

async function refreshUsage() {
  await Promise.all([
    loadOverview(selectedRange.value),
    loadBreakdown(selectedRange.value, selectedBreakdown.value),
  ])
  updateTimestamp()
}

const refreshBreakdown = useDebounceFn(() => {
  void loadBreakdown(selectedRange.value, selectedBreakdown.value)
}, 120)

watch(selectedRange, () => {
  refreshUsage()
})
watch(selectedBreakdown, () => {
  refreshBreakdown()
})
onMounted(() => {
  refreshUsage()
})
</script>

<style scoped>
/* ── Root ───────────────────────────────────────────── */
.usage-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

/* ── Top Bar ────────────────────────────────────────── */
.dashboard-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.topbar-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.last-updated {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-light);
  background: var(--fill-tsp-white-main);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.refresh-btn:hover {
  border-color: var(--border-main);
  color: var(--text-primary);
  background: var(--fill-tsp-white-dark);
}

.refresh-btn:focus-visible {
  outline: 2px solid var(--text-brand);
  outline-offset: 2px;
}

.refresh-spinning svg {
  animation: spin 0.8s linear infinite;
}

/* ── Error & Fallback Banners ───────────────────────── */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(239, 68, 68, 0.2);
  background: var(--function-error-tsp, rgba(239, 68, 68, 0.05));
  color: var(--function-error, #ef4444);
  font-size: 13px;
  font-weight: 500;
}

.error-retry {
  margin-left: auto;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(239, 68, 68, 0.25);
  background: transparent;
  color: var(--function-error, #ef4444);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;
}

.error-retry:hover {
  background: rgba(239, 68, 68, 0.08);
}

.fallback-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px dashed rgba(59, 130, 246, 0.2);
  background: rgba(59, 130, 246, 0.03);
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* ── Segmented Controls ─────────────────────────────── */
.segment-group {
  display: inline-flex;
  gap: 2px;
  background: var(--fill-tsp-white-dark, rgba(17, 24, 39, 0.04));
  border-radius: 9px;
  padding: 3px;
  border: 1px solid var(--border-light);
}

.segment {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-tertiary);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.segment-sm {
  padding: 4px 10px;
  font-size: 11px;
}

.segment:hover {
  color: var(--text-secondary);
}

.segment:focus-visible {
  outline: 2px solid var(--text-brand);
  outline-offset: -1px;
  border-radius: 6px;
}

.segment-active {
  background: var(--background-white-main);
  color: var(--text-primary);
  font-weight: 600;
  border-color: var(--border-light);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}

/* ── KPI Hero Cards ─────────────────────────────────── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi-card {
  --tone-rgb: 148, 163, 184;
  position: relative;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: var(--fill-tsp-white-main);
  overflow: hidden;
  transition: all 0.2s ease;
}

.kpi-card:hover {
  border-color: var(--border-main);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
}

.tone-cost {
  --tone-rgb: 14, 165, 233;
}
.tone-runs {
  --tone-rgb: 34, 197, 94;
}
.tone-success {
  --tone-rgb: 16, 185, 129;
}
.tone-duration {
  --tone-rgb: 249, 115, 22;
}

.kpi-accent {
  height: 3px;
  width: 100%;
  background: linear-gradient(
    90deg,
    rgba(var(--tone-rgb), 0.85),
    rgba(var(--tone-rgb), 0.45)
  );
}

.kpi-body {
  padding: 14px 16px 16px;
}

.kpi-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kpi-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: rgba(var(--tone-rgb), 0.1);
  color: rgba(var(--tone-rgb), 1);
}

.kpi-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.kpi-value {
  margin-top: 12px;
  font-size: 26px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.kpi-detail {
  margin-top: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  line-height: 1.4;
}

.kpi-sub {
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* ── Skeleton ───────────────────────────────────────── */
.kpi-skeleton {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skeleton {
  display: block;
  border-radius: 6px;
  background: linear-gradient(
    90deg,
    var(--border-light) 0%,
    var(--background-surface, #f1f5f9) 50%,
    var(--border-light) 100%
  );
  background-size: 220% 100%;
  animation: skeleton-pulse 1.4s ease infinite;
}

.skeleton-lg {
  width: 70%;
  height: 26px;
}
.skeleton-sm {
  width: 55%;
  height: 12px;
}

/* ── Section Card ───────────────────────────────────── */
.section-card {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 20px;
  transition: border-color 0.2s ease;
}

.section-card:hover {
  border-color: var(--border-main);
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.section-header-wrap {
  flex-wrap: wrap;
  justify-content: space-between;
}

.section-header-left {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.section-actions {
  margin-left: auto;
  flex-shrink: 0;
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

.section-icon-blue {
  background: rgba(59, 130, 246, 0.08);
  color: #2563eb;
}
.section-icon-green {
  background: rgba(34, 197, 94, 0.08);
  color: #16a34a;
}
.section-icon-purple {
  background: rgba(139, 92, 246, 0.08);
  color: #7c3aed;
}
.section-icon-amber {
  background: rgba(245, 158, 11, 0.08);
  color: #d97706;
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
  margin: 0;
  line-height: 1.4;
}

.section-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.4;
}

/* ── Chart Shell ────────────────────────────────────── */
.chart-shell {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ── State Placeholders ─────────────────────────────── */
.state-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 160px;
  width: 100%;
  color: var(--text-tertiary);
  font-size: 13px;
}

.state-empty {
  padding: 24px;
}

.state-empty-sm {
  min-height: 120px;
}

.state-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-tertiary);
  opacity: 0.7;
}

/* ── Panel Grid ─────────────────────────────────────── */
.panel-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 14px;
}

/* ── Data Table ─────────────────────────────────────── */
.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  padding: 0 8px 10px;
  text-align: left;
  font-size: 10px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  white-space: nowrap;
}

.data-table td {
  padding: 10px 8px;
  border-top: 1px solid var(--border-light);
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.data-table tbody tr:first-child td {
  border-top-color: var(--border-main);
}

.table-row-hover {
  transition: background 0.12s ease;
}

.table-row-hover:hover td {
  background: rgba(59, 130, 246, 0.025);
}

.table-state {
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-tertiary);
  font-size: 12px;
  padding: 24px 0 !important;
}

.col-right {
  text-align: right;
}

.cell-mono {
  font-variant-numeric: tabular-nums;
}

.cell-muted {
  color: var(--text-tertiary);
}

.cell-truncate {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.breakdown-key {
  display: inline-block;
  padding: 2px 7px;
  background: var(--fill-tsp-white-dark, rgba(17, 24, 39, 0.04));
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  color: var(--text-secondary);
}

/* ── Status Badges ──────────────────────────────────── */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.badge-ok {
  background: var(--function-success-tsp, rgba(34, 197, 94, 0.08));
  color: #15803d;
}
.badge-ok .status-dot {
  background: var(--function-success, #22c55e);
}

.badge-fail {
  background: var(--function-error-tsp, rgba(239, 68, 68, 0.08));
  color: #b91c1c;
}
.badge-fail .status-dot {
  background: var(--function-error, #ef4444);
}

.badge-cancel {
  background: rgba(148, 163, 184, 0.08);
  color: #475569;
}
.badge-cancel .status-dot {
  background: #94a3b8;
}

.badge-running {
  background: rgba(59, 130, 246, 0.08);
  color: #1d4ed8;
}
.badge-running .status-dot {
  background: #3b82f6;
  animation: pulse-dot 1.5s ease infinite;
}

/* ── Error Rate Badges ──────────────────────────────── */
.error-rate {
  display: inline-flex;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--function-error-tsp, rgba(239, 68, 68, 0.06));
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.error-rate-warn {
  background: rgba(245, 158, 11, 0.08);
  color: #d97706;
}

.error-rate-high {
  background: var(--function-error-tsp, rgba(239, 68, 68, 0.08));
  color: var(--function-error, #dc2626);
}

/* ── Efficiency Grid ────────────────────────────────── */
.efficiency-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.eff-card {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--fill-tsp-white-dark, rgba(17, 24, 39, 0.02));
  border-left: 3px solid var(--accent, var(--border-main));
  transition: all 0.2s ease;
}

.eff-card:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-main);
  border-left-color: var(--accent, var(--border-main));
}

.eff-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
}

.eff-value {
  display: block;
  margin-top: 8px;
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

.eff-detail {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* ── Transitions ────────────────────────────────────── */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.2s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ── Animations ─────────────────────────────────────── */
@keyframes skeleton-pulse {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse-dot {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 1120px) {
  .kpi-grid,
  .efficiency-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .panel-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .kpi-grid,
  .efficiency-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-topbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .section-card {
    padding: 16px;
  }

  .section-header {
    flex-direction: column;
  }
}
</style>
