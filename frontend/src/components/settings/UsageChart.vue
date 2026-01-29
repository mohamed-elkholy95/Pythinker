<template>
  <div class="usage-chart">
    <!-- Y-Axis Labels -->
    <div class="chart-y-axis">
      <span class="y-label">{{ formatNumber(maxValue) }}</span>
      <span class="y-label">{{ formatNumber(Math.round(maxValue / 2)) }}</span>
      <span class="y-label">0</span>
    </div>

    <!-- Chart Area -->
    <div class="chart-area">
      <!-- Grid Lines -->
      <div class="chart-grid">
        <div class="grid-line"></div>
        <div class="grid-line"></div>
        <div class="grid-line"></div>
      </div>

      <!-- Bars Container -->
      <div class="chart-bars">
        <div
          v-for="(bar, index) in normalizedBars"
          :key="index"
          class="bar-wrapper"
          @mouseenter="hoveredIndex = index"
          @mouseleave="hoveredIndex = null"
        >
          <!-- Tooltip -->
          <Transition name="tooltip">
            <div v-if="hoveredIndex === index" class="bar-tooltip">
              <div class="tooltip-date">{{ bar.label }}</div>
              <div class="tooltip-stats">
                <span class="tooltip-tokens">{{ formatNumber(bar.value) }} tokens</span>
                <span class="tooltip-cost">${{ bar.cost.toFixed(4) }}</span>
              </div>
            </div>
          </Transition>

          <!-- Bar -->
          <div class="bar-column">
            <div
              class="bar"
              :class="{
                'bar-today': index === normalizedBars.length - 1,
                'bar-hovered': hoveredIndex === index
              }"
              :style="{
                height: `${bar.percentage}%`,
                animationDelay: `${index * 20}ms`
              }"
            >
              <div class="bar-glow"></div>
            </div>
          </div>

          <!-- X-Axis Label -->
          <span
            class="bar-label"
            :class="{ 'label-today': index === normalizedBars.length - 1 }"
          >
            {{ bar.shortLabel }}
          </span>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="chart-legend">
      <div class="legend-item">
        <span class="legend-dot"></span>
        <span class="legend-text">Daily token usage</span>
      </div>
      <div class="legend-item legend-today">
        <span class="legend-dot legend-dot-today"></span>
        <span class="legend-text">Today</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface ChartData {
  date: string
  tokens: number
  cost: number
}

const props = defineProps<{
  data: ChartData[]
}>()

const hoveredIndex = ref<number | null>(null)

// Calculate max value for scaling
const maxValue = computed(() => {
  if (!props.data.length) return 1000
  const max = Math.max(...props.data.map(d => d.tokens))
  // Round up to a nice number
  const magnitude = Math.pow(10, Math.floor(Math.log10(max || 1000)))
  return Math.ceil((max || 1000) / magnitude) * magnitude
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
      percentage: maxValue.value > 0 ? Math.max((item.tokens / maxValue.value) * 100, 2) : 2
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
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  padding: 8px 0;
}

.chart-y-axis {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 24px;
  width: 40px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 4px 0;
  pointer-events: none;
}

.y-label {
  font-size: 10px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-align: right;
  padding-right: 8px;
  font-variant-numeric: tabular-nums;
}

.chart-area {
  position: relative;
  height: 140px;
  margin-left: 44px;
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
  background: linear-gradient(
    90deg,
    var(--border-light) 0%,
    var(--border-main) 50%,
    var(--border-light) 100%
  );
  opacity: 0.5;
}

.chart-bars {
  position: relative;
  height: calc(100% - 24px);
  display: flex;
  align-items: flex-end;
  gap: 4px;
  padding: 0 4px;
}

.bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  position: relative;
  cursor: pointer;
}

.bar-column {
  flex: 1;
  display: flex;
  align-items: flex-end;
  width: 100%;
  max-width: 24px;
}

.bar {
  width: 100%;
  background: linear-gradient(
    180deg,
    rgba(59, 130, 246, 0.6) 0%,
    rgba(59, 130, 246, 0.4) 100%
  );
  border-radius: 4px 4px 0 0;
  position: relative;
  overflow: hidden;
  animation: barGrow 0.5s ease-out forwards;
  transform-origin: bottom;
  transform: scaleY(0);
  transition: all 0.2s ease;
}

@keyframes barGrow {
  to {
    transform: scaleY(1);
  }
}

.bar-glow {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.2) 0%,
    transparent 50%
  );
  opacity: 0;
  transition: opacity 0.2s ease;
}

.bar:hover .bar-glow,
.bar-hovered .bar-glow {
  opacity: 1;
}

.bar:hover,
.bar-hovered {
  background: linear-gradient(
    180deg,
    rgba(59, 130, 246, 0.8) 0%,
    rgba(59, 130, 246, 0.6) 100%
  );
}

.bar-today {
  background: linear-gradient(
    180deg,
    var(--text-brand) 0%,
    rgba(59, 130, 246, 0.7) 100%
  );
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.3);
}

.bar-today:hover,
.bar-today.bar-hovered {
  background: linear-gradient(
    180deg,
    var(--text-brand) 0%,
    rgba(59, 130, 246, 0.85) 100%
  );
  box-shadow: 0 0 16px rgba(59, 130, 246, 0.4);
}

.bar-label {
  margin-top: 6px;
  font-size: 10px;
  font-weight: 500;
  color: var(--text-tertiary);
  transition: color 0.2s ease;
}

.label-today {
  color: var(--text-brand);
  font-weight: 600;
}

/* Tooltip */
.bar-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--Tooltips-main);
  border-radius: 8px;
  padding: 8px 12px;
  white-space: nowrap;
  z-index: 10;
  pointer-events: none;
}

.bar-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: var(--Tooltips-main);
}

.tooltip-date {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  margin-bottom: 4px;
}

.tooltip-stats {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tooltip-tokens {
  font-size: 12px;
  font-weight: 500;
  color: #fff;
}

.tooltip-cost {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
}

/* Tooltip Transition */
.tooltip-enter-active,
.tooltip-leave-active {
  transition: all 0.15s ease;
}

.tooltip-enter-from,
.tooltip-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

/* Legend */
.chart-legend {
  display: flex;
  justify-content: center;
  gap: 20px;
  padding-top: 4px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: linear-gradient(
    180deg,
    rgba(59, 130, 246, 0.6) 0%,
    rgba(59, 130, 246, 0.4) 100%
  );
}

.legend-dot-today {
  background: var(--text-brand);
  box-shadow: 0 0 6px rgba(59, 130, 246, 0.4);
}

.legend-text {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
}
</style>
