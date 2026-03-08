<template>
  <header class="canvas-workspace-header">
    <div class="canvas-workspace-header__left">
      <button
        v-if="showBackButton"
        type="button"
        class="canvas-workspace-header__icon-btn"
        aria-label="Back"
        @click="emit('back')"
      >
        <ArrowLeft :size="16" />
      </button>

      <div class="canvas-workspace-header__identity">
        <div class="canvas-workspace-header__title-row">
          <h1 class="canvas-workspace-header__title">
            {{ projectName || 'Untitled canvas' }}
          </h1>
          <span class="canvas-workspace-header__version">v{{ version }}</span>
        </div>

        <div class="canvas-workspace-header__meta">
          <span
            class="canvas-workspace-header__badge"
            :class="`is-${syncStatus}`"
          >
            <span class="canvas-workspace-header__badge-dot" />
            {{ syncLabel }}
          </span>
          <span class="canvas-workspace-header__badge is-neutral">
            <component :is="modeIcon" :size="12" />
            {{ modeLabel }}
          </span>
          <span
            v-if="sessionId"
            class="canvas-workspace-header__badge is-neutral"
          >
            <Link2 :size="12" />
            {{ sessionId }}
          </span>
          <span
            v-if="elementCount !== undefined"
            class="canvas-workspace-header__badge is-neutral"
          >
            <Layers3 :size="12" />
            {{ elementCount }} elements
          </span>
        </div>
      </div>
    </div>

    <div class="canvas-workspace-header__actions">
      <button
        v-if="secondaryActionLabel"
        type="button"
        class="canvas-workspace-header__secondary-btn"
        data-testid="canvas-header-secondary"
        @click="emit('secondary-action')"
      >
        {{ secondaryActionLabel }}
      </button>
      <button
        v-if="primaryActionLabel"
        type="button"
        class="canvas-workspace-header__primary-btn"
        data-testid="canvas-header-primary"
        @click="emit('primary-action')"
      >
        {{ primaryActionLabel }}
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, Bot, Layers3, Link2, PencilLine } from 'lucide-vue-next'

import type { CanvasSyncStatus } from '@/types/canvas'

interface Props {
  projectName: string
  syncStatus: CanvasSyncStatus
  mode: 'agent' | 'manual'
  sessionId?: string | null
  version: number
  elementCount?: number
  primaryActionLabel?: string
  secondaryActionLabel?: string
  showBackButton?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  sessionId: null,
  elementCount: undefined,
  primaryActionLabel: '',
  secondaryActionLabel: '',
  showBackButton: false,
})

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'primary-action'): void
  (e: 'secondary-action'): void
}>()

const syncLabel = computed(() => {
  if (props.syncStatus === 'live') return 'Live'
  if (props.syncStatus === 'saved') return 'Saved'
  if (props.syncStatus === 'syncing') return 'Syncing'
  if (props.syncStatus === 'stale') return 'Stale'
  return 'Conflict'
})

const modeLabel = computed(() => (props.mode === 'agent' ? 'Agent' : 'Manual'))
const modeIcon = computed(() => (props.mode === 'agent' ? Bot : PencilLine))
</script>

<style scoped>
.canvas-workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.92)),
    var(--background-white-main);
  box-shadow: 0 14px 34px var(--shadow-XS);
}

.canvas-workspace-header__left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  flex: 1;
}

.canvas-workspace-header__identity {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.canvas-workspace-header__title-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  min-width: 0;
}

.canvas-workspace-header__title {
  margin: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-sans);
  font-size: 18px;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.canvas-workspace-header__version {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-tertiary);
}

.canvas-workspace-header__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.canvas-workspace-header__badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  border: 1px solid var(--border-light);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  background: var(--fill-tsp-white-main);
}

.canvas-workspace-header__badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.canvas-workspace-header__badge.is-live {
  color: var(--status-running);
  background: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.18);
}

.canvas-workspace-header__badge.is-saved {
  color: var(--function-success);
  background: var(--function-success-tsp);
  border-color: var(--function-success-border);
}

.canvas-workspace-header__badge.is-syncing {
  color: var(--text-primary);
}

.canvas-workspace-header__badge.is-stale {
  color: var(--function-warning);
  background: var(--function-warning-tsp);
  border-color: rgba(247, 144, 9, 0.18);
}

.canvas-workspace-header__badge.is-conflict {
  color: var(--function-error);
  background: var(--function-error-tsp);
  border-color: rgba(239, 68, 68, 0.18);
}

.canvas-workspace-header__badge.is-neutral {
  color: var(--text-secondary);
}

.canvas-workspace-header__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.canvas-workspace-header__icon-btn,
.canvas-workspace-header__secondary-btn,
.canvas-workspace-header__primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 38px;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.canvas-workspace-header__icon-btn {
  width: 38px;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  color: var(--text-secondary);
}

.canvas-workspace-header__icon-btn:hover,
.canvas-workspace-header__secondary-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-workspace-header__secondary-btn {
  padding: 0 var(--space-4);
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  color: var(--text-secondary);
}

.canvas-workspace-header__primary-btn {
  padding: 0 var(--space-4);
  border: 1px solid rgba(17, 24, 39, 0.18);
  background: var(--Button-primary-black);
  color: var(--text-onblack);
}

.canvas-workspace-header__primary-btn:hover {
  background: var(--button-primary-hover);
}

@media (max-width: 960px) {
  .canvas-workspace-header {
    flex-direction: column;
    align-items: stretch;
  }

  .canvas-workspace-header__actions {
    justify-content: flex-end;
  }
}
</style>
