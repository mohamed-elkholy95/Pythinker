<template>
  <div class="wide-research-mini" :class="{ completed: isCompleted, searching: isSearching }">
    <!-- Animated background -->
    <div class="mini-atmosphere">
      <div class="mini-grid"></div>
      <div class="mini-sweep" :style="{ '--progress': progressPercent + '%' }"></div>
    </div>

    <!-- Main content -->
    <div class="mini-content">
      <!-- Status indicator with icon -->
      <div class="mini-header">
        <div class="status-icon" :class="statusClass">
          <svg v-if="isSearching" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <svg v-else-if="isAggregating" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 3v18M3 12h18"/>
          </svg>
          <svg v-else-if="isCompleted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 6v6l4 2"/>
          </svg>
        </div>
        <span class="status-label">{{ statusLabel }}</span>
      </div>

      <!-- Compact progress ring -->
      <div class="mini-progress">
        <svg class="progress-ring" viewBox="0 0 36 36">
          <circle
            class="ring-bg"
            cx="18"
            cy="18"
            r="15"
            fill="none"
            stroke-width="3"
          />
          <circle
            class="ring-fill"
            cx="18"
            cy="18"
            r="15"
            fill="none"
            stroke-width="3"
            :stroke-dasharray="circumference"
            :stroke-dashoffset="progressOffset"
            stroke-linecap="round"
          />
        </svg>
        <div class="progress-center">
          <span class="progress-value">{{ completedQueries }}</span>
          <span class="progress-sep">/</span>
          <span class="progress-total">{{ totalQueries }}</span>
        </div>
      </div>

      <!-- Sources found counter -->
      <div class="mini-sources">
        <div class="sources-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          </svg>
        </div>
        <span class="sources-value">{{ sourcesFound }}</span>
      </div>

      <!-- Active streams indicators -->
      <div class="mini-streams">
        <div
          v-for="(stream, idx) in visibleStreams"
          :key="idx"
          class="stream-dot"
          :class="stream.status"
          :style="{ '--hue': stream.hue }"
          :title="stream.label"
        ></div>
      </div>
    </div>

    <!-- Activity indicator -->
    <div v-if="isActive" class="activity-indicator"></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WideResearchMiniState } from '@/types/message'

interface StreamDot {
  label: string
  status: 'pending' | 'active' | 'done'
  hue: number
}

const props = withDefaults(defineProps<{
  state: WideResearchMiniState | null
  isActive?: boolean
}>(), {
  state: null,
  isActive: false
})

// Computed state
const isSearching = computed(() => props.state?.status === 'searching')
const isAggregating = computed(() => props.state?.status === 'aggregating')
const isCompleted = computed(() => props.state?.status === 'completed')
const totalQueries = computed(() => props.state?.total_queries || 0)
const completedQueries = computed(() => props.state?.completed_queries || 0)
const sourcesFound = computed(() => props.state?.sources_found || 0)

const progressPercent = computed(() => {
  if (!props.state || totalQueries.value === 0) return 0
  if (isCompleted.value) return 100
  return Math.round((completedQueries.value / totalQueries.value) * 100)
})

const circumference = 2 * Math.PI * 15
const progressOffset = computed(() => {
  return circumference - (progressPercent.value / 100) * circumference
})

const statusLabel = computed(() => {
  switch (props.state?.status) {
    case 'pending': return 'Preparing'
    case 'searching': return 'Researching'
    case 'aggregating': return 'Analyzing'
    case 'completed': return 'Complete'
    case 'failed': return 'Failed'
    default: return 'Research'
  }
})

const statusClass = computed(() => props.state?.status || 'pending')

// Generate stream dots from search types
const visibleStreams = computed((): StreamDot[] => {
  const types = props.state?.search_types || []
  const hues = [200, 280, 340, 160, 40, 320]

  return types.slice(0, 4).map((type, idx) => ({
    label: getTypeLabel(type),
    status: getStreamDotStatus(),
    hue: hues[idx % hues.length]
  }))
})

function getTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    info: 'General',
    news: 'News',
    academic: 'Academic',
    api: 'APIs',
    data: 'Data',
    tool: 'Tools'
  }
  return labels[type] || type
}

function getStreamDotStatus(): 'pending' | 'active' | 'done' {
  if (!props.state) return 'pending'
  if (isCompleted.value) return 'done'
  if (isSearching.value) return 'active'
  return 'pending'
}
</script>

<style scoped>
.wide-research-mini {
  --mini-primary: #00d4ff;
  --mini-secondary: #7c3aed;
  --mini-accent: #10b981;
  --mini-bg: rgba(10, 15, 30, 0.98);

  position: absolute;
  inset: 0;
  background: var(--mini-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

/* ===== Atmosphere ===== */
.mini-atmosphere {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.mini-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 212, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 212, 255, 0.04) 1px, transparent 1px);
  background-size: 12px 12px;
  opacity: 0.5;
}

.mini-sweep {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    transparent 0%,
    rgba(0, 212, 255, 0.08) calc(var(--progress) - 10%),
    rgba(0, 212, 255, 0.2) var(--progress),
    transparent calc(var(--progress) + 5%)
  );
}

/* ===== Content ===== */
.mini-content {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px;
  z-index: 1;
}

/* ===== Header ===== */
.mini-header {
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-icon {
  width: 12px;
  height: 12px;
  color: var(--mini-primary);
}

.status-icon.searching svg {
  animation: search-pulse 1.5s ease-in-out infinite;
}

.status-icon.aggregating svg {
  color: var(--mini-secondary);
  animation: spin 2s linear infinite;
}

.status-icon.completed svg {
  color: var(--mini-accent);
}

@keyframes search-pulse {
  0%, 100% { opacity: 0.6; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.1); }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.status-label {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 7px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(255, 255, 255, 0.7);
}

/* ===== Progress Ring ===== */
.mini-progress {
  position: relative;
  width: 36px;
  height: 36px;
}

.progress-ring {
  transform: rotate(-90deg);
}

.ring-bg {
  stroke: rgba(255, 255, 255, 0.1);
}

.ring-fill {
  stroke: var(--mini-primary);
  transition: stroke-dashoffset 0.4s ease;
  filter: drop-shadow(0 0 4px rgba(0, 212, 255, 0.5));
}

.wide-research-mini.completed .ring-fill {
  stroke: var(--mini-accent);
  filter: drop-shadow(0 0 4px rgba(16, 185, 129, 0.5));
}

.progress-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1px;
}

.progress-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  color: #ffffff;
}

.progress-sep {
  font-family: 'JetBrains Mono', monospace;
  font-size: 7px;
  color: rgba(255, 255, 255, 0.3);
}

.progress-total {
  font-family: 'JetBrains Mono', monospace;
  font-size: 7px;
  color: rgba(255, 255, 255, 0.5);
}

/* ===== Sources Counter ===== */
.mini-sources {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: 8px;
}

.sources-icon {
  width: 10px;
  height: 10px;
  color: var(--mini-accent);
}

.sources-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 8px;
  font-weight: 600;
  color: var(--mini-accent);
}

/* ===== Stream Dots ===== */
.mini-streams {
  display: flex;
  gap: 4px;
  margin-top: 2px;
}

.stream-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: hsla(var(--hue), 60%, 50%, 0.3);
  transition: all 0.3s ease;
}

.stream-dot.active {
  background: hsla(var(--hue), 70%, 55%, 1);
  box-shadow: 0 0 6px hsla(var(--hue), 70%, 55%, 0.6);
  animation: dot-pulse 1s ease-in-out infinite;
}

.stream-dot.done {
  background: var(--mini-accent);
}

@keyframes dot-pulse {
  0%, 100% { opacity: 0.7; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.1); }
}

/* ===== Activity Indicator ===== */
.activity-indicator {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 6px;
  height: 6px;
  background: var(--mini-primary);
  border-radius: 50%;
  animation: activity-pulse 1.5s ease-in-out infinite;
  box-shadow: 0 0 8px rgba(0, 212, 255, 0.6);
}

@keyframes activity-pulse {
  0%, 100% { opacity: 0.5; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ===== State Variations ===== */
.wide-research-mini.completed {
  --mini-primary: #10b981;
}

.wide-research-mini.completed .activity-indicator {
  background: var(--mini-accent);
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
}

/* ===== Dark mode adjustments ===== */
:global(.dark) .wide-research-mini {
  background: rgba(8, 12, 24, 0.98);
}
</style>
