<template>
  <ContentContainer :centered="isLoading || showEmpty" constrained class="generic-view">
    <LoadingState
      v-if="isLoading"
      :label="t('Tool is executing...')"
      :detail="functionName || ''"
      animation="spinner"
    />

    <div v-else class="generic-body">
      <!-- Tool name and function -->
      <div v-if="functionName" class="tool-section">
        <div class="tool-title">
          {{ t('Tool') }}: {{ functionName }}
        </div>

        <!-- Arguments -->
        <div v-if="args && Object.keys(args).length > 0" class="tool-block">
          <div class="tool-label">{{ t('Arguments') }}:</div>
          <pre class="tool-code"><code>{{ JSON.stringify(args, null, 2) }}</code></pre>
        </div>

        <!-- Result -->
        <div v-if="hasResult" class="tool-block">
          <div class="tool-label">{{ t('Result') }}:</div>
          <div class="tool-result">
            {{ typeof result === 'string' ? result : JSON.stringify(result, null, 2) }}
          </div>
        </div>

        <!-- Status indicator -->
        <div v-else class="tool-status">
          <span>{{ statusMessage }}</span>
          <LoadingDots v-if="isExecuting" />
        </div>
      </div>

      <!-- Fallback for generic content -->
      <div v-else-if="hasContent" class="tool-block">
        <div class="tool-result">
          {{ typeof content === 'string' ? content : JSON.stringify(content, null, 2) }}
        </div>
      </div>

      <EmptyState v-else message="No content available" icon="inbox" />
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import LoadingDots from '@/components/toolViews/shared/LoadingDots.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';

const props = defineProps<{
  functionName?: string;
  args?: Record<string, any>;
  result?: any;
  content?: any;
  isExecuting?: boolean;
}>();

const { t } = useI18n();

const hasResult = computed(() => props.result !== undefined && props.result !== null);
const hasContent = computed(() => props.content !== undefined && props.content !== null);
const isLoading = computed(() => !!props.isExecuting && !props.functionName && !hasContent.value && !hasResult.value);
const showEmpty = computed(() => !isLoading.value && !props.functionName && !hasContent.value && !hasResult.value);
const statusMessage = computed(() =>
  props.isExecuting ? t('Tool is executing...') : t('Waiting for result...')
);
</script>

<style scoped>
.generic-view {
  height: 100%;
}

.generic-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.tool-section {
  padding: var(--space-3) 0;
}

.tool-title {
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  margin-bottom: var(--space-2);
}

.tool-label {
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  margin-bottom: var(--space-2);
}

.tool-block {
  margin-bottom: var(--space-4);
}

.tool-code {
  background: var(--fill-tsp-gray-main);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow-x: auto;
}

.tool-result {
  background: var(--fill-tsp-gray-main);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.tool-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}
</style>
