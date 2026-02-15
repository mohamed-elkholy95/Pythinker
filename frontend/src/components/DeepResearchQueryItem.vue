<template>
  <div class="query-item" :class="statusClass">
    <!-- Connector line -->
    <div v-if="!isLast" class="query-connector" :class="{ 'connector-active': isCompleted }"></div>

    <!-- Status indicator -->
    <div class="query-indicator">
      <div v-if="isCompleted" class="indicator-complete">
        <Check class="w-3 h-3 text-white" :stroke-width="3" />
      </div>
      <div v-else-if="isSearching" class="indicator-searching"></div>
      <div v-else-if="isSkipped" class="indicator-skipped">
        <Minus class="w-3 h-3" />
      </div>
      <div v-else-if="isFailed" class="indicator-failed">
        <X class="w-3 h-3" />
      </div>
      <div v-else class="indicator-pending">
        <span class="text-[10px] font-medium">{{ index + 1 }}</span>
      </div>
    </div>

    <!-- Query text -->
    <span class="query-text">{{ query.query }}</span>

    <!-- Skip button -->
    <button
      v-if="canSkip"
      @click.stop="$emit('skip', query.id)"
      class="skip-btn-sm"
    >
      Skip
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, Minus, X } from 'lucide-vue-next'
import type { DeepResearchQuery } from '@/types/message'

interface Props {
  query: DeepResearchQuery
  index: number
  isLast?: boolean
  canSkip?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isLast: false,
  canSkip: false
})

defineEmits<{
  (e: 'skip', queryId: string): void
}>()

const isCompleted = computed(() => props.query.status === 'completed')
const isSearching = computed(() => props.query.status === 'searching')
const isSkipped = computed(() => props.query.status === 'skipped')
const isFailed = computed(() => props.query.status === 'failed')
const isPending = computed(() => props.query.status === 'pending')

const statusClass = computed(() => ({
  'query-completed': isCompleted.value,
  'query-searching': isSearching.value,
  'query-skipped': isSkipped.value,
  'query-failed': isFailed.value,
  'query-pending': isPending.value
}))
</script>

<style scoped>
.query-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 0;
  position: relative;
}

.query-item:first-child {
  padding-top: 0;
}

.query-item:last-child {
  padding-bottom: 0;
}

/* Connector line */
.query-connector {
  position: absolute;
  left: 11px;
  top: 28px;
  bottom: -8px;
  width: 2px;
  background: var(--bolt-elements-borderColor);
  border-radius: 1px;
}

.query-connector.connector-active {
  background: linear-gradient(to bottom, var(--function-success), var(--bolt-elements-borderColor));
}

/* Indicators */
.query-indicator {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
}

.indicator-complete {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(34, 197, 94, 0.3);
}

.indicator-searching {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #000000 0%, #1a1a1a 100%);
  box-shadow:
    0 0 0 3px rgba(0, 0, 0, 0.12),
    0 2px 8px rgba(0, 0, 0, 0.3);
  animation: search-pulse 1.5s ease-in-out infinite;
}

@keyframes search-pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow:
      0 0 0 3px rgba(59, 130, 246, 0.12),
      0 2px 8px rgba(59, 130, 246, 0.3);
  }
  50% {
    transform: scale(1.05);
    box-shadow:
      0 0 0 5px rgba(59, 130, 246, 0.08),
      0 4px 12px rgba(59, 130, 246, 0.25);
  }
}

.indicator-skipped {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bolt-elements-bg-depth-3);
  border: 2px solid var(--bolt-elements-borderColor);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bolt-elements-textTertiary);
}

.indicator-failed {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.3);
}

.indicator-pending {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bolt-elements-textTertiary);
}

/* Query text */
.query-text {
  font-size: 14px;
  line-height: 1.5;
  padding-top: 2px;
  flex: 1;
  min-width: 0;
}

.query-completed .query-text {
  color: var(--bolt-elements-textSecondary);
}

.query-searching .query-text {
  color: var(--bolt-elements-textPrimary);
  font-weight: 500;
}

.query-skipped .query-text {
  color: var(--bolt-elements-textTertiary);
  text-decoration: line-through;
}

.query-failed .query-text {
  color: var(--bolt-elements-textTertiary);
}

.query-pending .query-text {
  color: var(--bolt-elements-textTertiary);
}

/* Skip button */
.skip-btn-sm {
  flex-shrink: 0;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  background: var(--bolt-elements-bg-depth-3);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  opacity: 0;
}

.query-item:hover .skip-btn-sm {
  opacity: 1;
}

.skip-btn-sm:hover {
  background: var(--bolt-elements-bg-depth-4);
  border-color: var(--bolt-elements-borderColorActive);
  color: var(--bolt-elements-textPrimary);
}
</style>
