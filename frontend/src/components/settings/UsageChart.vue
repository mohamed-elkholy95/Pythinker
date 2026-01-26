<template>
  <div class="usage-chart">
    <div class="chart-container">
      <div class="chart-bars">
        <div
          v-for="(bar, index) in normalizedBars"
          :key="index"
          class="bar-column"
          :title="`${bar.label}: ${formatNumber(bar.value)} tokens ($${bar.cost.toFixed(4)})`"
        >
          <div
            class="bar"
            :style="{ height: `${bar.percentage}%` }"
            :class="{ 'bar-today': index === normalizedBars.length - 1 }"
          />
          <span class="bar-label">{{ bar.shortLabel }}</span>
        </div>
      </div>
      <div class="chart-y-axis">
        <span class="y-label">{{ formatNumber(maxValue) }}</span>
        <span class="y-label">{{ formatNumber(Math.round(maxValue / 2)) }}</span>
        <span class="y-label">0</span>
      </div>
    </div>
    <div class="chart-legend">
      <span class="legend-item">
        <span class="legend-dot" />
        Daily tokens
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface ChartData {
  date: string
  tokens: number
  cost: number
}

const props = defineProps<{
  data: ChartData[]
}>()

// Calculate max value for scaling
const maxValue = computed(() => {
  if (!props.data.length) return 1000
  const max = Math.max(...props.data.map(d => d.tokens))
  return max || 1000
})

// Normalize bars to percentages
const normalizedBars = computed(() => {
  return props.data.map(item => {
    const date = new Date(item.date)
    const dayNum = date.getDate()
    const monthShort = date.toLocaleString('en', { month: 'short' })

    return {
      label: `${monthShort} ${dayNum}`,
      shortLabel: dayNum.toString(),
      value: item.tokens,
      cost: item.cost,
      percentage: maxValue.value > 0 ? (item.tokens / maxValue.value) * 100 : 0
    }
  })
})

// Format large numbers
function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1)}M`
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}K`
  }
  return num.toString()
}
</script>

<style scoped>
.usage-chart {
  width: 100%;
  padding: 0.5rem;
}

.chart-container {
  display: flex;
  gap: 0.5rem;
  height: 120px;
}

.chart-bars {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 2px;
  padding-bottom: 20px;
  position: relative;
}

.bar-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
  cursor: pointer;
}

.bar {
  width: 100%;
  max-width: 20px;
  background: hsl(var(--primary) / 0.6);
  border-radius: 2px 2px 0 0;
  transition: background-color 0.2s, height 0.3s ease-out;
  min-height: 2px;
}

.bar:hover {
  background: hsl(var(--primary));
}

.bar-today {
  background: hsl(var(--primary));
}

.bar-label {
  font-size: 9px;
  color: hsl(var(--muted-foreground));
  margin-top: 4px;
  position: absolute;
  bottom: 0;
}

.chart-y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding-bottom: 20px;
  width: 40px;
  text-align: right;
}

.y-label {
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.chart-legend {
  display: flex;
  justify-content: center;
  gap: 1rem;
  margin-top: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: hsl(var(--primary) / 0.6);
}
</style>
