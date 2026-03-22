<script setup lang="ts">
import { computed } from 'vue'
import PlannerActivityIndicator from '@/components/ui/PlannerActivityIndicator.vue'
import type { PlanningPhase } from '@/types/event'

interface Props {
  title?: string
  phase: PlanningPhase
  message: string
  progressPercent?: number
  complexityCategory?: 'simple' | 'medium' | 'complex'
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Agent is thinking',
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
    <PlannerActivityIndicator />
    <span class="status-title">{{ title }}</span>
    <span class="status-sep">&middot;</span>
    <span class="status-phase">{{ thinkingMessage }}</span>
    <div class="progress-track" aria-hidden="true">
      <div
        class="progress-fill"
        :class="{ 'progress-fill--indeterminate': progressValue === null }"
        :style="progressValue !== null ? { width: progressWidth } : undefined"
      />
    </div>
    <span v-if="badge" class="complexity-badge" :class="badge.cls">{{ badge.label }}</span>
    <span v-if="progressValue !== null" class="progress-value">{{ progressValue }}%</span>
  </div>
</template>

<style scoped>
.planning-card {
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: var(--background-menu-white, #fff);
  box-shadow: 0 1px 4px 0 rgba(0, 0, 0, 0.04);
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  overflow: hidden;
}

.status-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  flex-shrink: 0;
}

.status-sep {
  font-size: 10px;
  color: var(--text-secondary, #94a3b8);
  flex-shrink: 0;
}

.status-phase {
  font-size: 11px;
  color: var(--text-secondary, #64748b);
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.progress-track {
  position: relative;
  height: 3px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.25);
  overflow: hidden;
  flex: 1 1 60px;
  min-width: 40px;
  max-width: 100px;
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

.progress-value {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

.complexity-badge {
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.03em;
  flex-shrink: 0;
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
  background: var(--background-menu-dark, rgba(15, 23, 42, 0.78));
  box-shadow: 0 1px 4px 0 rgba(2, 6, 23, 0.2);
}

:deep(.dark) .status-title,
.dark .status-title,
:deep(.dark) .progress-value,
.dark .progress-value {
  color: #e2e8f0;
}

:deep(.dark) .status-phase,
.dark .status-phase {
  color: #cbd5e1;
}

@keyframes progress-indeterminate {
  0% { transform: translateX(-30%); }
  50% { transform: translateX(90%); }
  100% { transform: translateX(-30%); }
}

@media (prefers-reduced-motion: reduce) {
  .progress-fill {
    transition: none;
  }

  .progress-fill--indeterminate {
    width: 40%;
    animation: none;
    transform: none;
  }
}
</style>
