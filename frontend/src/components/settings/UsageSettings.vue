<template>
  <div class="usage-settings">
    <!-- Hero Stats Section -->
    <div class="hero-stats">
      <!-- Today's Usage Card -->
      <div class="stat-card stat-card-primary" :style="{ animationDelay: '0ms' }">
        <div class="stat-card-glow"></div>
        <div class="stat-card-content">
          <div class="stat-header">
            <div class="stat-icon-wrapper stat-icon-today">
              <Zap class="w-5 h-5" />
            </div>
            <span class="stat-label">Today</span>
          </div>
          <div v-if="loading" class="stat-skeleton">
            <div class="skeleton-line skeleton-lg"></div>
            <div class="skeleton-line skeleton-sm"></div>
          </div>
          <div v-else class="stat-value-group">
            <div class="stat-value">{{ formatTokens(summary?.today.tokens || 0) }}</div>
            <div class="stat-meta">
              <span class="stat-cost">{{ formatCost(summary?.today.cost || 0) }}</span>
              <span class="stat-separator"></span>
              <span class="stat-calls">{{ summary?.today.llm_calls || 0 }} calls</span>
            </div>
          </div>
        </div>
        <div class="stat-card-shine"></div>
      </div>

      <!-- This Month's Usage Card -->
      <div class="stat-card stat-card-secondary" :style="{ animationDelay: '100ms' }">
        <div class="stat-card-content">
          <div class="stat-header">
            <div class="stat-icon-wrapper stat-icon-month">
              <TrendingUp class="w-5 h-5" />
            </div>
            <span class="stat-label">This Month</span>
          </div>
          <div v-if="loading" class="stat-skeleton">
            <div class="skeleton-line skeleton-lg"></div>
            <div class="skeleton-line skeleton-sm"></div>
          </div>
          <div v-else class="stat-value-group">
            <div class="stat-value">{{ formatTokens(summary?.month.tokens || 0) }}</div>
            <div class="stat-meta">
              <span class="stat-cost">{{ formatCost(summary?.month.cost || 0) }}</span>
              <span class="stat-separator"></span>
              <span class="stat-calls">{{ summary?.month.sessions || 0 }} sessions</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Activity Metrics -->
    <div class="metrics-row">
      <div
        v-for="(metric, index) in activityMetrics"
        :key="metric.label"
        class="metric-card"
        :style="{ animationDelay: `${200 + index * 50}ms` }"
      >
        <div class="metric-icon-wrapper" :class="metric.iconClass">
          <component :is="metric.icon" class="w-4 h-4" />
        </div>
        <div class="metric-content">
          <span class="metric-value">{{ metric.value }}</span>
          <span class="metric-label">{{ metric.label }}</span>
        </div>
      </div>
    </div>

    <!-- Chart Section -->
    <div class="chart-section" :style="{ animationDelay: '350ms' }">
      <div class="section-header">
        <div class="section-title-group">
          <BarChart3 class="w-4 h-4 text-[var(--text-tertiary)]" />
          <span class="section-title">Daily Usage</span>
        </div>
        <div class="period-selector">
          <button
            v-for="period in periods"
            :key="period.days"
            @click="selectedPeriod = period.days"
            class="period-btn"
            :class="{ 'period-btn-active': selectedPeriod === period.days }"
          >
            {{ period.label }}
          </button>
        </div>
      </div>

      <div class="chart-container">
        <UsageChart
          v-if="!loadingDaily && chartData.length"
          :data="chartData"
        />
        <div v-else-if="loadingDaily" class="chart-loading">
          <div class="chart-loading-spinner">
            <Loader2 class="w-6 h-6 animate-spin" />
          </div>
          <span class="chart-loading-text">Loading usage data...</span>
        </div>
        <div v-else class="chart-empty">
          <div class="chart-empty-icon">
            <BarChart3 class="w-8 h-8" />
          </div>
          <span class="chart-empty-text">No usage data yet</span>
          <span class="chart-empty-hint">Start using the AI to see your activity here</span>
        </div>
      </div>
    </div>

    <!-- Recent Activity Table -->
    <div class="activity-section" :style="{ animationDelay: '450ms' }">
      <div class="section-header">
        <div class="section-title-group">
          <Clock class="w-4 h-4 text-[var(--text-tertiary)]" />
          <span class="section-title">Recent Activity</span>
        </div>
      </div>

      <div class="activity-table-wrapper">
        <table class="activity-table">
          <thead>
            <tr>
              <th class="th-date">Date</th>
              <th class="th-tokens">Tokens</th>
              <th class="th-cost">Cost</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loadingDaily" class="loading-row">
              <td colspan="3">
                <div class="table-loading">
                  <Loader2 class="w-4 h-4 animate-spin" />
                  <span>Loading...</span>
                </div>
              </td>
            </tr>
            <tr v-else-if="!dailyUsage.length" class="empty-row">
              <td colspan="3">
                <span class="table-empty">No activity recorded</span>
              </td>
            </tr>
            <tr
              v-for="(day, index) in dailyUsage.slice(0, 7)"
              :key="day.date"
              class="activity-row"
              :style="{ animationDelay: `${500 + index * 30}ms` }"
            >
              <td class="td-date">
                <span class="date-badge" :class="{ 'date-today': isToday(day.date) }">
                  {{ formatDate(day.date) }}
                </span>
              </td>
              <td class="td-tokens">
                <span class="tokens-value">
                  {{ formatTokens(day.total_prompt_tokens + day.total_completion_tokens) }}
                </span>
              </td>
              <td class="td-cost">
                <span class="cost-value">{{ formatCost(day.total_cost) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  Zap,
  TrendingUp,
  Cpu,
  Wrench,
  CalendarCheck,
  BarChart3,
  Clock,
  Loader2
} from 'lucide-vue-next'
import UsageChart from './UsageChart.vue'
import {
  getUsageSummary,
  getDailyUsage,
  type UsageSummary,
  type DailyUsage
} from '@/api/usage'

// State
const loading = ref(true)
const loadingDaily = ref(true)
const summary = ref<UsageSummary | null>(null)
const dailyUsage = ref<DailyUsage[]>([])
const selectedPeriod = ref(30)

// Period options
const periods = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 }
]

// Activity metrics computed
const activityMetrics = computed(() => [
  {
    label: 'LLM Calls',
    value: summary.value?.month.llm_calls || 0,
    icon: Cpu,
    iconClass: 'metric-icon-llm'
  },
  {
    label: 'Tool Calls',
    value: summary.value?.month.tool_calls || 0,
    icon: Wrench,
    iconClass: 'metric-icon-tool'
  },
  {
    label: 'Active Days',
    value: summary.value?.month.active_days || 0,
    icon: CalendarCheck,
    iconClass: 'metric-icon-days'
  }
])

// Chart data transformation
const chartData = computed(() => {
  return dailyUsage.value.map(day => ({
    date: day.date,
    tokens: day.total_prompt_tokens + day.total_completion_tokens,
    cost: day.total_cost
  }))
})

// Format tokens for display
function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`
  }
  if (tokens >= 1_000) {
    return `${(tokens / 1_000).toFixed(1)}K`
  }
  return tokens.toString()
}

// Format cost for display
function formatCost(cost: number): string {
  if (cost < 0.01 && cost > 0) {
    return `<$0.01`
  }
  return `$${cost.toFixed(2)}`
}

// Check if date is today
function isToday(dateStr: string): boolean {
  const date = new Date(dateStr)
  const today = new Date()
  return date.toDateString() === today.toDateString()
}

// Format date for table
function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  if (date.toDateString() === today.toDateString()) {
    return 'Today'
  }
  if (date.toDateString() === yesterday.toDateString()) {
    return 'Yesterday'
  }
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// Fetch summary data
async function fetchSummary() {
  try {
    loading.value = true
    summary.value = await getUsageSummary()
  } catch (error) {
    console.error('Failed to fetch usage summary:', error)
  } finally {
    loading.value = false
  }
}

// Fetch daily data
async function fetchDailyUsage() {
  try {
    loadingDaily.value = true
    const result = await getDailyUsage(selectedPeriod.value)
    dailyUsage.value = result.days.reverse() // Most recent last for chart
  } catch (error) {
    console.error('Failed to fetch daily usage:', error)
    dailyUsage.value = []
  } finally {
    loadingDaily.value = false
  }
}

// Watch period changes
watch(selectedPeriod, () => {
  fetchDailyUsage()
})

// Initial fetch
onMounted(() => {
  fetchSummary()
  fetchDailyUsage()
})
</script>

<style scoped>
.usage-settings {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
}

/* Hero Stats */
.hero-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.stat-card {
  position: relative;
  border-radius: 16px;
  padding: 20px;
  overflow: hidden;
  animation: fadeSlideUp 0.4s ease-out forwards;
  opacity: 0;
  transform: translateY(12px);
}

@keyframes fadeSlideUp {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.stat-card-primary {
  background: linear-gradient(
    135deg,
    var(--fill-blue) 0%,
    rgba(59, 130, 246, 0.05) 100%
  );
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.stat-card-glow {
  position: absolute;
  top: -50%;
  right: -30%;
  width: 80%;
  height: 150%;
  background: radial-gradient(
    ellipse at center,
    rgba(59, 130, 246, 0.15) 0%,
    transparent 70%
  );
  pointer-events: none;
}

.stat-card-shine {
  position: absolute;
  top: 0;
  left: -100%;
  width: 50%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.1) 50%,
    transparent 100%
  );
  animation: shine 3s ease-in-out infinite;
  pointer-events: none;
}

@keyframes shine {
  0%, 100% {
    left: -100%;
  }
  50% {
    left: 150%;
  }
}

.stat-card-secondary {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-main);
}

.stat-card-content {
  position: relative;
  z-index: 1;
}

.stat-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.stat-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
}

.stat-icon-today {
  background: rgba(59, 130, 246, 0.15);
  color: var(--text-brand);
}

.stat-icon-month {
  background: var(--fill-tsp-white-dark);
  color: var(--icon-secondary);
}

.stat-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.stat-skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-line {
  background: linear-gradient(
    90deg,
    var(--fill-tsp-white-main) 0%,
    var(--fill-tsp-white-dark) 50%,
    var(--fill-tsp-white-main) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  border-radius: 6px;
}

.skeleton-lg {
  height: 32px;
  width: 80px;
}

.skeleton-sm {
  height: 16px;
  width: 120px;
}

@keyframes skeleton-pulse {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.stat-value-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.stat-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.stat-cost {
  font-weight: 600;
  color: var(--text-secondary);
}

.stat-separator {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--text-tertiary);
}

/* Metrics Row */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.metric-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  animation: fadeSlideUp 0.4s ease-out forwards;
  opacity: 0;
  transform: translateY(12px);
  transition: all 0.2s ease;
}

.metric-card:hover {
  background: var(--fill-tsp-white-dark);
  border-color: var(--border-main);
}

.metric-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  flex-shrink: 0;
}

.metric-icon-llm {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
}

.metric-icon-tool {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.metric-icon-days {
  background: rgba(251, 146, 60, 0.1);
  color: #fb923c;
}

.metric-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.metric-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

/* Chart Section */
.chart-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: fadeSlideUp 0.4s ease-out forwards;
  opacity: 0;
  transform: translateY(12px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.period-selector {
  display: flex;
  background: var(--fill-tsp-white-main);
  border-radius: 8px;
  padding: 3px;
  gap: 2px;
}

.period-btn {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.period-btn:hover {
  color: var(--text-secondary);
}

.period-btn-active {
  background: var(--background-white-main);
  color: var(--text-primary);
  box-shadow: 0 1px 3px var(--shadow-XS);
}

.chart-container {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 16px;
  min-height: 180px;
}

.chart-loading,
.chart-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 160px;
  gap: 12px;
}

.chart-loading-spinner {
  color: var(--text-tertiary);
}

.chart-loading-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

.chart-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  background: var(--fill-tsp-white-dark);
  border-radius: 12px;
  color: var(--icon-tertiary);
}

.chart-empty-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.chart-empty-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* Activity Section */
.activity-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: fadeSlideUp 0.4s ease-out forwards;
  opacity: 0;
  transform: translateY(12px);
}

.activity-table-wrapper {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  overflow: hidden;
}

.activity-table {
  width: 100%;
  border-collapse: collapse;
}

.activity-table th {
  padding: 12px 16px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--fill-tsp-white-light);
  border-bottom: 1px solid var(--border-light);
}

.th-date {
  text-align: left;
}

.th-tokens,
.th-cost {
  text-align: right;
}

.activity-row {
  animation: fadeSlideUp 0.3s ease-out forwards;
  opacity: 0;
  transform: translateY(8px);
  transition: background 0.15s ease;
}

.activity-row:hover {
  background: var(--fill-tsp-white-light);
}

.activity-row:not(:last-child) {
  border-bottom: 1px solid var(--border-light);
}

.activity-table td {
  padding: 14px 16px;
}

.td-date {
  text-align: left;
}

.td-tokens,
.td-cost {
  text-align: right;
}

.date-badge {
  display: inline-flex;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--fill-tsp-white-dark);
  border-radius: 6px;
}

.date-today {
  background: var(--fill-blue);
  color: var(--text-brand);
}

.tokens-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.cost-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.loading-row td,
.empty-row td {
  padding: 32px 16px;
  text-align: center;
}

.table-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.table-empty {
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>
