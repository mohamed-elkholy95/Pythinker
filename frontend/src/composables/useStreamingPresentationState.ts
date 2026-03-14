import { computed, getCurrentScope, onScopeDispose, ref, watch, type MaybeRefOrGetter, toValue } from 'vue';
import {
  STREAMING_FRAME_BATCH_MS,
  STREAMING_LABELS,
  STREAMING_STALE_TIMEOUT_MS,
  THINKING_ROTATING_LABELS,
  THINKING_ROTATION_INTERVAL_MS,
  type StreamPhase,
  type StreamingViewType,
  VALID_PHASE_TRANSITIONS
} from '@/constants/streamingPresentation';

export interface StreamingPresentationInput {
  isInitializing: MaybeRefOrGetter<boolean>;
  isSummaryStreaming: MaybeRefOrGetter<boolean>;
  summaryStreamText?: MaybeRefOrGetter<string | undefined>;
  finalReportText?: MaybeRefOrGetter<string | undefined>;
  isThinking?: MaybeRefOrGetter<boolean | undefined>;
  isActiveOperation?: MaybeRefOrGetter<boolean | undefined>;
  isPlanStreaming?: MaybeRefOrGetter<boolean | undefined>;
  planPresentationText?: MaybeRefOrGetter<string | undefined>;
  toolDisplayName?: MaybeRefOrGetter<string | undefined>;
  toolDescription?: MaybeRefOrGetter<string | undefined>;
  baseViewType?: MaybeRefOrGetter<StreamingViewType | null | undefined>;
  isSessionComplete?: MaybeRefOrGetter<boolean | undefined>;
  replayScreenshotUrl?: MaybeRefOrGetter<string | undefined>;
  previewText?: MaybeRefOrGetter<string | undefined>;
  staleTimeoutMs?: number;
}

const resolve = <T>(value: MaybeRefOrGetter<T>): T => toValue(value);

const isValidTransition = (current: StreamPhase, next: StreamPhase): boolean =>
  VALID_PHASE_TRANSITIONS[current].includes(next);

export function useStreamingPresentationState(input: StreamingPresentationInput) {
  const phase = ref<StreamPhase>('idle');
  const previousPhase = ref<StreamPhase | null>(null);
  const lastUpdatedAt = ref<number>(Date.now());
  const updateCount = ref<number>(0);

  const toolDisplayName = ref<string>(input.toolDisplayName ? (resolve(input.toolDisplayName) || '') : '');
  const toolDescription = ref<string>(input.toolDescription ? (resolve(input.toolDescription) || '') : '');
  const previewText = ref<string>('');

  const staleTimeoutMs = input.staleTimeoutMs ?? STREAMING_STALE_TIMEOUT_MS;

  let frameBatchTimer: ReturnType<typeof setTimeout> | null = null;
  let pendingPreviewText: string | null = null;
  let staleCheckTimer: ReturnType<typeof setTimeout> | null = null;
  let labelRotationTimer: ReturnType<typeof setInterval> | null = null;

  const thinkingLabelIndex = ref(0);

  const startLabelRotation = (): void => {
    if (labelRotationTimer !== null) return;
    labelRotationTimer = setInterval(() => {
      thinkingLabelIndex.value = (thinkingLabelIndex.value + 1) % THINKING_ROTATING_LABELS.length;
    }, THINKING_ROTATION_INTERVAL_MS);
  };

  const stopLabelRotation = (): void => {
    if (labelRotationTimer === null) return;
    clearInterval(labelRotationTimer);
    labelRotationTimer = null;
    thinkingLabelIndex.value = 0;
  };

  watch(phase, (p) => {
    if (p === 'thinking') {
      startLabelRotation();
    } else {
      stopLabelRotation();
    }
  }, { immediate: true });

  const touch = (): void => {
    lastUpdatedAt.value = Date.now();
    updateCount.value += 1;
  };

  const flushPreviewText = (): void => {
    frameBatchTimer = null;
    if (pendingPreviewText === null) return;
    previewText.value = pendingPreviewText;
    pendingPreviewText = null;
    touch();
  };

  const setPreviewText = (next: string): void => {
    const normalized = next || '';

    if (normalized === previewText.value && pendingPreviewText === null) {
      return;
    }

    if (previewText.value.length === 0 && updateCount.value === 0) {
      previewText.value = normalized;
      touch();
      return;
    }

    pendingPreviewText = normalized;
    if (frameBatchTimer !== null) return;
    frameBatchTimer = setTimeout(flushPreviewText, STREAMING_FRAME_BATCH_MS);
  };

  const setToolDisplayName = (next: string): void => {
    if (toolDisplayName.value === next) return;
    toolDisplayName.value = next;
    touch();
  };

  const setToolDescription = (next: string): void => {
    if (toolDescription.value === next) return;
    toolDescription.value = next;
    touch();
  };

  const setPhase = (nextPhase: StreamPhase): boolean => {
    const current = phase.value;
    if (current === nextPhase) return true;
    if (current === 'idle' && nextPhase === 'summary_final') {
      // Hydration edge case: restored UI may only receive buffered summary text.
      previousPhase.value = current;
      phase.value = nextPhase;
      touch();
      return true;
    }
    if (!isValidTransition(current, nextPhase)) {
      console.warn(`Invalid phase transition: ${current} -> ${nextPhase}`);
      return false;
    }

    previousPhase.value = current;
    phase.value = nextPhase;
    touch();
    return true;
  };

  const resetToSafeState = (): void => {
    previousPhase.value = phase.value;
    phase.value = 'idle';
    previewText.value = '';
    pendingPreviewText = null;
    touch();
    console.warn('Streaming state reset due to inconsistency');
  };

  const desiredPhase = computed<StreamPhase>(() => {
    const summaryStreaming = resolve(input.isSummaryStreaming);
    const summaryText = resolve(input.summaryStreamText || '') || '';
    const finalReportText = resolve(input.finalReportText || '') || '';
    const thinking = Boolean(resolve(input.isThinking || false));
    const activeOperation = Boolean(resolve(input.isActiveOperation || false));
    const planText = resolve(input.planPresentationText || '') || '';

    if (summaryStreaming) return 'summarizing';
    if (finalReportText.length > 0) return 'summary_final';
    if (!summaryStreaming && summaryText.length > 0) return 'summary_final';
    if (planText.length > 0) return 'planning';
    if (thinking || activeOperation) return 'thinking';
    return 'idle';
  });

  watch(
    desiredPhase,
    (nextPhase) => {
      setPhase(nextPhase);
    },
    { immediate: true }
  );

  watch(
    () => resolve(input.toolDisplayName || ''),
    (next) => setToolDisplayName(next || ''),
    { immediate: true }
  );

  watch(
    () => resolve(input.toolDescription || ''),
    (next) => setToolDescription(next || ''),
    { immediate: true }
  );

  watch(
    () => {
      const summaryText = resolve(input.summaryStreamText || '') || '';
      const finalReportText = resolve(input.finalReportText || '') || '';
      const planText = resolve(input.planPresentationText || '') || '';
      const sourcePreviewText = resolve(input.previewText || '') || '';
      if (phase.value === 'summary_final' && finalReportText.length > 0) {
        return finalReportText;
      }
      if (phase.value === 'summarizing' || phase.value === 'summary_final') {
        return summaryText;
      }
      if (phase.value === 'planning' && planText.length > 0) {
        return planText;
      }
      return sourcePreviewText;
    },
    (next) => setPreviewText(next || ''),
    { immediate: true }
  );

  const isSummaryPhase = computed(() => phase.value === 'summarizing' || phase.value === 'summary_final');
  const isPlanningPhase = computed(() => phase.value === 'planning');

  const headline = computed<string>(() => {
    if (resolve(input.isInitializing)) return STREAMING_LABELS.initializing;
    if (phase.value === 'summarizing') return STREAMING_LABELS.summarizing_active;
    if (phase.value === 'summary_final') return STREAMING_LABELS.summarizing_final;
    if (phase.value === 'planning') {
      const planStreaming = Boolean(resolve(input.isPlanStreaming || false));
      return planStreaming ? STREAMING_LABELS.planning_active : STREAMING_LABELS.planning_final;
    }
    if (phase.value === 'thinking') return THINKING_ROTATING_LABELS[thinkingLabelIndex.value];
    if (resolve(input.isSessionComplete || false)) return STREAMING_LABELS.completed;
    if (toolDisplayName.value) return `Pythinker is using ${toolDisplayName.value}`;
    return STREAMING_LABELS.waiting;
  });

  const subtitle = computed<string>(() => {
    if (isSummaryPhase.value) return '';
    return toolDescription.value || '';
  });

  const viewType = computed<StreamingViewType>(() => {
    if (isSummaryPhase.value) return 'report';
    return resolve(input.baseViewType || 'generic') || 'generic';
  });

  const showReplayFrame = computed<boolean>(() => {
    const replayUrl = String(resolve(input.replayScreenshotUrl ?? ''));
    const sessionComplete = Boolean(resolve(input.isSessionComplete || false));
    const initializing = Boolean(resolve(input.isInitializing));
    const activeOperation = Boolean(resolve(input.isActiveOperation || false));

    if (initializing || isSummaryPhase.value || activeOperation) return false;
    return sessionComplete && replayUrl.length > 0;
  });

  const isStreaming = computed<boolean>(() => phase.value !== 'idle');

  const shouldResetForStaleState = (): boolean => {
    const initializing = Boolean(resolve(input.isInitializing));
    const summaryStreaming = Boolean(resolve(input.isSummaryStreaming));
    const activeOperation = Boolean(resolve(input.isActiveOperation || false));
    if (initializing) return false;
    if (!(summaryStreaming || activeOperation || phase.value === 'thinking' || phase.value === 'summarizing')) {
      return false;
    }
    return (Date.now() - lastUpdatedAt.value) >= staleTimeoutMs;
  };

  const scheduleStaleCheck = (): void => {
    if (staleCheckTimer !== null) {
      clearTimeout(staleCheckTimer);
      staleCheckTimer = null;
    }
    if (staleTimeoutMs <= 0) return;

    staleCheckTimer = setTimeout(() => {
      if (shouldResetForStaleState()) {
        resetToSafeState();
      }
      scheduleStaleCheck();
    }, Math.max(staleTimeoutMs, 1000));
  };

  watch(
    () => [phase.value, lastUpdatedAt.value, resolve(input.isSummaryStreaming), resolve(input.isActiveOperation || false), resolve(input.isInitializing)] as const,
    () => {
      scheduleStaleCheck();
    },
    { immediate: true }
  );

  const cleanup = (): void => {
    stopLabelRotation();
    if (staleCheckTimer !== null) {
      clearTimeout(staleCheckTimer);
      staleCheckTimer = null;
    }
    if (frameBatchTimer !== null) {
      clearTimeout(frameBatchTimer);
      frameBatchTimer = null;
    }
  };

  if (getCurrentScope()) {
    onScopeDispose(cleanup);
  }

  return {
    phase,
    previousPhase,
    lastUpdatedAt,
    updateCount,
    headline,
    subtitle,
    viewType,
    previewText,
    isStreaming,
    isSummaryPhase,
    isPlanningPhase,
    showReplayFrame,
    setPhase,
    setPreviewText,
    setToolDisplayName,
    setToolDescription,
    resetToSafeState,
    dispose: cleanup,
  };
}
