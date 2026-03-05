<script setup lang="ts">
import { computed } from 'vue'
import PlannerActivityIndicator from '@/components/ui/PlannerActivityIndicator.vue'
import type { PlanningPhase } from '@/types/event'

interface Props {
  phase: PlanningPhase
  message: string
  progressPercent?: number
  complexityCategory?: 'simple' | 'medium' | 'complex'
}

const props = withDefaults(defineProps<Props>(), {
  complexityCategory: undefined,
})

const PHASE_DESCRIPTIONS: Record<PlanningPhase, string> = {
  received: 'Understanding your request',
  analyzing: 'Breaking down your request',
  planning: 'Building an execution plan',
  verifying: 'Verifying plan quality',
  executing_setup: 'Starting execution',
  finalizing: 'Preparing execution',
  waiting: 'Waiting for your input',
}

const BADGE_STYLES: Record<string, { label: string; cls: string }> = {
  simple: { label: 'Simple', cls: 'badge--simple' },
  medium: { label: 'Medium', cls: 'badge--medium' },
  complex: { label: 'Complex', cls: 'badge--complex' },
}

const phaseDescription = computed(() => PHASE_DESCRIPTIONS[props.phase] ?? PHASE_DESCRIPTIONS.received)

const thinkingMessage = computed(() => {
  const trimmed = props.message.trim()
  if (trimmed.length > 0) return trimmed
  return phaseDescription.value
})

const progressValue = computed(() => {
  if (typeof props.progressPercent !== 'number' || Number.isNaN(props.progressPercent)) {
    return null
  }
  return Math.min(Math.max(Math.round(props.progressPercent), 0), 100)
})

const progressWidth = computed(() => `${progressValue.value ?? 0}%`)

const badge = computed(() => {
  if (!props.complexityCategory) return null
  return BADGE_STYLES[props.complexityCategory] ?? null
})
</script>

<template>
  <div class="planning-card" role="status" aria-live="polite">
    <div class="card-header">
      <div class="status-wrap">
        <PlannerActivityIndicator />
        <div class="status-copy">
          <p class="status-title">Agent is thinking</p>
          <p class="status-phase">{{ phaseDescription }}</p>
        </div>
      </div>
      <span v-if="progressValue !== null" class="progress-value">{{ progressValue }}%</span>
    </div>

    <p class="thinking-message">{{ thinkingMessage }}</p>

    <div class="card-footer">
      <div class="progress-track" aria-hidden="true">
        <div
          class="progress-fill"
          :class="{ 'progress-fill--indeterminate': progressValue === null }"
          :style="progressValue !== null ? { width: progressWidth } : undefined"
        />
      </div>
      <span v-if="badge" class="complexity-badge" :class="badge.cls">{{ badge.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.planning-card {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.status-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.status-copy {
  min-width: 0;
}

.status-title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
  line-height: 1.2;
}

.status-phase {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--text-secondary, #64748b);
  line-height: 1.2;
}

.progress-value {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

.thinking-message {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary, #334155);
  line-height: 1.35;
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-track {
  position: relative;
  height: 4px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.35);
  overflow: hidden;
  flex: 1;
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #c48a50 0%, #d9ab7a 100%);
  transition: width 0.35s ease;
}

.progress-fill--indeterminate {
  width: 32%;
  animation: progress-indeterminate 1.6s ease-in-out infinite;
}

.complexity-badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
}

.badge--simple {
  color: #065f46;
  background: rgba(16, 185, 129, 0.16);
}

.badge--medium {
  color: #92400e;
  background: rgba(245, 158, 11, 0.2);
}

.badge--complex {
  color: #9f1239;
  background: rgba(244, 63, 94, 0.2);
}

:deep(.dark) .planning-card,
.dark .planning-card {
  border-color: rgba(148, 163, 184, 0.24);
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.78) 0%, rgba(2, 6, 23, 0.86) 100%);
  box-shadow: 0 12px 28px rgba(2, 6, 23, 0.45);
}

:deep(.dark) .status-title,
.dark .status-title,
:deep(.dark) .progress-value,
.dark .progress-value {
  color: #e2e8f0;
}

:deep(.dark) .status-phase,
.dark .status-phase,
:deep(.dark) .thinking-message,
.dark .thinking-message {
  color: #cbd5e1;
}

@keyframes progress-indeterminate {
  0% {
    transform: translateX(-30%);
  }
  50% {
    transform: translateX(90%);
  }
  100% {
    transform: translateX(-30%);
  }
}
</style>
