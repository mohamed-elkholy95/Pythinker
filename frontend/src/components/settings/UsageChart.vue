<template>
  <div class="usage-chart" :class="`usage-chart-${metric}`">
    <div class="chart-area">
      <div class="chart-grid">
        <div class="grid-line"></div>
        <div class="grid-line"></div>
        <div class="grid-line"></div>
      </div>

      <div class="chart-bars">
        <div
          v-for="(bar, index) in normalizedBars"
          :key="bar.date"
          class="bar-wrapper"
          @mouseenter="hoveredIndex = index"
          @mouseleave="hoveredIndex = null"
        >
          <Transition name="tooltip">
            <div v-if="hoveredIndex === index" class="bar-tooltip">
              <div class="tooltip-date">{{ bar.label }}</div>
              <div class="tooltip-value">{{ formatMetricValue(bar.value) }}</div>
              <div v-if="bar.detail" class="tooltip-detail">{{ bar.detail }}</div>
            </div>
          </Transition>

          <div class="bar-column">
            <div
              class="bar"
              :class="{
                'bar-today': index === normalizedBars.length - 1,
                'bar-hovered': hoveredIndex === index,
              }"
              :style="{
                height: `${bar.percentage}%`,
                animationDelay: `${index * 18}ms`,
              }"
            >
              <div class="bar-glow"></div>
            </div>
          </div>

          <span class="bar-label" :class="{ 'label-today': index === normalizedBars.length - 1 }">
            {{ bar.shortLabel }}
          </span>
        </div>
      </div>
    </div>

    <div class="chart-legend">
      <div class="legend-item">
        <span class="legend-dot"></span>
        <span class="legend-text">{{ legendText }}</span>
      </div>
      <div class="legend-item legend-today">
        <span class="legend-dot legend-dot-today"></span>
        <span class="legend-text">Latest</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

export type UsageChartMetric = 'cost' | 'runs' | 'tokens' | 'tools'

interface ChartData {
  date: string
  value: number
  detail?: string
}

const props = withDefaults(
  defineProps<{
    data: ChartData[]
    metric?: UsageChartMetric
    legendLabel?: string
  }>(),
  {
    metric: 'tokens',
    legendLabel: '',
  }
)

const hoveredIndex = ref<number | null>(null)

const legendText = computed(() => {
  if (props.legendLabel) {
    return props.legendLabel
  }

  return {
    cost: 'Estimated daily cost',
    runs: 'Daily agent runs',
    tokens: 'Daily token volume',
    tools: 'Daily tool activity',
  }[props.metric]
})

const maxValue = computed(() => {
  if (!props.data.length) {
    return 1
  }

  const max = Math.max(...props.data.map(item => item.value), 1)
  const magnitude = Math.pow(10, Math.max(0, Math.floor(Math.log10(max))))
  return Math.ceil(max / magnitude) * magnitude
})

const normalizedBars = computed(() => {
  return props.data.map(item => {
    const date = new Date(item.date)
    const dayNum = date.getDate()
    const monthShort = date.toLocaleString('en-US', { month: 'short' })

    return {
      date: item.date,
      label: `${monthShort} ${dayNum}`,
      shortLabel: dayNum.toString(),
      value: item.value,
      detail: item.detail ?? '',
      percentage: maxValue.value > 0 ? Math.max((item.value / maxValue.value) * 100, 4) : 4,
    }
  })
})

function formatMetricValue(value: number): string {
  if (props.metric === 'cost') {
    if (value < 0.01 && value > 0) {
      return '<$0.01'
    }
    return `$${value.toFixed(2)}`
  }

  if (props.metric === 'runs' || props.metric === 'tools') {
    return value.toLocaleString('en-US')
  }

  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`
  }
  return value.toString()
}
</script>

<style scoped>
.usage-chart {
  --usage-bar-start: rgba(14, 165, 233, 0.75);
  --usage-bar-end: rgba(14, 165, 233, 0.45);
  --usage-bar-today: rgba(2, 132, 199, 0.95);
  --usage-glow: rgba(14, 165, 233, 0.3);
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
}

.usage-chart-runs {
  --usage-bar-start: rgba(34, 197, 94, 0.75);
  --usage-bar-end: rgba(34, 197, 94, 0.45);
  --usage-bar-today: rgba(22, 163, 74, 0.95);
  --usage-glow: rgba(34, 197, 94, 0.28);
}

.usage-chart-tokens {
  --usage-bar-start: rgba(59, 130, 246, 0.78);
  --usage-bar-end: rgba(59, 130, 246, 0.45);
  --usage-bar-today: rgba(37, 99, 235, 0.95);
  --usage-glow: rgba(59, 130, 246, 0.28);
}

.usage-chart-tools {
  --usage-bar-start: rgba(249, 115, 22, 0.78);
  --usage-bar-end: rgba(249, 115, 22, 0.44);
  --usage-bar-today: rgba(234, 88, 12, 0.95);
  --usage-glow: rgba(249, 115, 22, 0.28);
}

.chart-area {
  position: relative;
  height: 164px;
}

.chart-grid {
  position: absolute;
  inset: 0;
  bottom: 24px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  pointer-events: none;
}

.grid-line {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, var(--border-main) 50%, transparent 100%);
  opacity: 0.6;
}

.chart-bars {
  position: relative;
  height: calc(100% - 24px);
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding: 0 2px;
}

.bar-wrapper {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}

.bar-column {
  width: 100%;
  max-width: 28px;
  flex: 1;
  display: flex;
  align-items: flex-end;
}

.bar {
  width: 100%;
  border-radius: 10px 10px 0 0;
  background: linear-gradient(180deg, var(--usage-bar-start) 0%, var(--usage-bar-end) 100%);
  position: relative;
  overflow: hidden;
  transform-origin: bottom;
  transform: scaleY(0);
  animation: bar-grow 0.45s ease-out forwards;
  transition: filter 0.18s ease;
}

.bar-glow {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.18) 0%, transparent 56%);
  opacity: 0;
  transition: opacity 0.18s ease;
}

.bar-hovered,
.bar:hover {
  filter: saturate(1.08) brightness(1.04);
}

.bar-hovered .bar-glow,
.bar:hover .bar-glow {
  opacity: 1;
}

.bar-today {
  background: linear-gradient(180deg, var(--usage-bar-today) 0%, var(--usage-bar-end) 100%);
  box-shadow: 0 0 14px var(--usage-glow);
}

.bar-label {
  margin-top: 8px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
}

.label-today {
  color: var(--text-primary);
}

.bar-tooltip {
  position: absolute;
  left: 50%;
  bottom: calc(100% + 10px);
  transform: translateX(-50%);
  min-width: 112px;
  padding: 9px 12px;
  border-radius: 10px;
  background: var(--Tooltips-main);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.15);
  pointer-events: none;
  z-index: 10;
}

.bar-tooltip::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 100%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: var(--Tooltips-main);
}

.tooltip-date {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.88);
}

.tooltip-value {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}

.tooltip-detail {
  margin-top: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.72);
}

.chart-legend {
  display: flex;
  justify-content: center;
  gap: 22px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, var(--usage-bar-start) 0%, var(--usage-bar-end) 100%);
}

.legend-dot-today {
  background: var(--usage-bar-today);
  box-shadow: 0 0 8px var(--usage-glow);
}

.legend-text {
  font-size: 11px;
  color: var(--text-tertiary);
}

.tooltip-enter-active,
.tooltip-leave-active {
  transition: all 0.16s ease;
}

.tooltip-enter-from,
.tooltip-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

@keyframes bar-grow {
  to {
    transform: scaleY(1);
  }
}
</style>
