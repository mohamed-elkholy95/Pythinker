<template>
  <div class="step-compact" :class="{ 'step-compact--has-connector': showBottomConnector }">
    <!-- Compact header: icon + title + chevron (same as regular steps) -->
    <div class="step-compact-header" @click="toggleExpanded">
      <!-- Status icon -->
      <div v-if="isCompleted" class="step-compact-icon step-compact-icon--done">
        <CheckIcon :size="10" :stroke-width="2.5" />
      </div>
      <div v-else-if="isFailed" class="step-compact-icon step-compact-icon--failed">
        <XIcon :size="10" :stroke-width="2.5" />
      </div>
      <div v-else class="step-compact-icon step-compact-icon--running">
        <span class="step-running-dot" aria-hidden="true"></span>
      </div>

      <!-- Title -->
      <span class="step-compact-title">Finalizing Report</span>

      <!-- Chevron -->
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        class="step-compact-chevron"
        :class="{ 'rotate-180': isExpanded }">
        <path d="m6 9 6 6 6-6"></path>
      </svg>
    </div>

    <!-- Sub-stages (collapsible) -->
    <div
      class="step-compact-body"
      :class="isExpanded ? 'step-compact-body--open' : 'step-compact-body--closed'"
    >
      <div class="step-compact-tools">
        <TransitionGroup name="stage" tag="div" class="flex flex-col gap-1">
          <div
            v-for="(stage, index) in stages"
            :key="stage.description + index"
            class="finalization-stage flex items-center gap-2 py-[2px]"
          >
            <!-- Stage status icon -->
            <div class="stage-icon flex-shrink-0 w-4 h-4 flex items-center justify-center">
              <CheckIcon
                v-if="stage.status === 'completed'"
                :size="12"
                :stroke-width="2.5"
                class="text-[var(--text-tertiary)]"
              />
              <XIcon
                v-else-if="stage.status === 'failed'"
                :size="12"
                :stroke-width="2.5"
                class="stage-icon-failed"
              />
              <span v-else class="stage-running-dot" aria-hidden="true"></span>
            </div>
            <!-- Stage description -->
            <span
              class="stage-label text-[13px] leading-[1.4]"
              :class="{
                'text-[var(--text-tertiary)]': stage.status === 'completed',
                'text-[var(--text-primary)] font-medium': stage.status === 'running',
                'stage-label-failed': stage.status === 'failed',
              }"
            >{{ stage.description }}</span>
          </div>
        </TransitionGroup>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { CheckIcon, XIcon } from 'lucide-vue-next';
import type { StepContent } from '../types/message';

const props = defineProps<{
  step: StepContent;
  showTopConnector?: boolean;
  showBottomConnector?: boolean;
}>();

const isExpanded = ref(true);
const toggleExpanded = () => { isExpanded.value = !isExpanded.value; };

const isCompleted = computed(() => props.step.status === 'completed');
const isFailed = computed(() => props.step.status === 'failed');

interface Stage {
  description: string;
  status: 'completed' | 'running' | 'failed';
}

/**
 * Map raw backend stage descriptions to polished, user-friendly labels.
 * Keeps unknown descriptions as-is for forward-compatibility.
 */
const STAGE_LABEL_MAP: Record<string, string> = {
  'Writing report...': 'Writing report',
  'Verifying factual claims...': 'Verifying sources',
  'Fact-checking sources...': 'Verifying sources',
  'Verification complete': 'Sources verified',
  'Report finalized': 'Report ready',
  'Summary failed delivery integrity checks': 'Quality check issue',
  'Summary contained no usable content': 'Generation issue',
};

const humanizeDescription = (raw: string): string => {
  // Handle dynamic verification messages with citation prune counts
  const citationMatch = raw.match(/^Verified \((\d+) ungrounded citations? removed\)$/);
  if (citationMatch) {
    return `Sources cleaned (${citationMatch[1]} removed)`;
  }
  return STAGE_LABEL_MAP[raw] ?? raw.replace(/\.{2,}$/, '');
};

const stages = computed((): Stage[] => {
  const history = props.step.sub_stage_history ?? [];
  const isTerminal = isCompleted.value || isFailed.value;

  const completedStages: Stage[] = history.map(desc => ({
    description: humanizeDescription(desc),
    status: 'completed',
  }));

  const currentStage: Stage = {
    description: humanizeDescription(props.step.description),
    status: isTerminal
      ? (isFailed.value ? 'failed' : 'completed')
      : 'running',
  };

  return [...completedStages, currentStage];
});
</script>

<style scoped>
/* Sub-stage running dot */
.stage-running-dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 9999px;
  background: #8c8c8c;
  animation: stage-dot-pulse 1.2s ease-in-out infinite;
}

.stage-icon-failed {
  color: #e53e3e;
}

.stage-label-failed {
  color: #e53e3e;
}

/* TransitionGroup animations for sub-stages entering */
.stage-enter-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.stage-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}
.stage-enter-to {
  opacity: 1;
  transform: translateY(0);
}

@keyframes stage-dot-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.75); }
}

/* Dark mode */
:global(.dark) .stage-running-dot {
  background: rgba(255, 255, 255, 0.82);
}

:global(.dark) .stage-icon-failed {
  color: #fc8181;
}

:global(.dark) .stage-label-failed {
  color: #fc8181;
}
</style>
