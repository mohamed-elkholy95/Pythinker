<template>
  <Transition name="research-fade">
    <div v-if="isActive" class="wide-research-overlay" :class="{ 'completed': isCompleted }">
      <!-- Atmospheric background effects -->
      <div class="research-atmosphere">
        <div class="grid-lines"></div>
        <div class="scan-sweep" :style="{ '--progress': progressPercent + '%' }"></div>
        <div class="particle-field">
          <div v-for="i in 12" :key="i" class="particle" :style="getParticleStyle(i)"></div>
        </div>
      </div>

      <!-- Main content container -->
      <div class="research-content">
        <!-- Header with topic -->
        <div class="research-header">
          <div class="header-glow"></div>
          <div class="status-badge" :class="statusClass">
            <span class="status-dot"></span>
            <span class="status-text">{{ statusLabel }}</span>
          </div>
          <h2 class="research-topic">{{ topic }}</h2>
          <p class="research-subtitle">Wide Research • {{ searchTypesLabel }}</p>
          <ResearchPhaseIndicator
            :phase="phaseForIndicator"
            compact
            class="phase-indicator"
          />
        </div>

        <!-- Progress ring visualization -->
        <div class="progress-section">
          <div class="progress-ring-container">
            <svg class="progress-ring" viewBox="0 0 120 120">
              <!-- Background ring -->
              <circle
                class="ring-bg"
                cx="60"
                cy="60"
                r="52"
                fill="none"
                stroke-width="6"
              />
              <!-- Progress ring -->
              <circle
                class="ring-progress"
                cx="60"
                cy="60"
                r="52"
                fill="none"
                stroke-width="6"
                :stroke-dasharray="circumference"
                :stroke-dashoffset="progressOffset"
                stroke-linecap="round"
              />
              <!-- Inner glow -->
              <circle
                class="ring-glow"
                cx="60"
                cy="60"
                r="46"
                fill="none"
                stroke-width="1"
              />
            </svg>

            <!-- Center stats -->
            <div class="ring-center">
              <span class="ring-value">{{ completedQueries }}</span>
              <span class="ring-divider">/</span>
              <span class="ring-total">{{ totalQueries }}</span>
              <span class="ring-label">queries</span>
            </div>
          </div>

          <!-- Sources counter -->
          <div class="sources-counter">
            <div class="counter-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                <line x1="12" y1="22.08" x2="12" y2="12"/>
              </svg>
            </div>
            <div class="counter-value">
              <span class="value-num">{{ sourcesFound }}</span>
              <span class="value-label">sources discovered</span>
            </div>
          </div>
        </div>

        <!-- Parallel search streams visualization -->
        <div class="search-streams">
          <div class="streams-header">
            <span class="streams-title">Parallel Search Streams</span>
            <span class="streams-count">{{ activeStreams }} active</span>
          </div>

          <div class="streams-grid">
            <div
              v-for="(stream, idx) in searchStreams"
              :key="idx"
              class="stream-item"
              :class="stream.status"
            >
              <div class="stream-icon" :style="{ '--hue': stream.hue }">
                <component :is="getStreamIcon(stream.type)" class="icon" />
              </div>
              <div class="stream-info">
                <span class="stream-type">{{ stream.label }}</span>
                <span class="stream-query" v-if="stream.currentQuery">
                  {{ truncate(stream.currentQuery, 28) }}
                </span>
                <div class="stream-progress" v-if="stream.status === 'searching'">
                  <div class="progress-bar" :style="{ width: stream.progress + '%' }"></div>
                </div>
              </div>
              <div class="stream-count" v-if="stream.resultsCount > 0">
                +{{ stream.resultsCount }}
              </div>
            </div>
          </div>
        </div>

        <!-- Current query indicator -->
        <div v-if="currentQuery" class="current-query">
          <div class="query-pulse"></div>
          <span class="query-label">Searching:</span>
          <span class="query-text">{{ truncate(currentQuery, 50) }}</span>
        </div>

        <!-- Aggregation phase indicator -->
        <Transition name="phase-slide">
          <div v-if="aggregationPhase" class="aggregation-phase">
            <div class="phase-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 3v18M3 12h18M7.8 7.8l8.4 8.4M16.2 7.8l-8.4 8.4"/>
              </svg>
            </div>
            <span class="phase-label">{{ aggregationPhase }}</span>
          </div>
        </Transition>
      </div>

      <!-- Bottom timeline -->
      <div class="research-timeline">
        <div class="timeline-track">
          <div class="timeline-fill" :style="{ width: progressPercent + '%' }"></div>
        </div>
        <div class="timeline-markers">
          <div class="marker" :class="{ active: progressPercent >= 0 }">
            <span class="marker-dot"></span>
            <span class="marker-label">Start</span>
          </div>
          <div class="marker" :class="{ active: progressPercent >= 33 }">
            <span class="marker-dot"></span>
            <span class="marker-label">Searching</span>
          </div>
          <div class="marker" :class="{ active: progressPercent >= 66 }">
            <span class="marker-dot"></span>
            <span class="marker-label">Aggregating</span>
          </div>
          <div class="marker" :class="{ active: progressPercent >= 100 }">
            <span class="marker-dot"></span>
            <span class="marker-label">Complete</span>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import { Search, Globe, BookOpen, Newspaper, Database, Wrench } from 'lucide-vue-next'
import ResearchPhaseIndicator from '@/components/research/ResearchPhaseIndicator.vue'
import type { WideResearchState } from '@/types/message'

interface SearchStream {
  type: string
  label: string
  status: 'pending' | 'searching' | 'completed'
  currentQuery?: string
  progress: number
  resultsCount: number
  hue: number
}

const props = withDefaults(defineProps<{
  state: WideResearchState | null
  phase?: string | null
  alwaysShow?: boolean  // When true, always show overlay even without active state
}>(), {
  state: null,
  phase: null,
  alwaysShow: false
})

// Computed values
const isActive = computed(() => props.alwaysShow || (props.state !== null && props.state.status !== 'completed'))
const isCompleted = computed(() => props.state?.status === 'completed')
const topic = computed(() => props.state?.topic || 'Research')
const totalQueries = computed(() => props.state?.total_queries || 0)
const completedQueries = computed(() => props.state?.completed_queries || 0)
const sourcesFound = computed(() => props.state?.sources_found || 0)
const currentQuery = computed(() => props.state?.current_query)
const aggregationPhase = computed(() => {
  if (props.state?.status === 'aggregating') {
    return props.state.aggregation_strategy === 'synthesize'
      ? 'Synthesizing findings...'
      : props.state.aggregation_strategy === 'validate'
        ? 'Cross-validating sources...'
        : 'Aggregating results...'
  }
  return null
})

const progressPercent = computed(() => {
  if (!props.state || totalQueries.value === 0) return 0
  if (props.state.status === 'completed') return 100
  if (props.state.status === 'aggregating') return 85 + (15 * (completedQueries.value / totalQueries.value))
  return (completedQueries.value / totalQueries.value) * 85
})

const circumference = 2 * Math.PI * 52
const progressOffset = computed(() => {
  return circumference - (progressPercent.value / 100) * circumference
})

const statusLabel = computed(() => {
  switch (props.state?.status) {
    case 'pending': return 'Preparing'
    case 'searching': return 'Searching'
    case 'aggregating': return 'Aggregating'
    case 'completed': return 'Complete'
    case 'failed': return 'Failed'
    default: return 'Initializing'
  }
})

const statusClass = computed(() => props.state?.status || 'pending')
const phaseForIndicator = computed(() => {
  if (props.phase) return props.phase
  if (props.state?.phase) return props.state.phase
  switch (props.state?.status) {
    case 'pending':
      return 'planning'
    case 'searching':
      return 'executing'
    case 'aggregating':
      return 'summarizing'
    case 'completed':
      return 'completed'
    default:
      return 'planning'
  }
})

const searchTypesLabel = computed(() => {
  const types = props.state?.search_types || []
  if (types.length === 0) return 'Multi-source'
  if (types.length <= 2) return types.join(' & ')
  return `${types.length} search types`
})

// Generate search streams from state
const searchStreams = computed((): SearchStream[] => {
  const types = props.state?.search_types || ['info', 'news', 'academic']
  const hues = [200, 280, 340, 160, 40, 320] // Distinct hues for each type

  return types.map((type, idx) => ({
    type,
    label: getTypeLabel(type),
    status: getStreamStatus(type),
    currentQuery: props.state?.current_query,
    progress: Math.min(100, (completedQueries.value / Math.max(1, totalQueries.value / types.length)) * 100),
    resultsCount: Math.floor(sourcesFound.value / types.length),
    hue: hues[idx % hues.length]
  }))
})

const activeStreams = computed(() => {
  return searchStreams.value.filter(s => s.status === 'searching').length
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

function getStreamStatus(_type: string): 'pending' | 'searching' | 'completed' {
  if (!props.state) return 'pending'
  if (props.state.status === 'completed' || props.state.status === 'aggregating') return 'completed'
  if (props.state.status === 'pending') return 'pending'
  return 'searching'
}

function getStreamIcon(type: string) {
  const icons: Record<string, Component> = {
    info: Globe,
    news: Newspaper,
    academic: BookOpen,
    api: Database,
    data: Database,
    tool: Wrench
  }
  return icons[type] || Search
}

function truncate(text: string, maxLength: number): string {
  if (!text) return ''
  return text.length > maxLength ? text.slice(0, maxLength - 3) + '...' : text
}

function getParticleStyle(index: number) {
  const angle = (index / 12) * 360
  const delay = index * 0.3
  return {
    '--angle': angle + 'deg',
    '--delay': delay + 's'
  }
}
</script>

<style scoped>
/* ===== Design System Variables ===== */
.wide-research-overlay {
  --research-primary: #00d4ff;
  --research-secondary: #7c3aed;
  --research-accent: #10b981;
  --research-warning: #f59e0b;
  --research-bg: rgba(10, 15, 30, 0.95);
  --research-surface: rgba(20, 30, 50, 0.8);
  --research-border: rgba(0, 212, 255, 0.2);
  --research-glow: rgba(0, 212, 255, 0.4);

  /* Typography */
  --font-display: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
  --font-body: var(--font-sans);
}

/* ===== Base Overlay ===== */
.wide-research-overlay {
  position: absolute;
  inset: 0;
  background: var(--research-bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 50;
}

/* ===== Atmospheric Effects ===== */
.research-atmosphere {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
}

.scan-sweep {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(0, 212, 255, 0.05) calc(var(--progress) - 5%),
    rgba(0, 212, 255, 0.15) var(--progress),
    transparent calc(var(--progress) + 2%)
  );
  animation: sweep-pulse 2s ease-in-out infinite;
}

@keyframes sweep-pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.particle-field {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.particle {
  position: absolute;
  width: 4px;
  height: 4px;
  background: var(--research-primary);
  border-radius: 50%;
  opacity: 0;
  animation: particle-orbit 8s linear infinite;
  animation-delay: var(--delay);
}

@keyframes particle-orbit {
  0% {
    opacity: 0;
    transform: rotate(var(--angle)) translateX(80px) scale(0);
  }
  10% {
    opacity: 0.8;
    transform: rotate(var(--angle)) translateX(100px) scale(1);
  }
  90% {
    opacity: 0.4;
    transform: rotate(calc(var(--angle) + 180deg)) translateX(160px) scale(0.5);
  }
  100% {
    opacity: 0;
    transform: rotate(calc(var(--angle) + 180deg)) translateX(180px) scale(0);
  }
}

/* ===== Main Content ===== */
.research-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  gap: 24px;
  z-index: 1;
}

/* ===== Header ===== */
.research-header {
  text-align: center;
  position: relative;
}

.header-glow {
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  width: 200px;
  height: 60px;
  background: radial-gradient(ellipse at center, var(--research-glow) 0%, transparent 70%);
  filter: blur(20px);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: var(--research-surface);
  border: 1px solid var(--research-border);
  border-radius: 20px;
  font-family: var(--font-display);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--research-primary);
  margin-bottom: 12px;
}

.status-badge.searching {
  border-color: var(--research-primary);
}

.status-badge.aggregating {
  border-color: var(--research-secondary);
  color: var(--research-secondary);
}

.status-badge.completed {
  border-color: var(--research-accent);
  color: var(--research-accent);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

.research-topic {
  font-family: var(--font-body);
  font-size: 20px;
  font-weight: 600;
  color: #ffffff;
  margin: 0 0 4px;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.research-subtitle {
  font-family: var(--font-display);
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
  letter-spacing: 0.5px;
}

.phase-indicator {
  margin-top: var(--space-3);
  min-width: 280px;
}

/* ===== Progress Section ===== */
.progress-section {
  display: flex;
  align-items: center;
  gap: 32px;
}

.progress-ring-container {
  position: relative;
  width: 120px;
  height: 120px;
}

.progress-ring {
  transform: rotate(-90deg);
}

.ring-bg {
  stroke: rgba(255, 255, 255, 0.1);
}

.ring-progress {
  stroke: var(--research-primary);
  transition: stroke-dashoffset 0.5s ease-out;
  filter: drop-shadow(0 0 8px var(--research-glow));
}

.ring-glow {
  stroke: var(--research-glow);
  animation: ring-pulse 2s ease-in-out infinite;
}

@keyframes ring-pulse {
  0%, 100% { opacity: 0.2; }
  50% { opacity: 0.6; }
}

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.ring-value {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
  line-height: 1;
}

.ring-divider {
  font-family: var(--font-display);
  font-size: 14px;
  color: rgba(255, 255, 255, 0.3);
  margin: 0 2px;
}

.ring-total {
  font-family: var(--font-display);
  font-size: 16px;
  color: rgba(255, 255, 255, 0.5);
}

.ring-label {
  font-family: var(--font-display);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: rgba(255, 255, 255, 0.4);
  margin-top: 4px;
}

/* ===== Sources Counter ===== */
.sources-counter {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: var(--research-surface);
  border: 1px solid var(--research-border);
  border-radius: 12px;
}

.counter-icon {
  width: 32px;
  height: 32px;
  color: var(--research-accent);
  opacity: 0.8;
}

.counter-icon svg {
  width: 100%;
  height: 100%;
}

.counter-value {
  display: flex;
  flex-direction: column;
}

.value-num {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--research-accent);
  line-height: 1;
}

.value-label {
  font-family: var(--font-display);
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ===== Search Streams ===== */
.search-streams {
  width: 100%;
  max-width: 400px;
}

.streams-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 0 4px;
}

.streams-title {
  font-family: var(--font-display);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: rgba(255, 255, 255, 0.6);
}

.streams-count {
  font-family: var(--font-display);
  font-size: 10px;
  color: var(--research-primary);
}

.streams-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stream-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.stream-item.searching {
  background: rgba(0, 212, 255, 0.05);
  border-color: rgba(0, 212, 255, 0.2);
}

.stream-item.completed {
  border-color: rgba(16, 185, 129, 0.2);
}

.stream-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsla(var(--hue), 70%, 50%, 0.15);
  border-radius: 6px;
  color: hsla(var(--hue), 70%, 60%, 1);
}

.stream-icon .icon {
  width: 14px;
  height: 14px;
}

.stream-info {
  flex: 1;
  min-width: 0;
}

.stream-type {
  display: block;
  font-family: var(--font-body);
  font-size: 12px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
}

.stream-query {
  display: block;
  font-family: var(--font-display);
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stream-progress {
  height: 2px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 1px;
  margin-top: 6px;
  overflow: hidden;
}

.stream-progress .progress-bar {
  height: 100%;
  background: var(--research-primary);
  border-radius: 1px;
  transition: width 0.3s ease;
}

.stream-count {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 600;
  color: var(--research-accent);
  padding: 2px 8px;
  background: rgba(16, 185, 129, 0.15);
  border-radius: 10px;
}

/* ===== Current Query ===== */
.current-query {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--research-surface);
  border: 1px solid var(--research-border);
  border-radius: 8px;
  max-width: 400px;
}

.query-pulse {
  width: 8px;
  height: 8px;
  background: var(--research-primary);
  border-radius: 50%;
  animation: pulse-dot 1s ease-in-out infinite;
  box-shadow: 0 0 12px var(--research-glow);
}

.query-label {
  font-family: var(--font-display);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(255, 255, 255, 0.5);
}

.query-text {
  font-family: var(--font-body);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== Aggregation Phase ===== */
.aggregation-phase {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  background: rgba(124, 58, 237, 0.1);
  border: 1px solid rgba(124, 58, 237, 0.3);
  border-radius: 8px;
}

.phase-icon {
  width: 20px;
  height: 20px;
  color: var(--research-secondary);
  animation: spin 4s linear infinite;
}

.phase-icon svg {
  width: 100%;
  height: 100%;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.phase-label {
  font-family: var(--font-display);
  font-size: 12px;
  color: var(--research-secondary);
}

/* ===== Timeline ===== */
.research-timeline {
  padding: 16px 24px 20px;
  z-index: 1;
}

.timeline-track {
  height: 3px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 12px;
}

.timeline-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--research-primary), var(--research-secondary));
  border-radius: 2px;
  transition: width 0.5s ease-out;
  box-shadow: 0 0 10px var(--research-glow);
}

.timeline-markers {
  display: flex;
  justify-content: space-between;
}

.marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  opacity: 0.3;
  transition: opacity 0.3s ease;
}

.marker.active {
  opacity: 1;
}

.marker-dot {
  width: 8px;
  height: 8px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  transition: all 0.3s ease;
}

.marker.active .marker-dot {
  background: var(--research-primary);
  box-shadow: 0 0 8px var(--research-glow);
}

.marker-label {
  font-family: var(--font-display);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(255, 255, 255, 0.5);
}

.marker.active .marker-label {
  color: rgba(255, 255, 255, 0.8);
}

/* ===== Completed State ===== */
.wide-research-overlay.completed {
  --research-primary: #10b981;
  --research-glow: rgba(16, 185, 129, 0.4);
}

/* ===== Transitions ===== */
.research-fade-enter-active,
.research-fade-leave-active {
  transition: all 0.5s ease;
}

.research-fade-enter-from {
  opacity: 0;
  transform: scale(0.95);
}

.research-fade-leave-to {
  opacity: 0;
  transform: scale(1.02);
}

.phase-slide-enter-active,
.phase-slide-leave-active {
  transition: all 0.4s ease;
}

.phase-slide-enter-from,
.phase-slide-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
