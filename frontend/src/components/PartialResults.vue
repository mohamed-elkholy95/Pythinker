<script setup lang="ts">
interface PartialResult {
  stepIndex: number
  stepTitle: string
  headline: string
  sourcesCount: number
}

defineProps<{
  results: PartialResult[]
}>()
</script>

<template>
  <div v-if="results.length" class="partial-results">
    <div class="partial-results-header">Findings so far</div>
    <ul class="partial-results-list">
      <li v-for="r in results" :key="r.stepIndex" class="partial-result-item">
        <span class="result-headline">{{ r.headline }}</span>
        <span v-if="r.sourcesCount" class="result-sources">{{ r.sourcesCount }} sources</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.partial-results {
  padding: 0.5rem 0.75rem;
  margin: 0.5rem 0;
  border-left: 2px solid var(--status-running, #3b82f6);
  background: var(--background-surface, #f8fafc);
  border-radius: 0 0.375rem 0.375rem 0;
  font-size: 0.8125rem;
}

.partial-results-header {
  font-weight: 600;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.6;
  margin-bottom: 0.375rem;
}

.partial-results-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.partial-result-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}

.result-headline {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-sources {
  flex-shrink: 0;
  opacity: 0.5;
  font-size: 0.75rem;
}
</style>
