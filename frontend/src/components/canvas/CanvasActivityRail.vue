<template>
  <aside class="canvas-activity-rail">
    <div class="canvas-activity-rail__header">
      <div>
        <div class="canvas-activity-rail__eyebrow">Canvas Activity</div>
        <h2 class="canvas-activity-rail__title">Agent workspace state</h2>
      </div>
      <span class="canvas-activity-rail__source" :class="`is-${lastSource ?? 'system'}`">
        {{ sourceLabel }}
      </span>
    </div>

    <div class="canvas-activity-rail__stats">
      <div class="canvas-activity-rail__stat">
        <span class="canvas-activity-rail__stat-label">Server version</span>
        <span class="canvas-activity-rail__stat-value">v{{ serverVersion }}</span>
      </div>
      <div class="canvas-activity-rail__stat">
        <span class="canvas-activity-rail__stat-label">Elements</span>
        <span class="canvas-activity-rail__stat-value">{{ elementCount }} elements</span>
      </div>
      <div v-if="pendingRemoteVersion !== null" class="canvas-activity-rail__stat is-pending">
        <span class="canvas-activity-rail__stat-label">Queued</span>
        <span class="canvas-activity-rail__stat-value">v{{ pendingRemoteVersion }} pending</span>
      </div>
    </div>

    <div class="canvas-activity-rail__card">
      <div class="canvas-activity-rail__card-label">Last operation</div>
      <div class="canvas-activity-rail__card-value">
        {{ lastOperation || 'Waiting for a canvas mutation' }}
      </div>
      <div class="canvas-activity-rail__subtle">
        {{ changedSummary }}
      </div>
    </div>

    <div class="canvas-activity-rail__card">
      <div class="canvas-activity-rail__card-label">Session link</div>
      <div class="canvas-activity-rail__card-value">
        {{ sessionId || 'No linked session' }}
      </div>
      <div v-if="updatedAt" class="canvas-activity-rail__subtle">
        Updated {{ formattedUpdatedAt }}
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  sessionId?: string | null
  serverVersion: number
  pendingRemoteVersion?: number | null
  elementCount: number
  lastOperation?: string | null
  lastSource?: 'agent' | 'manual' | 'system' | null
  changedElementIds?: string[]
  updatedAt?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  sessionId: null,
  pendingRemoteVersion: null,
  lastOperation: null,
  lastSource: null,
  changedElementIds: () => [],
  updatedAt: null,
})

const sourceLabel = computed(() => {
  if (props.lastSource === 'agent') return 'Agent'
  if (props.lastSource === 'manual') return 'Manual'
  return 'System'
})

const changedSummary = computed(() => {
  const changedCount = props.changedElementIds.length
  if (changedCount === 0) return 'No element-level diff metadata reported'
  if (changedCount === 1) return '1 changed element'
  return `${changedCount} changed`
})

const formattedUpdatedAt = computed(() => {
  if (!props.updatedAt) return ''
  const parsed = new Date(props.updatedAt)
  if (Number.isNaN(parsed.getTime())) return props.updatedAt
  return parsed.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  })
})
</script>

<style scoped>
.canvas-activity-rail {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.02), rgba(255, 255, 255, 0.98));
  box-shadow: 0 12px 28px var(--shadow-XS);
}

.canvas-activity-rail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.canvas-activity-rail__eyebrow {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.canvas-activity-rail__title {
  margin: 4px 0 0;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.canvas-activity-rail__source {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  border: 1px solid var(--border-light);
  background: var(--fill-tsp-white-main);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.canvas-activity-rail__source.is-agent {
  color: var(--status-running);
  background: rgba(59, 130, 246, 0.1);
}

.canvas-activity-rail__source.is-manual {
  color: var(--text-primary);
}

.canvas-activity-rail__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-2);
}

.canvas-activity-rail__stat,
.canvas-activity-rail__card {
  padding: var(--space-3);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
}

.canvas-activity-rail__stat.is-pending {
  background: rgba(247, 144, 9, 0.08);
  border-color: rgba(247, 144, 9, 0.16);
}

.canvas-activity-rail__stat-label,
.canvas-activity-rail__card-label {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.canvas-activity-rail__stat-value,
.canvas-activity-rail__card-value {
  display: block;
  margin-top: 6px;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.canvas-activity-rail__subtle {
  margin-top: 6px;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.45;
}
</style>
