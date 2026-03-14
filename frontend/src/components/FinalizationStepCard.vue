<template>
  <div class="finalization-step-card flex flex-col empty:pb-0">
    <div class="step-inner flex">
      <!-- Left rail: Status indicator + Timeline line -->
      <div class="step-left-rail w-[24px] relative flex-shrink-0">
        <!-- Top-level status indicator -->
        <div class="step-status-node w-4 flex items-center justify-center relative z-[1]" style="height: 26px;">
          <div
            v-if="isCompleted"
            class="step-status-indicator step-icon-badge step-icon-completed w-4 h-4 flex items-center justify-center rounded-[15px]"
          >
            <CheckIcon class="step-completed-check" :size="10" :stroke-width="2" />
          </div>
          <div
            v-else-if="isFailed"
            class="step-status-indicator step-icon-badge step-icon-failed w-4 h-4 flex items-center justify-center rounded-[15px]"
          >
            <XIcon class="step-failed-icon" :size="10" :stroke-width="2.5" />
          </div>
          <div
            v-else
            class="step-status-indicator step-icon-badge step-icon-running w-4 h-4 flex items-center justify-center rounded-[15px] step-running"
          >
            <span class="step-running-dot" aria-hidden="true"></span>
          </div>
        </div>
        <!-- Timeline connectors -->
        <div v-if="showTopConnector" class="step-connector-segment step-connector-top"></div>
        <div v-if="showBottomConnector" class="step-connector-segment step-connector-bottom"></div>
      </div>

      <!-- Right content -->
      <div class="finalization-right flex-1 min-w-0 pb-1">
        <!-- Card header -->
        <div
          class="finalization-header flex items-center justify-between gap-2 cursor-pointer"
          style="min-height: 26px;"
          @click="toggleExpanded"
        >
          <div class="flex items-center gap-2 min-w-0 flex-1">
            <span class="finalization-label text-sm font-medium text-[var(--text-primary)] truncate">
              Finalizing Report
            </span>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <ChevronDownIcon
              :size="16"
              class="text-[var(--text-tertiary)] transition-transform duration-200"
              :class="{ 'rotate-180': isExpanded }"
            />
          </div>
        </div>

        <!-- Sub-stages (collapsible) -->
        <div
          class="finalization-stages overflow-hidden transition-[max-height,opacity] duration-200 ease-in-out"
          :class="isExpanded ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'"
        >
          <div class="finalization-stages-inner pt-1.5 pb-0.5 flex flex-col gap-0.5 pl-0.5">
            <TransitionGroup name="stage" tag="div" class="flex flex-col gap-0.5">
              <div
                v-for="(stage, index) in stages"
                :key="stage.description + index"
                class="finalization-stage flex items-center gap-2 py-[3px]"
              >
                <!-- Stage status icon -->
                <div class="stage-icon flex-shrink-0 w-3.5 h-3.5 flex items-center justify-center">
                  <CheckIcon
                    v-if="stage.status === 'completed'"
                    :size="11"
                    :stroke-width="2.5"
                    class="text-[var(--text-tertiary)]"
                  />
                  <XIcon
                    v-else-if="stage.status === 'failed'"
                    :size="11"
                    :stroke-width="2.5"
                    class="stage-icon-failed"
                  />
                  <span
                    v-else
                    class="stage-running-dot"
                    aria-hidden="true"
                  ></span>
                </div>
                <!-- Stage description -->
                <span
                  class="stage-label text-xs leading-[1.4]"
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { CheckIcon, XIcon, ChevronDownIcon } from 'lucide-vue-next';
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
.finalization-label {
  font-size: 14px;
  line-height: 1.35;
  letter-spacing: 0;
}

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
