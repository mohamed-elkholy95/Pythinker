<template>
  <div class="w-full h-full overflow-y-auto">
    <div class="max-w-[640px] mx-auto px-4 py-3">
      <!-- Tool name and function -->
      <div v-if="functionName" class="py-3 pt-0">
        <div class="text-[var(--text-primary)] text-sm font-medium mb-2">
          {{ t('Tool') }}: {{ functionName }}
        </div>

        <!-- Arguments -->
        <div v-if="args && Object.keys(args).length > 0" class="mb-4">
          <div class="text-[var(--text-primary)] text-sm font-medium mb-2">{{ t('Arguments') }}:</div>
          <pre class="bg-[var(--fill-tsp-gray-main)] rounded-lg p-3 text-xs text-[var(--text-secondary)] overflow-x-auto"><code>{{ JSON.stringify(args, null, 2) }}</code></pre>
        </div>

        <!-- Result -->
        <div v-if="result" class="mb-4">
          <div class="text-[var(--text-primary)] text-sm font-medium mb-2">{{ t('Result') }}:</div>
          <div class="bg-[var(--fill-tsp-gray-main)] rounded-lg p-3 text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
            {{ typeof result === 'string' ? result : JSON.stringify(result, null, 2) }}
          </div>
        </div>

        <!-- Status indicator -->
        <div v-else class="text-[var(--text-tertiary)] text-sm">
          {{ isExecuting ? t('Tool is executing...') : t('Waiting for result...') }}
        </div>
      </div>

      <!-- Fallback for generic content -->
      <div v-else-if="content" class="py-3">
        <div class="bg-[var(--fill-tsp-gray-main)] rounded-lg p-3 text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
          {{ typeof content === 'string' ? content : JSON.stringify(content, null, 2) }}
        </div>
      </div>

      <div v-else class="text-[var(--text-tertiary)] text-sm text-center py-8">
        No content available
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

defineProps<{
  functionName?: string;
  args?: Record<string, any>;
  result?: any;
  content?: any;
  isExecuting?: boolean;
}>();

const { t } = useI18n();
</script>
