<template>
  <div class="space-y-6">
    <!-- Summary Cards -->
    <div class="grid grid-cols-2 gap-4">
      <!-- Today's Usage -->
      <div class="rounded-lg border bg-card p-4">
        <div class="flex items-center gap-2 mb-3">
          <Calendar class="h-4 w-4 text-muted-foreground" />
          <span class="text-sm font-medium">Today</span>
        </div>
        <div v-if="loading" class="animate-pulse space-y-2">
          <div class="h-6 bg-muted rounded w-20" />
          <div class="h-4 bg-muted rounded w-16" />
        </div>
        <div v-else>
          <div class="text-2xl font-bold">{{ formatTokens(summary?.today.tokens || 0) }}</div>
          <div class="text-xs text-muted-foreground">
            {{ formatCost(summary?.today.cost || 0) }} &bull;
            {{ summary?.today.llm_calls || 0 }} calls
          </div>
        </div>
      </div>

      <!-- This Month's Usage -->
      <div class="rounded-lg border bg-card p-4">
        <div class="flex items-center gap-2 mb-3">
          <CalendarDays class="h-4 w-4 text-muted-foreground" />
          <span class="text-sm font-medium">This Month</span>
        </div>
        <div v-if="loading" class="animate-pulse space-y-2">
          <div class="h-6 bg-muted rounded w-20" />
          <div class="h-4 bg-muted rounded w-16" />
        </div>
        <div v-else>
          <div class="text-2xl font-bold">{{ formatTokens(summary?.month.tokens || 0) }}</div>
          <div class="text-xs text-muted-foreground">
            {{ formatCost(summary?.month.cost || 0) }} &bull;
            {{ summary?.month.sessions || 0 }} sessions
          </div>
        </div>
      </div>
    </div>

    <!-- Activity Stats Row -->
    <div class="grid grid-cols-3 gap-3">
      <div class="rounded-lg border bg-card p-3 text-center">
        <div class="text-lg font-semibold">{{ summary?.month.llm_calls || 0 }}</div>
        <div class="text-xs text-muted-foreground">LLM Calls</div>
      </div>
      <div class="rounded-lg border bg-card p-3 text-center">
        <div class="text-lg font-semibold">{{ summary?.month.tool_calls || 0 }}</div>
        <div class="text-xs text-muted-foreground">Tool Calls</div>
      </div>
      <div class="rounded-lg border bg-card p-3 text-center">
        <div class="text-lg font-semibold">{{ summary?.month.active_days || 0 }}</div>
        <div class="text-xs text-muted-foreground">Active Days</div>
      </div>
    </div>

    <!-- Period Selector and Chart -->
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <span class="text-sm font-medium">Daily Usage</span>
        <div class="flex gap-1">
          <button
            v-for="period in periods"
            :key="period.days"
            @click="selectedPeriod = period.days"
            class="px-2 py-1 text-xs rounded-md transition-colors"
            :class="selectedPeriod === period.days
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted hover:bg-muted/80'"
          >
            {{ period.label }}
          </button>
        </div>
      </div>

      <div class="rounded-lg border bg-card p-3">
        <UsageChart
          v-if="!loadingDaily && chartData.length"
          :data="chartData"
        />
        <div v-else-if="loadingDaily" class="h-[140px] flex items-center justify-center">
          <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
        <div v-else class="h-[140px] flex items-center justify-center text-muted-foreground text-sm">
          No usage data yet
        </div>
      </div>
    </div>

    <!-- Daily Breakdown Table -->
    <div class="space-y-2">
      <span class="text-sm font-medium">Recent Activity</span>
      <div class="rounded-lg border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-muted/50">
            <tr>
              <th class="text-left p-2 font-medium">Date</th>
              <th class="text-right p-2 font-medium">Tokens</th>
              <th class="text-right p-2 font-medium">Cost</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loadingDaily">
              <td colspan="3" class="p-4 text-center text-muted-foreground">
                <Loader2 class="h-4 w-4 animate-spin mx-auto" />
              </td>
            </tr>
            <tr v-else-if="!dailyUsage.length">
              <td colspan="3" class="p-4 text-center text-muted-foreground">
                No usage data
              </td>
            </tr>
            <tr
              v-for="day in dailyUsage.slice(0, 7)"
              :key="day.date"
              class="border-t hover:bg-muted/30"
            >
              <td class="p-2">{{ formatDate(day.date) }}</td>
              <td class="p-2 text-right font-mono text-xs">
                {{ formatTokens(day.total_prompt_tokens + day.total_completion_tokens) }}
              </td>
              <td class="p-2 text-right font-mono text-xs">
                {{ formatCost(day.total_cost) }}
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
import { Calendar, CalendarDays, Loader2 } from 'lucide-vue-next'
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
