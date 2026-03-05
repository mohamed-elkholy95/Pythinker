<script setup lang="ts">
import { computed } from 'vue'
import { Check } from 'lucide-vue-next'
import PlannerActivityIndicator from '@/components/ui/PlannerActivityIndicator.vue'
import type { PlanningPhase } from '@/types/event'

interface Props {
  phase: PlanningPhase
  message: string
  progressPercent: number
  complexityCategory?: 'simple' | 'medium' | 'complex'
  currentPlanningMessage: string
}

const props = withDefaults(defineProps<Props>(), {
  complexityCategory: undefined,
})

interface PhaseStep {
  key: PlanningPhase
  label: string
}

const PHASE_STEPS: PhaseStep[] = [
  { key: 'received', label: 'Received' },
  { key: 'analyzing', label: 'Analyzing' },
  { key: 'planning', label: 'Planning' },
  { key: 'finalizing', label: 'Finalizing' },
]

const currentPhaseIndex = computed(() => {
  const idx = PHASE_STEPS.findIndex((s) => s.key === props.phase)
  return idx >= 0 ? idx : 0
})

const stepClass = (index: number) => ({
  'step--complete': index < currentPhaseIndex.value,
  'step--active': index === currentPhaseIndex.value,
  'step--pending': index > currentPhaseIndex.value,
})

// Time estimate removed — keyword-based heuristics cannot accurately predict
// actual task duration (depends on LLM speed, search count, network, browser).
// Showing a confidently wrong estimate is worse than no estimate.
// The complexity badge provides sufficient context.

const BADGE_STYLES: Record<string, { label: string; cls: string }> = {
  simple: { label: 'Simple', cls: 'badge--simple' },
  medium: { label: 'Medium', cls: 'badge--medium' },
  complex: { label: 'Complex', cls: 'badge--complex' },
}

const badge = computed(() => {
  if (!props.complexityCategory) return null
  return BADGE_STYLES[props.complexityCategory] ?? null
})

const progressWidth = computed(() => `${Math.min(Math.max(props.progressPercent, 0), 100)}%`)

</script>

<template>
  <div
    class="planning-card"
    role="status"
    aria-live="polite"
  >
    <!-- Row 1: Neural network icon + Phase stepper -->
    <div class="card-header">
      <div class="card-activity">
        <PlannerActivityIndicator />
      </div>

      <!-- Phase stepper -->
      <div class="phase-track" :aria-label="`Phase: ${phase}`">
        <template v-for="(step, index) in PHASE_STEPS" :key="step.key">
          <!-- Connector line (before every step except first) -->
          <div
            v-if="index > 0"
            class="phase-connector"
            :class="{ 'connector--filled': index <= currentPhaseIndex }"
          />
          <div class="phase-step" :class="stepClass(index)">
            <span class="step-dot">
              <Check v-if="index < currentPhaseIndex" :size="8" class="step-check" />
            </span>
            <span class="step-label">{{ step.label }}</span>
          </div>
        </template>
      </div>
    </div>

    <!-- Row 2: Cycling message -->
    <div class="card-message">
      <span class="message-shimmer">
        {{ currentPlanningMessage }}
      </span>
    </div>

    <!-- Row 3: Progress bar + Complexity badge -->
    <div
      v-if="badge"
      class="card-footer"
    >
      <div class="time-label-spacer" />

      <!-- Thin progress bar -->
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: progressWidth }" />
      </div>

      <!-- Complexity badge -->
      <span v-if="badge" class="complexity-badge" :class="badge.cls">
        {{ badge.label }}
      </span>
    </div>
  </div>
</template>

<style scoped>
/* ===== CARD CONTAINER ===== */
.planning-card {
  padding: 12px 16px 10px;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ===== HEADER ROW ===== */
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-activity {
  flex-shrink: 0;
}

/* ===== PHASE STEPPER ===== */
.phase-track {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0;
  min-width: 0;
}

.phase-connector {
  flex: 0 0 auto;
  width: 12px;
  height: 1.5px;
  background: var(--border-main, #e2e8f0);
  transition: background 0.4s ease;
}

.connector--filled {
  background: #34d399;
}

.phase-step {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.step-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
  border: 1.5px solid var(--border-main, #cbd5e1);
  background: transparent;
}

.step-check {
  color: #fff;
  stroke-width: 3;
}

.step-label {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--text-muted, #94a3b8);
  white-space: nowrap;
  letter-spacing: 0.01em;
  transition: color 0.3s ease;
}

/* Step states */
.step--complete .step-dot {
  background: #34d399;
  border-color: #34d399;
}

.step--active .step-dot {
  border-color: #c48a50;
  background: rgba(196, 138, 80, 0.15);
  animation: dot-pulse 1.8s ease-in-out infinite;
}

.step--active .step-label {
  color: var(--text-primary, #1e293b);
  font-weight: 600;
}

.step--pending .step-dot {
  border-color: var(--border-main, #e2e8f0);
  background: transparent;
}

/* ===== MESSAGE ROW ===== */
.card-message {
  padding: 0 2px 0 32px; /* 22px activity icon + 10px gap = align under stepper */
}

.message-shimmer {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  background: linear-gradient(
    120deg,
    #6b7280 0%,
    #6b7280 35%,
    #d1d5db 50%,
    #6b7280 65%,
    #6b7280 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: planning-shimmer 2.5s ease-in-out infinite;
}

/* ===== FOOTER ROW ===== */
.card-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 2px;
}

.time-label-spacer {
  flex-shrink: 0;
  width: 0;
}

/* Progress bar */
.progress-track {
  flex: 1;
  height: 3px;
  border-radius: 2px;
  background: var(--fill-tsp-gray-main, rgba(15, 23, 42, 0.06));
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, #c48a50, #e3a45a);
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Complexity badge */
.complexity-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  flex-shrink: 0;
}

.badge--simple {
  background: rgba(52, 211, 153, 0.12);
  color: #059669;
  border: 1px solid rgba(52, 211, 153, 0.25);
}

.badge--medium {
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.badge--complex {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.2);
}

/* ===== ANIMATIONS ===== */
@keyframes dot-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(196, 138, 80, 0.35);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(196, 138, 80, 0);
    transform: scale(1.1);
  }
}

@keyframes planning-shimmer {
  0% {
    background-position: 100% 50%;
  }
  50% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 100% 50%;
  }
}

/* ===== DARK MODE ===== */
:deep(.dark) .planning-card,
.dark .planning-card {
  background: linear-gradient(180deg, #222222 0%, #1a1a1a 100%);
  border: 1px solid rgba(128, 128, 128, 0.2);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
}

:deep(.dark) .message-shimmer,
.dark .message-shimmer {
  background: linear-gradient(
    120deg,
    #9ca3af 0%,
    #9ca3af 35%,
    #f3f4f6 50%,
    #9ca3af 65%,
    #9ca3af 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

:deep(.dark) .step--active .step-dot,
.dark .step--active .step-dot {
  border-color: #ffd67a;
  background: rgba(255, 214, 122, 0.15);
}

:deep(.dark) .step--active .step-label,
.dark .step--active .step-label {
  color: #fafafa;
}

:deep(.dark) .phase-connector,
.dark .phase-connector {
  background: rgba(255, 255, 255, 0.1);
}

:deep(.dark) .connector--filled,
.dark .connector--filled {
  background: #34d399;
}

:deep(.dark) .step-dot,
.dark .step-dot {
  border-color: rgba(255, 255, 255, 0.15);
}

:deep(.dark) .progress-fill,
.dark .progress-fill {
  background: linear-gradient(90deg, #ffd67a, #ffe9ae);
}

:deep(.dark) .badge--simple,
.dark .badge--simple {
  background: rgba(52, 211, 153, 0.15);
  color: #6ee7b7;
  border-color: rgba(52, 211, 153, 0.3);
}

:deep(.dark) .badge--medium,
.dark .badge--medium {
  background: rgba(96, 165, 250, 0.12);
  color: #93bbfd;
  border-color: rgba(96, 165, 250, 0.25);
}

:deep(.dark) .badge--complex,
.dark .badge--complex {
  background: rgba(251, 191, 36, 0.12);
  color: #fcd34d;
  border-color: rgba(251, 191, 36, 0.25);
}

</style>
