<script setup lang="ts">
import { computed } from 'vue'
import { Circle, CheckCircle2, Loader2, AlertCircle, SkipForward } from 'lucide-vue-next'
import type { PlanEventData } from '@/types/event'

const props = defineProps<{
  plan?: PlanEventData | null
  /** Raw plan markdown from streaming (used before structured plan arrives) */
  streamingText?: string
  /** Whether the plan is still being streamed */
  isStreaming?: boolean
}>()

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
      title: step.description?.split('.')[0]?.substring(0, 80) || `Step ${i + 1}`,
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
    <!-- Header -->
    <div class="plan-header">
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

    <!-- Streaming indicator -->
    <div v-if="isStreaming && parsedSteps.length === 0" class="plan-streaming">
      <Loader2 :size="14" class="animate-spin text-blue-400" />
      <span>Creating plan...</span>
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

.plan-streaming {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
