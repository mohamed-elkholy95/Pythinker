<template>
  <div class="deep-research-card" :class="{ 'is-expanded': isExpanded }">
    <!-- Header -->
    <div class="research-header" @click="toggleExpand">
      <div class="research-icon">
        <Search v-if="isPending || isAwaitingApproval" :size="18" />
        <Loader2 v-else-if="isSearching" :size="18" class="animate-spin" />
        <CheckCircle2 v-else-if="isCompleted" :size="18" />
        <XCircle v-else-if="isCancelled" :size="18" />
      </div>

      <div class="research-info">
        <span class="research-title">Deep Research</span>
        <span class="research-subtitle">{{ statusText }}</span>
      </div>

      <!-- Progress Pill -->
      <div class="progress-pill">
        <span class="completed-count">{{ content.completed_count }}</span>
        <span class="divider">/</span>
        <span class="total-count">{{ content.total_count }}</span>
      </div>

      <!-- Run Button (when awaiting approval) -->
      <RunButtonDropdown
        v-if="isAwaitingApproval"
        :auto-run="content.auto_run"
        @run="handleRun"
        @toggle-auto-run="handleToggleAutoRun"
      />

      <!-- Skip All Button (when searching) -->
      <button
        v-if="isSearching"
        @click.stop="handleSkipAll"
        class="skip-btn"
      >
        Skip All
      </button>

      <ChevronDown
        :size="18"
        class="expand-icon"
        :class="{ 'rotate-180': isExpanded }"
      />
    </div>

    <div class="workflow-meta">
      <ResearchPhaseIndicator :phase="phaseForIndicator" compact />
      <div v-if="content.latest_reflection" class="reflection-note">
        <span class="reflection-label">Learned:</span>
        <span class="reflection-text">{{ content.latest_reflection.learned }}</span>
      </div>
    </div>

    <!-- Expandable Query List -->
    <Transition name="expand">
      <div v-if="isExpanded" class="query-list">
        <DeepResearchQueryItem
          v-for="(query, index) in content.queries"
          :key="query.id"
          :query="query"
          :index="index"
          :is-last="index === content.queries.length - 1"
          :can-skip="query.status === 'pending' || query.status === 'searching'"
          @skip="handleSkipQuery"
        />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, Loader2, CheckCircle2, XCircle, ChevronDown } from 'lucide-vue-next'
import RunButtonDropdown from './RunButtonDropdown.vue'
import DeepResearchQueryItem from './DeepResearchQueryItem.vue'
import ResearchPhaseIndicator from '@/components/research/ResearchPhaseIndicator.vue'
import type { DeepResearchContent } from '@/types/message'

interface Props {
  content: DeepResearchContent
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'run', researchId: string): void
  (e: 'skip', researchId: string, queryId?: string): void
  (e: 'toggle-auto-run'): void
}>()

const isExpanded = ref(false)

// Status computed properties
const isPending = computed(() => props.content.status === 'pending')
const isAwaitingApproval = computed(() => props.content.status === 'awaiting_approval')
const isSearching = computed(() =>
  props.content.status === 'started' ||
  props.content.status === 'query_started' ||
  props.content.status === 'query_completed' ||
  props.content.status === 'query_skipped'
)
const isCompleted = computed(() => props.content.status === 'completed')
const isCancelled = computed(() => props.content.status === 'cancelled')

const phaseForIndicator = computed(() => {
  if (props.content.phase) return props.content.phase
  if (isPending.value || isAwaitingApproval.value) return 'planning'
  if (isSearching.value) return 'executing'
  if (isCompleted.value) return 'completed'
  return 'summarizing'
})

// Status text
const statusText = computed(() => {
  switch (props.content.status) {
    case 'pending':
      return 'Preparing queries...'
    case 'awaiting_approval':
      return 'Waiting for approval'
    case 'started':
    case 'query_started':
    case 'query_completed':
    case 'query_skipped':
      return `Searching... (${props.content.completed_count}/${props.content.total_count})`
    case 'completed':
      return 'Research completed'
    case 'cancelled':
      return 'Cancelled'
    default:
      return ''
  }
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const handleRun = () => {
  emit('run', props.content.research_id)
}

const handleSkipQuery = (queryId: string) => {
  emit('skip', props.content.research_id, queryId)
}

const handleSkipAll = () => {
  emit('skip', props.content.research_id)
}

const handleToggleAutoRun = () => {
  emit('toggle-auto-run')
}
</script>

<style scoped>
.deep-research-card {
  background: var(--bolt-elements-bg-depth-1);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 14px;
  overflow: hidden;
  transition: all 0.2s ease;
}

.deep-research-card:hover {
  border-color: var(--bolt-elements-borderColorActive);
}

/* Header */
.research-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.research-header:hover {
  background: var(--bolt-elements-bg-depth-2);
}

.research-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--bolt-elements-item-backgroundAccent);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bolt-elements-item-contentAccent);
}

.research-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.research-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
}

.research-subtitle {
  font-size: 12px;
  color: var(--bolt-elements-textSecondary);
}

/* Progress pill */
.progress-pill {
  display: flex;
  align-items: baseline;
  gap: 2px;
  padding: 6px 12px;
  background: var(--bolt-elements-bg-depth-4);
  border-radius: 20px;
}

.completed-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
  font-variant-numeric: tabular-nums;
}

.divider {
  font-size: 11px;
  color: var(--bolt-elements-textTertiary);
}

.total-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--bolt-elements-textSecondary);
  font-variant-numeric: tabular-nums;
}

/* Skip button */
.skip-btn {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  background: var(--bolt-elements-bg-depth-3);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.skip-btn:hover {
  background: var(--bolt-elements-bg-depth-4);
  border-color: var(--bolt-elements-borderColorActive);
  color: var(--bolt-elements-textPrimary);
}

/* Expand icon */
.expand-icon {
  flex-shrink: 0;
  color: var(--bolt-elements-textTertiary);
  transition: transform 0.2s ease;
}

.expand-icon.rotate-180 {
  transform: rotate(180deg);
}

/* Query list */
.query-list {
  padding: 0 16px 16px;
  border-top: 1px solid var(--bolt-elements-borderColor);
  margin-top: -1px;
  padding-top: 14px;
}

.workflow-meta {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: 0 var(--space-4) var(--space-3);
}

.reflection-note {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.reflection-label {
  color: var(--text-tertiary);
  font-weight: var(--font-medium);
}

.reflection-text {
  color: var(--text-secondary);
}

/* Expand transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 500px;
}

/* Spin animation */
.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
