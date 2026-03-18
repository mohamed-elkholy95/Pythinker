<template>
  <div class="research-phase" :class="{ compact }" role="status" aria-live="polite">
    <div class="phase-header" v-if="!compact">
      <span class="phase-label">Research Phase</span>
      <span class="phase-current">{{ currentLabel }}</span>
    </div>

    <div class="phase-track" :aria-label="`Current phase: ${currentLabel}`">
      <div
        v-for="(step, index) in phaseSteps"
        :key="step.key"
        class="phase-step"
        :class="stepClass(index)"
      >
        <span class="step-dot" />
        <span class="step-text">{{ step.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface PhaseStep {
  key: string
  label: string
}

const props = withDefaults(defineProps<{
  phase?: string | null
  compact?: boolean
}>(), {
  phase: null,
  compact: false,
})

const NORMALIZED_LABELS: Record<string, string> = {
  planning: 'Planning',
  executing: 'Executing',
  summarizing: 'Summarizing',
  completed: 'Completed',
  compilation: 'Compiling',
  phase_1: 'Phase 1',
  phase_2: 'Phase 2',
  phase_3: 'Phase 3',
}

const defaultSteps: PhaseStep[] = [
  { key: 'planning', label: 'Planning' },
  { key: 'executing', label: 'Executing' },
  { key: 'summarizing', label: 'Summarizing' },
  { key: 'completed', label: 'Complete' },
]

const phasedSteps: PhaseStep[] = [
  { key: 'phase_1', label: 'Phase 1' },
  { key: 'phase_2', label: 'Phase 2' },
  { key: 'phase_3', label: 'Phase 3' },
  { key: 'compilation', label: 'Compile' },
]

const normalizedPhase = computed(() => {
  if (!props.phase) return 'planning'
  if (props.phase === 'query_started' || props.phase === 'query_completed' || props.phase === 'query_skipped') {
    return 'executing'
  }
  if (props.phase === 'started') {
    return 'executing'
  }
  return props.phase
})

const phaseSteps = computed(() => {
  if (normalizedPhase.value.startsWith('phase_') || normalizedPhase.value === 'compilation') {
    return phasedSteps
  }
  return defaultSteps
})

const currentLabel = computed(() => {
  if (normalizedPhase.value in NORMALIZED_LABELS) {
    return NORMALIZED_LABELS[normalizedPhase.value]
  }
  return normalizedPhase.value
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
})

const currentIndex = computed(() => {
  const idx = phaseSteps.value.findIndex((step) => step.key === normalizedPhase.value)
  if (idx >= 0) return idx
  if (normalizedPhase.value === 'completed') return phaseSteps.value.length - 1
  return 0
})

const stepClass = (index: number) => ({
  complete: index < currentIndex.value,
  active: index === currentIndex.value,
})
</script>

<style scoped>
.research-phase {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-main);
}

.research-phase.compact {
  padding: var(--space-2);
  gap: var(--space-1);
}

.phase-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
}

.phase-label {
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.phase-current {
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.phase-track {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-2);
}

.phase-step {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--text-muted);
  min-width: 0;
}

.step-dot {
  width: 7px;
  height: 7px;
  border-radius: var(--radius-full);
  background: var(--border-main);
  flex-shrink: 0;
}

.step-text {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.phase-step.active {
  color: var(--text-primary);
}

.phase-step.active .step-dot {
  background: var(--text-brand);
}

.phase-step.complete {
  color: var(--text-secondary);
}

.phase-step.complete .step-dot {
  background: var(--function-success);
}
</style>
