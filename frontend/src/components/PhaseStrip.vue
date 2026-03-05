<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'

type Phase = 'planning' | 'verifying' | 'searching' | 'writing' | 'done'

interface Props {
  currentPhase: Phase
  startTime: number
  stepProgress: { current: number; total: number } | null
}

const props = defineProps<Props>()

const PHASES: { key: Phase; label: string }[] = [
  { key: 'planning', label: 'Planning' },
  { key: 'verifying', label: 'Verifying' },
  { key: 'searching', label: 'Searching' },
  { key: 'writing', label: 'Writing' },
  { key: 'done', label: 'Done' },
]

const phaseIndex = (phase: Phase): number =>
  PHASES.findIndex(p => p.key === phase)

const phaseStatus = (phase: Phase): 'completed' | 'active' | 'pending' => {
  const current = phaseIndex(props.currentPhase)
  const target = phaseIndex(phase)
  if (target < current) return 'completed'
  if (target === current) return 'active'
  return 'pending'
}

// Elapsed time ticker
const elapsedSeconds = ref(Math.floor((Date.now() - props.startTime) / 1000))

const tick = () => {
  elapsedSeconds.value = Math.floor((Date.now() - props.startTime) / 1000)
}

const timer = setInterval(tick, 1000)
onBeforeUnmount(() => clearInterval(timer))

const formattedElapsed = computed(() => {
  const s = elapsedSeconds.value
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  return `${m}m ${rem}s`
})

// Accessibility: progress value (0-100) based on phase index
const ariaValue = computed(() => {
  const idx = phaseIndex(props.currentPhase)
  return Math.round((idx / (PHASES.length - 1)) * 100)
})
</script>

<template>
  <div
    class="phase-strip"
    role="progressbar"
    :aria-valuenow="ariaValue"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-label="`Agent progress: ${currentPhase}`"
  >
    <div class="phase-strip__phases">
      <template v-for="(phase, idx) in PHASES" :key="phase.key">
        <!-- Connector line between dots -->
        <div
          v-if="idx > 0"
          class="phase-strip__connector"
          :class="{
            'phase-strip__connector--completed': phaseIndex(currentPhase) >= idx,
          }"
        />

        <!-- Phase dot + label -->
        <div
          class="phase-strip__item"
          :class="{
            'phase--completed': phaseStatus(phase.key) === 'completed',
            'phase--active': phaseStatus(phase.key) === 'active',
            'phase--pending': phaseStatus(phase.key) === 'pending',
          }"
          :data-phase="phase.key"
        >
          <span class="phase-strip__dot" />
          <span class="phase-strip__label">{{ phase.label }}</span>
        </div>
      </template>
    </div>

    <div class="phase-strip__meta">
      <span
        v-if="stepProgress"
        class="phase-strip__steps"
      >
        {{ stepProgress.current }} / {{ stepProgress.total }}
      </span>
      <span class="phase-strip__elapsed">{{ formattedElapsed }}</span>
    </div>
  </div>
</template>

<style scoped>
.phase-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 14px;
  border-bottom: 1px solid var(--border-main);
  background: var(--background-surface);
  font-family: var(--font-sans, sans-serif);
  user-select: none;
}

/* --- Phase row --- */
.phase-strip__phases {
  display: flex;
  align-items: center;
  gap: 0;
}

/* --- Individual phase item --- */
.phase-strip__item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* --- Dot --- */
.phase-strip__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background-color 0.25s ease;
}

.phase--pending .phase-strip__dot {
  background-color: var(--text-tertiary);
  opacity: 0.4;
}

.phase--active .phase-strip__dot {
  background-color: var(--status-running);
  animation: pulse-dot 1.5s ease-in-out infinite;
}

.phase--completed .phase-strip__dot {
  background-color: var(--function-success);
}

/* --- Label --- */
.phase-strip__label {
  font-size: 0.75rem;
  line-height: 1;
  white-space: nowrap;
}

.phase--pending .phase-strip__label {
  color: var(--text-tertiary);
}

.phase--active .phase-strip__label {
  color: var(--text-primary);
  font-weight: var(--font-semibold, 600);
}

.phase--completed .phase-strip__label {
  color: var(--text-secondary);
}

/* --- Connector line --- */
.phase-strip__connector {
  width: 16px;
  height: 1px;
  margin: 0 4px;
  flex-shrink: 0;
  background-color: var(--text-tertiary);
  opacity: 0.3;
  transition: background-color 0.25s ease, opacity 0.25s ease;
}

.phase-strip__connector--completed {
  background-color: var(--function-success);
  opacity: 0.6;
}

/* --- Right-side meta --- */
.phase-strip__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.phase-strip__steps,
.phase-strip__elapsed {
  font-size: 0.75rem;
  line-height: 1;
  color: var(--text-secondary);
  white-space: nowrap;
}

.phase-strip__steps {
  font-weight: var(--font-medium, 500);
}

/* --- Pulse animation --- */
@keyframes pulse-dot {
  0%,
  100% {
    box-shadow: 0 0 0 0 var(--status-running);
    opacity: 1;
  }
  50% {
    box-shadow: 0 0 0 4px transparent;
    opacity: 0.7;
  }
}
</style>
