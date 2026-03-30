<template>
  <div
    v-if="show"
    class="agent-handler-activity mb-3 rounded-xl border border-[var(--border-main)] bg-[var(--background-white-main)] dark:bg-[var(--fill-tsp-white-main)] shadow-sm overflow-hidden"
    role="status"
    :aria-label="$t('Agent activity')"
  >
    <div class="flex items-start gap-3 px-3 py-2.5 sm:px-4">
      <div
        class="mt-0.5 h-2 w-2 shrink-0 rounded-full"
        :class="pulseClass"
        aria-hidden="true"
      />
      <div class="min-w-0 flex-1 space-y-1">
        <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px] leading-snug">
          <span class="font-medium text-[var(--text-primary)]">{{ $t('Agent activity') }}</span>
          <span class="text-[var(--text-tertiary)]">·</span>
          <span class="text-[var(--text-secondary)]">
            {{
              isReceivingHeartbeats
                ? $t('Connection live')
                : $t('Waiting for heartbeats')
            }}
          </span>
          <span class="text-[var(--text-tertiary)]">·</span>
          <span
            class="text-[var(--text-tertiary)] tabular-nums"
            :title="$t('Time since last streamed agent event (not heartbeats)')"
          >
            {{ $t('Last update {seconds}s ago', { seconds: secondsSinceSubstantive }) }}
          </span>
        </div>
        <p
          v-if="isQuietButLive"
          class="text-[12px] leading-relaxed text-amber-800 dark:text-amber-200/90"
        >
          {{ $t('Long pause while connected — the model may still be drafting, summarizing, or verifying. This is normal for large reports.') }}
        </p>
      </div>
    </div>

    <div class="border-t border-[var(--border-main)]">
      <button
        type="button"
        class="flex w-full items-center justify-between gap-2 px-3 py-2 sm:px-4 text-left text-[12px] font-medium text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-gray-main)] transition-colors"
        :aria-expanded="logsExpanded"
        @click="logsExpanded = !logsExpanded"
      >
        <span class="flex items-center gap-2">
          <Server :size="14" class="shrink-0 opacity-80" aria-hidden="true" />
          {{ $t('Docker log preview (backend & sandbox)') }}
        </span>
        <ChevronDown
          :size="16"
          class="shrink-0 opacity-70 transition-transform duration-200"
          :class="{ 'rotate-180': logsExpanded }"
        />
      </button>
      <div v-if="logsExpanded" class="space-y-2 px-3 pb-3 sm:px-4">
        <p v-if="logsError" class="text-[12px] text-red-600 dark:text-red-400">{{ logsError }}</p>
        <p
          v-else-if="preview && !preview.enabled && preview.message"
          class="text-[12px] text-[var(--text-tertiary)]"
        >
          {{ preview.message }}
        </p>
        <p
          v-else-if="preview?.enabled && preview.message"
          class="text-[12px] leading-relaxed text-amber-800 dark:text-amber-200/90"
        >
          {{ preview.message }}
        </p>
        <div class="grid gap-2 sm:grid-cols-2">
          <div class="min-w-0">
            <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
              Backend
            </div>
            <pre
              class="log-pre max-h-[140px] overflow-auto rounded-lg border border-[var(--border-main)] bg-[var(--fill-tsp-gray-main)] p-2 text-[10px] leading-relaxed text-[var(--text-secondary)]"
            >{{ backendText }}</pre>
          </div>
          <div class="min-w-0">
            <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
              Sandbox
            </div>
            <pre
              class="log-pre max-h-[140px] overflow-auto rounded-lg border border-[var(--border-main)] bg-[var(--fill-tsp-gray-main)] p-2 text-[10px] leading-relaxed text-[var(--text-secondary)]"
            >{{ sandboxText }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useIntervalFn } from '@vueuse/core';
import { storeToRefs } from 'pinia';
import { ChevronDown, Server } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';

import { fetchContainerLogsPreview, type ContainerLogsPreview } from '@/api/diagnostics';
import { HANDLER_QUIET_THRESHOLD_MS } from '@/core/session/workflowTimingContract';
import { useConnectionStore } from '@/stores/connectionStore';

const props = defineProps<{
  show: boolean;
}>();

const { t } = useI18n();
const connectionStore = useConnectionStore();
const { lastRealEventTime, isReceivingHeartbeats, isLoading } = storeToRefs(connectionStore);

const clock = ref(Date.now());
useIntervalFn(
  () => {
    clock.value = Date.now();
  },
  1000,
  { immediateCallback: true },
);

const secondsSinceSubstantive = computed(() => {
  if (!lastRealEventTime.value) return 0;
  return Math.max(0, Math.floor((clock.value - lastRealEventTime.value) / 1000));
});

const isQuietButLive = computed(
  () =>
    isLoading.value &&
    isReceivingHeartbeats.value &&
    lastRealEventTime.value > 0 &&
    clock.value - lastRealEventTime.value > HANDLER_QUIET_THRESHOLD_MS,
);

const pulseClass = computed(() =>
  isReceivingHeartbeats.value
    ? 'bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.25)] animate-pulse'
    : 'bg-amber-500 animate-pulse',
);

const logsExpanded = ref(false);
const preview = ref<ContainerLogsPreview | null>(null);
const logsError = ref<string | null>(null);

const backendText = computed(() => {
  const lines = preview.value?.backend;
  if (!lines?.length) return t('No lines (container missing or preview disabled)');
  return lines.join('\n');
});

const sandboxText = computed(() => {
  const lines = preview.value?.sandbox;
  if (!lines?.length) return t('No lines (container missing or preview disabled)');
  return lines.join('\n');
});

async function loadLogs(): Promise<void> {
  logsError.value = null;
  try {
    preview.value = await fetchContainerLogsPreview();
  } catch {
    logsError.value = t('Could not load container logs.');
    preview.value = null;
  }
}

const { pause, resume } = useIntervalFn(
  () => {
    void loadLogs();
  },
  8000,
  { immediate: false },
);

watch(
  () => [props.show, logsExpanded.value] as const,
  ([visible, expanded]) => {
    if (visible && expanded) {
      void loadLogs();
      resume();
    } else {
      pause();
    }
  },
  { immediate: true },
);
</script>

<style scoped>
.log-pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
