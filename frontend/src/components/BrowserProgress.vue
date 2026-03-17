<script setup lang="ts">
import { computed } from 'vue'

import type { FetchProgressEvent } from '@/composables/useBrowserWorkflow'

interface Props {
  events?: FetchProgressEvent[]
  isStreaming?: boolean
  lastError?: string | null
}

type ProgressTone = 'idle' | 'active' | 'complete' | 'error'

const props = withDefaults(defineProps<Props>(), {
  events: () => [],
  isStreaming: false,
  lastError: null,
})

const latestEvent = computed<FetchProgressEvent | null>(() => {
  if (props.events.length === 0) {
    return null
  }
  return props.events[props.events.length - 1]
})

const suggestedMode = computed(() => {
  for (let index = props.events.length - 1; index >= 0; index -= 1) {
    const mode = props.events[index]?.suggested_mode
    if (mode) {
      return mode
    }
  }
  return null
})

const tone = computed<ProgressTone>(() => {
  if (props.lastError || latestEvent.value?.phase === 'failed') {
    return 'error'
  }
  if (latestEvent.value?.phase === 'completed') {
    return 'complete'
  }
  if (props.isStreaming) {
    return 'active'
  }
  return 'idle'
})

const statusLabel = computed(() => {
  if (latestEvent.value?.phase) {
    return formatLabel(latestEvent.value.phase)
  }
  if (props.isStreaming) {
    return 'Connecting'
  }
  return 'Idle'
})

const modeLabel = computed(() => {
  if (latestEvent.value?.mode) {
    return formatLabel(latestEvent.value.mode)
  }
  return 'Pending mode'
})

const errorMessage = computed(() => props.lastError ?? latestEvent.value?.error ?? null)

const recoveryHint = computed(() => {
  if (!suggestedMode.value) {
    return null
  }
  return `Try ${suggestedMode.value} mode next.`
})

const statusMessage = computed(() => {
  if (tone.value === 'error') {
    return 'The browser workflow needs another fetch strategy.'
  }
  if (tone.value === 'complete') {
    if (latestEvent.value?.from_cache) {
      return 'The latest response was served from cache.'
    }
    return 'The latest fetch finished successfully.'
  }
  if (tone.value === 'active') {
    return 'The browser workflow is still collecting content.'
  }
  return 'Start a fetch to see phase and delivery details.'
})

const eventCountLabel = computed(() => {
  const count = props.events.length
  return `${count} event${count === 1 ? '' : 's'}`
})

const metadataBadges = computed(() => {
  const badges: string[] = []
  if (latestEvent.value?.tier_used) {
    badges.push(`Tier ${formatLabel(latestEvent.value.tier_used)}`)
  }
  if (latestEvent.value?.from_cache) {
    badges.push('Cache hit')
  }
  if (typeof latestEvent.value?.response_time_ms === 'number') {
    badges.push(`${latestEvent.value.response_time_ms} ms`)
  }
  if (typeof latestEvent.value?.content_length === 'number') {
    badges.push(`${latestEvent.value.content_length.toLocaleString()} chars`)
  }
  return badges
})

const eventRows = computed(() =>
  props.events
    .map((event, index) => ({
      id: event.event_id ?? `${index}-${event.phase}-${event.mode ?? 'unknown'}`,
      title: formatLabel(event.phase),
      details: [
        event.mode ? formatLabel(event.mode) : null,
        event.tier_used ? event.tier_used : null,
        event.from_cache ? 'cache' : null,
        typeof event.response_time_ms === 'number' ? `${event.response_time_ms} ms` : null,
        event.error ?? null,
      ].filter((value): value is string => Boolean(value)),
    }))
    .reverse(),
)

const showSpinner = computed(() => props.isStreaming && tone.value === 'active')

function formatLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}
</script>

<template>
  <div class="browser-progress" :class="`browser-progress--${tone}`" role="status" aria-live="polite">
    <div class="browser-progress__header">
      <div>
        <p class="browser-progress__eyebrow">Browser workflow</p>
        <p class="browser-progress__status" data-testid="browser-progress-status">{{ statusLabel }}</p>
      </div>
      <span class="browser-progress__mode" data-testid="browser-progress-mode">{{ modeLabel }}</span>
    </div>

    <div class="browser-progress__hero">
      <span
        v-if="showSpinner"
        class="browser-progress__spinner"
        aria-hidden="true"
      />
      <span
        v-else
        class="browser-progress__indicator"
        aria-hidden="true"
      />

      <p class="browser-progress__message">{{ statusMessage }}</p>
    </div>

    <div v-if="metadataBadges.length > 0" class="browser-progress__meta">
      <span
        v-for="badge in metadataBadges"
        :key="badge"
        class="browser-progress__badge"
      >
        {{ badge }}
      </span>
    </div>

    <p
      v-if="errorMessage"
      class="browser-progress__error"
      data-testid="browser-progress-error"
    >
      {{ errorMessage }}
    </p>

    <p
      v-if="recoveryHint"
      class="browser-progress__recovery"
      data-testid="browser-progress-recovery"
    >
      {{ recoveryHint }}
    </p>

    <details
      v-if="eventRows.length > 0"
      class="browser-progress__log"
      data-testid="browser-progress-log"
    >
      <summary class="browser-progress__summary">
        Event log
        <span class="browser-progress__summary-count">{{ eventCountLabel }}</span>
      </summary>

      <ol class="browser-progress__list">
        <li v-for="event in eventRows" :key="event.id" class="browser-progress__item">
          <span class="browser-progress__item-title">{{ event.title }}</span>
          <span
            v-if="event.details.length > 0"
            class="browser-progress__item-details"
          >
            {{ event.details.join(' • ') }}
          </span>
        </li>
      </ol>
    </details>
  </div>
</template>

<style scoped>
.browser-progress {
  --progress-accent: var(--text-brand);
  --progress-surface: color-mix(in srgb, var(--background-surface) 82%, transparent);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid color-mix(in srgb, var(--progress-accent) 24%, var(--border-main));
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--progress-accent) 16%, transparent), transparent 48%),
    linear-gradient(180deg, color-mix(in srgb, var(--progress-surface) 72%, var(--background-surface)) 0%, var(--background-surface) 100%);
  box-shadow: 0 12px 24px color-mix(in srgb, var(--progress-accent) 10%, transparent);
}

.browser-progress--active {
  --progress-accent: var(--text-brand);
}

.browser-progress--complete {
  --progress-accent: var(--function-success);
}

.browser-progress--error {
  --progress-accent: var(--function-error);
}

.browser-progress__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.browser-progress__eyebrow {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.browser-progress__status {
  margin: var(--space-1) 0 0;
  color: var(--text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  line-height: 1.2;
}

.browser-progress__mode {
  flex-shrink: 0;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  border: 1px solid color-mix(in srgb, var(--progress-accent) 36%, transparent);
  background: color-mix(in srgb, var(--progress-accent) 12%, transparent);
  color: var(--text-primary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.browser-progress__hero {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.browser-progress__indicator,
.browser-progress__spinner {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
  border-radius: var(--radius-full);
}

.browser-progress__indicator {
  background: var(--progress-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--progress-accent) 16%, transparent);
}

.browser-progress__spinner {
  border: 2px solid color-mix(in srgb, var(--progress-accent) 20%, transparent);
  border-top-color: var(--progress-accent);
  animation: browser-progress-spin 0.9s linear infinite;
}

.browser-progress__message {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: 1.5;
}

.browser-progress__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.browser-progress__badge {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  background: var(--fill-tsp-white-main);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.browser-progress__error,
.browser-progress__recovery {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  line-height: 1.5;
}

.browser-progress__error {
  border: 1px solid color-mix(in srgb, var(--function-error) 30%, transparent);
  background: var(--function-error-tsp);
  color: var(--text-primary);
}

.browser-progress__recovery {
  border: 1px solid color-mix(in srgb, var(--progress-accent) 20%, transparent);
  background: color-mix(in srgb, var(--progress-accent) 10%, transparent);
  color: var(--text-secondary);
}

.browser-progress__log {
  border: 1px solid var(--border-main);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--background-surface) 86%, transparent);
  overflow: hidden;
}

.browser-progress__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  list-style: none;
}

.browser-progress__summary::-webkit-details-marker {
  display: none;
}

.browser-progress__summary-count {
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.browser-progress__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0 var(--space-3) var(--space-3);
  list-style: none;
}

.browser-progress__item {
  display: grid;
  gap: var(--space-1);
  padding-top: var(--space-2);
  border-top: 1px solid color-mix(in srgb, var(--border-main) 70%, transparent);
}

.browser-progress__item:first-child {
  padding-top: 0;
  border-top: 0;
}

.browser-progress__item-title {
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.browser-progress__item-details {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  line-height: 1.5;
}

@keyframes browser-progress-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
