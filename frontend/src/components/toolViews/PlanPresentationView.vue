<script setup lang="ts">
import { computed } from 'vue'
import { Circle, CheckCircle2, Loader2, AlertCircle, SkipForward } from 'lucide-vue-next'
import ThinkingIndicator from '@/components/ui/ThinkingIndicator.vue'
import type { PlanEventData } from '@/types/event'

const props = defineProps<{
  plan?: PlanEventData | null
  /** Raw plan markdown from streaming (used before structured plan arrives) */
  streamingText?: string
  /** Whether the plan is still being streamed */
  isStreaming?: boolean
}>()

/** Truncate text at a word boundary to avoid cutting mid-word. */
function truncateAtWordBoundary(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  const truncated = text.substring(0, maxLen)
  const lastSpace = truncated.lastIndexOf(' ')
  return lastSpace > maxLen * 0.6 ? truncated.substring(0, lastSpace) : truncated
}

interface ParsedStep {
  number: number
  title: string
  description: string
  status: string
}

const parsedSteps = computed((): ParsedStep[] => {
  if (props.plan?.steps?.length) {
    return props.plan.steps.map((step, i) => ({
      number: i + 1,
      title: truncateAtWordBoundary(step.description?.split('.')[0] || '', 120) || `Step ${i + 1}`,
      description: step.description || '',
      status: step.status || 'pending',
    }))
  }
  if (props.streamingText) {
    return parseMarkdownSteps(props.streamingText)
  }
  return []
})

const planTitle = computed(() => {
  if (props.plan?.title) return props.plan.title
  if (props.streamingText) {
    const match = props.streamingText.match(/^#\s+(.+)/m)
    if (match) return match[1]
  }
  return 'Execution Plan'
})

const planGoal = computed(() => {
  if (props.plan?.goal) return props.plan.goal
  if (props.streamingText) {
    const match = props.streamingText.match(/^>\s+(.+)/m)
    if (match) return match[1]
  }
  return ''
})

const completedCount = computed(() =>
  parsedSteps.value.filter(s => s.status === 'completed').length
)

const totalSteps = computed(() => parsedSteps.value.length)

function parseMarkdownSteps(text: string): ParsedStep[] {
  const steps: ParsedStep[] = []
  const lines = text.split('\n')
  let currentStep: ParsedStep | null = null

  for (const line of lines) {
    const stepMatch = line.match(/^##\s+Step\s+(\d+)\s*[—–-]\s*(.*)/)
    if (stepMatch) {
      if (currentStep) steps.push(currentStep)
      currentStep = {
        number: parseInt(stepMatch[1], 10),
        title: stepMatch[2].trim() || `Step ${stepMatch[1]}`,
        description: '',
        status: 'pending',
      }
    } else if (currentStep && line.trim() && !line.startsWith('#') && !line.startsWith('---') && !line.startsWith('|')) {
      const cleaned = line.replace(/^>\s*/, '').trim()
      if (cleaned) {
        currentStep.description = currentStep.description
          ? `${currentStep.description} ${cleaned}`
          : cleaned
      }
    }
  }
  if (currentStep) steps.push(currentStep)
  return steps
}

function getStepIcon(status: string) {
  switch (status) {
    case 'completed': return CheckCircle2
    case 'running':
    case 'started': return Loader2
    case 'failed': return AlertCircle
    case 'skipped': return SkipForward
    default: return Circle
  }
}

function getStepIconClass(status: string): string {
  switch (status) {
    case 'completed': return 'text-emerald-500'
    case 'running':
    case 'started': return 'text-blue-400 animate-spin'
    case 'failed': return 'text-red-400'
    case 'skipped': return 'text-gray-400'
    default: return 'text-gray-500 dark:text-gray-600'
  }
}

function getStepNumberClass(status: string): string {
  switch (status) {
    case 'completed': return 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
    case 'running':
    case 'started': return 'bg-blue-500/15 text-blue-400 border-blue-400/30'
    case 'failed': return 'bg-red-500/15 text-red-400 border-red-400/30'
    default: return 'bg-gray-500/10 text-gray-500 dark:text-gray-400 border-gray-500/20'
  }
}
</script>

<template>
  <div class="plan-presentation">
    <!-- Header (hidden during initial streaming placeholder) -->
    <div v-if="parsedSteps.length > 0 || !isStreaming" class="plan-header">
      <div class="plan-title-row">
        <h2 class="plan-title">{{ planTitle }}</h2>
        <div v-if="totalSteps > 0" class="plan-badge">
          {{ completedCount }}/{{ totalSteps }} steps
        </div>
      </div>
      <p v-if="planGoal" class="plan-goal">{{ planGoal }}</p>
    </div>

    <!-- Steps -->
    <div class="plan-steps">
      <div
        v-for="step in parsedSteps"
        :key="step.number"
        class="plan-step"
        :class="{
          'plan-step-active': step.status === 'running' || step.status === 'started',
          'plan-step-completed': step.status === 'completed',
        }"
      >
        <!-- Indicator column -->
        <div class="plan-step-indicator">
          <div class="plan-step-number" :class="getStepNumberClass(step.status)">
            <component
              v-if="step.status !== 'pending'"
              :is="getStepIcon(step.status)"
              :size="14"
              :class="getStepIconClass(step.status)"
            />
            <span v-else>{{ step.number }}</span>
          </div>
          <div
            v-if="step.number < totalSteps"
            class="plan-step-connector"
            :class="{ 'plan-step-connector-done': step.status === 'completed' }"
          />
        </div>

        <!-- Content column -->
        <div class="plan-step-content">
          <div class="plan-step-title">{{ step.title }}</div>
          <div v-if="step.description && step.description !== step.title" class="plan-step-desc">
            {{ step.description }}
          </div>
        </div>
      </div>
    </div>

    <!-- Planning indicator — shown before plan steps arrive -->
    <div v-if="isStreaming && parsedSteps.length === 0" class="plan-streaming">
      <!-- Animated header -->
      <div class="plan-streaming-header">
        <ThinkingIndicator :show-text="false" />
        <div class="plan-streaming-labels">
          <span class="plan-streaming-title">Planning</span>
          <span class="plan-streaming-subtitle">Analyzing task and building execution plan</span>
        </div>
      </div>

      <!-- Animated skeleton steps that hint at a plan being built -->
      <div class="plan-streaming-skeleton">
        <div v-for="i in 4" :key="i" class="skeleton-step" :style="{ animationDelay: `${(i - 1) * 0.15}s` }">
          <div class="skeleton-step-indicator">
            <div class="skeleton-circle" :class="{ 'skeleton-circle-active': i === 1 }">
              <div v-if="i === 1" class="skeleton-circle-pulse" />
            </div>
            <div v-if="i < 4" class="skeleton-connector" />
          </div>
          <div class="skeleton-step-content">
            <div class="skeleton-line skeleton-line-title" :style="{ width: `${65 + (i * 7) % 25}%` }" />
            <div class="skeleton-line skeleton-line-desc" :style="{ width: `${45 + (i * 13) % 35}%` }" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-presentation {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  background: var(--background-white-main);
}

.plan-header { margin-bottom: 24px; }

.plan-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.plan-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.3;
}

.plan-badge {
  flex-shrink: 0;
  padding: 3px 10px;
  border-radius: 12px;
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.06));
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}

.plan-goal {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

/* ── Steps ───────────────────────────── */
.plan-steps { display: flex; flex-direction: column; }

.plan-step { display: flex; gap: 14px; min-height: 56px; }

.plan-step-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 28px;
}

.plan-step-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  border: 1.5px solid;
  flex-shrink: 0;
}

.plan-step-connector {
  width: 2px;
  flex: 1;
  min-height: 12px;
  background: var(--border-light, rgba(0, 0, 0, 0.08));
  margin: 4px 0;
  border-radius: 1px;
}

.plan-step-connector-done { background: rgba(16, 185, 129, 0.3); }

.plan-step-content {
  flex: 1;
  min-width: 0;
  padding: 4px 0 14px;
}

.plan-step-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
  margin-bottom: 2px;
}

.plan-step-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.plan-step-active .plan-step-content {
  background: rgba(59, 130, 246, 0.06);
  border-radius: 8px;
  padding: 8px 12px 12px;
  margin: -4px -12px 10px;
}

.plan-step-active .plan-step-title { color: var(--text-brand, #3b82f6); }

/* ── Planning placeholder ────────────── */
.plan-streaming {
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding: 32px 0 24px;
  animation: plan-streaming-enter 0.5s ease-out;
}

@keyframes plan-streaming-enter {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.plan-streaming-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.plan-streaming-labels {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.plan-streaming-title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.01em;
  background: linear-gradient(90deg, #374151 0%, #374151 40%, #9ca3af 50%, #374151 60%, #374151 100%);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: plan-title-shimmer 4s linear infinite;
}

@keyframes plan-title-shimmer {
  0%   { background-position: 150% center; }
  100% { background-position: -150% center; }
}

.plan-streaming-subtitle {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
  opacity: 0.7;
}

/* Skeleton steps */
.plan-streaming-skeleton {
  display: flex;
  flex-direction: column;
}

.skeleton-step {
  display: flex;
  gap: 14px;
  min-height: 52px;
  animation: skeleton-step-enter 0.4s ease-out both;
}

@keyframes skeleton-step-enter {
  from { opacity: 0; transform: translateX(-6px); }
  to   { opacity: 1; transform: translateX(0); }
}

.skeleton-step-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 28px;
}

.skeleton-circle {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.06));
  border: 1.5px solid var(--border-light, rgba(0, 0, 0, 0.08));
  position: relative;
  flex-shrink: 0;
}

.skeleton-circle-active {
  background: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.25);
}

.skeleton-circle-pulse {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1.5px solid rgba(59, 130, 246, 0.3);
  animation: skeleton-pulse-ring 2s ease-in-out infinite;
}

@keyframes skeleton-pulse-ring {
  0%, 100% { opacity: 0.3; transform: scale(0.9); }
  50%      { opacity: 0.8; transform: scale(1.1); }
}

.skeleton-connector {
  width: 2px;
  flex: 1;
  min-height: 10px;
  margin: 4px 0;
  border-radius: 1px;
  background: var(--border-light, rgba(0, 0, 0, 0.06));
}

.skeleton-step-content {
  flex: 1;
  min-width: 0;
  padding: 4px 0 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton-line {
  height: 10px;
  border-radius: 5px;
  background: linear-gradient(
    90deg,
    var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.06)) 25%,
    var(--fill-tsp-gray-hover, rgba(0, 0, 0, 0.1)) 50%,
    var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.06)) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
}

.skeleton-line-title { height: 12px; }
.skeleton-line-desc  { height: 8px; opacity: 0.6; }

@keyframes skeleton-shimmer {
  0%   { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

/* Dark mode */
:global(.dark) .plan-streaming-title {
  background: linear-gradient(90deg, #e5e7eb 0%, #e5e7eb 40%, #6b7280 50%, #e5e7eb 60%, #e5e7eb 100%);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: plan-title-shimmer 4s linear infinite;
}

:global(.dark) .skeleton-circle {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
}

:global(.dark) .skeleton-circle-active {
  background: rgba(96, 165, 250, 0.12);
  border-color: rgba(96, 165, 250, 0.25);
}

:global(.dark) .skeleton-line {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.06) 25%,
    rgba(255, 255, 255, 0.12) 50%,
    rgba(255, 255, 255, 0.06) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
}

:global(.dark) .skeleton-connector {
  background: rgba(255, 255, 255, 0.08);
}
</style>
