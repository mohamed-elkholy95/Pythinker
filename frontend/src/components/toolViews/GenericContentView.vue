<template>
  <ContentContainer :centered="isLoading || showEmpty" constrained class="generic-view">
    <LoadingState
      v-if="isLoading"
      :label="t('Tool is executing...')"
      :detail="toolDisplayLabel"
      animation="spinner"
    />
    <ErrorState
      v-else-if="errorMessage"
      :error="errorMessage"
    />

    <div v-else class="generic-body">
      <CanvasMiniPreview
        v-if="isCanvasTool"
        :project-id="canvasProjectId"
        :project-name="canvasProjectName"
        :operation="canvasOperation"
        :element-count="canvasElementCount"
      />

      <!-- Tool name and function -->
      <div v-if="toolDisplayLabel" class="tool-section">
        <div class="tool-title">
          {{ t('Tool') }}: {{ toolDisplayLabel }}
        </div>

        <!-- Arguments -->
        <div v-if="args && Object.keys(args).length > 0" class="tool-block">
          <div class="tool-label">{{ t('Arguments') }}:</div>
          <div class="tool-code" v-html="highlightedArgs"></div>
        </div>

        <!-- Result -->
        <div v-if="hasResult" class="tool-block">
          <div class="tool-label">{{ t('Result') }}:</div>
          <div class="tool-result" v-html="highlightedResult"></div>
        </div>

        <!-- Status indicator -->
        <div v-else class="tool-status">
          <span>{{ statusMessage }}</span>
          <LoadingDots v-if="isExecuting" />
        </div>
      </div>

      <!-- Fallback for generic content -->
      <div v-else-if="hasContent" class="tool-block">
        <div class="tool-result" v-html="highlightedContent"></div>
      </div>

      <EmptyState v-else message="No content available" icon="inbox" />
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import ErrorState from '@/components/toolViews/shared/ErrorState.vue';
import LoadingDots from '@/components/toolViews/shared/LoadingDots.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import CanvasMiniPreview from '@/components/canvas/CanvasMiniPreview.vue';
import { useShiki } from '@/composables/useShiki';
import { getToolDisplay } from '@/utils/toolDisplay';
import type { CanvasToolContent } from '@/types/toolContent';

/** Structured tool result — string, JSON object, array, or null. */
export type ToolResultValue = string | Record<string, unknown> | unknown[] | null;

const props = defineProps<{
  toolName?: string;
  functionName?: string;
  args?: Record<string, unknown>;
  status?: 'calling' | 'running' | 'called' | 'interrupted';
  result?: ToolResultValue;
  content?: ToolResultValue | CanvasToolContent;
  error?: string;
  isExecuting?: boolean;
}>();

const { t } = useI18n();
const { highlightDualTheme } = useShiki();

// Highlighted content refs
const highlightedArgs = ref('');
const highlightedResult = ref('');
const highlightedContent = ref('');

// Helper to format and highlight JSON
async function highlightJson(data: unknown): Promise<string> {
  if (data === undefined || data === null) return '';

  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);

  // Check if it looks like JSON
  const isJson = typeof data !== 'string' || text.trim().startsWith('{') || text.trim().startsWith('[');

  if (isJson) {
    try {
      const highlighted = await highlightDualTheme(text, 'json');
      return highlighted;
    } catch {
      return escapeHtml(text);
    }
  }

  return escapeHtml(text);
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Update highlighted content when props change
watch(
  () => props.args,
  async (args) => {
    if (args && Object.keys(args).length > 0) {
      highlightedArgs.value = await highlightJson(args);
    }
  },
  { immediate: true }
);

watch(
  () => props.result,
  async (result) => {
    if (result !== undefined && result !== null) {
      highlightedResult.value = await highlightJson(result);
    }
  },
  { immediate: true }
);

watch(
  () => props.content,
  async (content) => {
    if (content !== undefined && content !== null) {
      highlightedContent.value = await highlightJson(content);
    }
  },
  { immediate: true }
);

const toolDisplay = computed(() => getToolDisplay({
  name: props.toolName,
  function: props.functionName,
  args: props.args
}));

const toolDisplayLabel = computed(() => {
  if (!props.functionName && !props.toolName) return '';
  return `${toolDisplay.value.displayName} · ${toolDisplay.value.actionLabel}`;
});

const isCanvasTool = computed(() => {
  if (props.toolName === 'canvas') return true;
  return !!props.functionName && props.functionName.startsWith('canvas_');
});

const canvasContent = computed(() => {
  return (props.content as CanvasToolContent | undefined) || undefined;
});

const canvasOperation = computed(() => {
  if (canvasContent.value?.operation) return canvasContent.value.operation;
  return props.functionName || '';
});

const canvasProjectId = computed(() => {
  const fromContent = canvasContent.value?.project_id;
  if (fromContent) return fromContent;
  const argId = props.args?.project_id;
  return typeof argId === 'string' ? argId : null;
});

const canvasProjectName = computed(() => {
  const fromContent = canvasContent.value?.project_name;
  if (fromContent) return fromContent;
  const argName = props.args?.name;
  return typeof argName === 'string' ? argName : null;
});

const canvasElementCount = computed(() => {
  if (typeof canvasContent.value?.element_count === 'number') {
    return canvasContent.value.element_count;
  }
  return 0;
});

const hasResult = computed(() => props.result !== undefined && props.result !== null);
const hasContent = computed(() => props.content !== undefined && props.content !== null);
const errorMessage = computed(() => {
  if (props.error) return props.error;
  const candidate = props.result ?? props.content;
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
    return '';
  }
  const withError = candidate as { error?: unknown; message?: unknown };
  if (typeof withError.error === 'string' && withError.error.trim().length > 0) {
    return withError.error;
  }
  if (typeof withError.message === 'string' && withError.message.trim().length > 0) {
    return withError.message;
  }
  return '';
});
const isLoading = computed(() => !!props.isExecuting && !toolDisplayLabel.value && !hasContent.value && !hasResult.value);
const showEmpty = computed(() =>
  !isLoading.value && !errorMessage.value && !toolDisplayLabel.value && !hasContent.value && !hasResult.value
);
const statusMessage = computed(() => {
  if (props.status === 'interrupted') return t('Tool execution was interrupted');
  if (props.isExecuting) return t('Tool is executing...');
  if (props.status === 'called') return t('Completed');
  return t('Waiting for result...');
});
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

.tool-code :deep(pre) {
  margin: 0;
  padding: 0;
  background: transparent !important;
}

.tool-code :deep(code) {
  font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace;
  font-size: var(--text-xs);
  line-height: 1.5;
}

/* Dark theme Shiki support */
:global(.dark) .tool-code :deep(span) {
  color: var(--shiki-dark) !important;
}

.tool-result {
  background: var(--fill-tsp-gray-main);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.tool-result :deep(pre) {
  margin: 0;
  padding: 0;
  background: transparent !important;
}

.tool-result :deep(code) {
  font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace;
  font-size: var(--text-sm);
  line-height: 1.5;
}

/* Dark theme Shiki support */
:global(.dark) .tool-result :deep(span) {
  color: var(--shiki-dark) !important;
}

.tool-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}
</style>
