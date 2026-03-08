<template>
  <div class="canvas-sync-banner" :class="`is-${status}`">
    <div class="canvas-sync-banner__body">
      <div class="canvas-sync-banner__icon">
        <RefreshCcw v-if="status === 'syncing'" :size="14" />
        <AlertTriangle v-else-if="status === 'stale'" :size="14" />
        <ShieldAlert v-else-if="status === 'conflict'" :size="14" />
        <CheckCircle2 v-else :size="14" />
      </div>
      <div class="canvas-sync-banner__copy">
        <div class="canvas-sync-banner__title">{{ title }}</div>
        <div v-if="description" class="canvas-sync-banner__description">{{ description }}</div>
      </div>
    </div>

    <div class="canvas-sync-banner__actions">
      <button
        v-if="secondaryActionLabel"
        type="button"
        class="canvas-sync-banner__secondary-btn"
        data-testid="canvas-sync-secondary"
        @click="emit('secondary-action')"
      >
        {{ secondaryActionLabel }}
      </button>
      <button
        v-if="primaryActionLabel"
        type="button"
        class="canvas-sync-banner__primary-btn"
        data-testid="canvas-sync-primary"
        @click="emit('primary-action')"
      >
        {{ primaryActionLabel }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { AlertTriangle, CheckCircle2, RefreshCcw, ShieldAlert } from 'lucide-vue-next'

import type { CanvasSyncStatus } from '@/types/canvas'

interface Props {
  status: Extract<CanvasSyncStatus, 'saved' | 'syncing' | 'stale' | 'conflict'>
  title: string
  description?: string
  primaryActionLabel?: string
  secondaryActionLabel?: string
}

withDefaults(defineProps<Props>(), {
  description: '',
  primaryActionLabel: '',
  secondaryActionLabel: '',
})

const emit = defineEmits<{
  (e: 'primary-action'): void
  (e: 'secondary-action'): void
}>()
</script>

<style scoped>
.canvas-sync-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
}

.canvas-sync-banner__body {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  min-width: 0;
  flex: 1;
}

.canvas-sync-banner__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.canvas-sync-banner__copy {
  min-width: 0;
}

.canvas-sync-banner__title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.canvas-sync-banner__description {
  margin-top: 2px;
  font-size: var(--text-sm);
  line-height: 1.45;
  color: var(--text-secondary);
}

.canvas-sync-banner__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.canvas-sync-banner__primary-btn,
.canvas-sync-banner__secondary-btn {
  min-height: 34px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.canvas-sync-banner__secondary-btn {
  background: transparent;
  color: var(--text-secondary);
}

.canvas-sync-banner__secondary-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-sync-banner__primary-btn {
  background: var(--Button-primary-black);
  color: var(--text-onblack);
}

.canvas-sync-banner__primary-btn:hover {
  background: var(--button-primary-hover);
}

.canvas-sync-banner.is-saved {
  background: linear-gradient(180deg, rgba(34, 197, 94, 0.08), rgba(255, 255, 255, 0.96));
  border-color: rgba(34, 197, 94, 0.18);
}

.canvas-sync-banner.is-saved .canvas-sync-banner__icon {
  color: var(--function-success);
  background: var(--function-success-tsp);
}

.canvas-sync-banner.is-syncing {
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.04), rgba(255, 255, 255, 0.98));
}

.canvas-sync-banner.is-syncing .canvas-sync-banner__icon {
  color: var(--text-primary);
  background: var(--fill-tsp-gray-main);
}

.canvas-sync-banner.is-stale {
  background: linear-gradient(180deg, rgba(247, 144, 9, 0.12), rgba(255, 255, 255, 0.98));
  border-color: rgba(247, 144, 9, 0.18);
}

.canvas-sync-banner.is-stale .canvas-sync-banner__icon {
  color: var(--function-warning);
  background: rgba(247, 144, 9, 0.14);
}

.canvas-sync-banner.is-conflict {
  background: linear-gradient(180deg, rgba(239, 68, 68, 0.1), rgba(255, 255, 255, 0.98));
  border-color: rgba(239, 68, 68, 0.18);
}

.canvas-sync-banner.is-conflict .canvas-sync-banner__icon {
  color: var(--function-error);
  background: var(--function-error-tsp);
}

@media (max-width: 960px) {
  .canvas-sync-banner {
    flex-direction: column;
    align-items: stretch;
  }

  .canvas-sync-banner__actions {
    justify-content: flex-end;
  }
}
</style>
