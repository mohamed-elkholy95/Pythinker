<script setup lang="ts">
import { Zap, Globe } from 'lucide-vue-next';
import type { ResearchMode } from '../api/agent';

const props = defineProps<{
  mode: ResearchMode | null;
}>();
</script>

<template>
  <span
    v-if="props.mode"
    class="research-mode-badge"
    :class="props.mode === 'fast_search' ? 'badge-fast' : 'badge-deep'"
  >
    <Zap v-if="props.mode === 'fast_search'" :size="12" />
    <Globe v-else :size="12" />
    <span class="badge-label">
      {{ props.mode === 'fast_search' ? 'Fast Search' : 'Deep Research' }}
    </span>
  </span>
</template>

<style scoped>
.research-mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  line-height: 16px;
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-fast {
  background: rgba(59, 130, 246, 0.1);
  color: var(--status-running, #3b82f6);
}

.badge-deep {
  background: rgba(16, 185, 129, 0.1);
  color: var(--status-success, #10b981);
}

.badge-label {
  letter-spacing: 0.01em;
}
</style>
