import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { computed, nextTick, ref } from 'vue';
import { useStreamingPresentationState } from '@/composables/useStreamingPresentationState';

describe('useStreamingPresentationState', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('prioritizes summarizing over active tool state', async () => {
    const isSummaryStreaming = ref(false);
    const summaryStreamText = ref('');
    const isThinking = ref(false);
    const isActiveOperation = ref(true);

    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming,
      summaryStreamText,
      isThinking,
      isActiveOperation,
      toolDisplayName: 'Terminal',
      toolDescription: 'Running npm test',
      baseViewType: 'terminal',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: ''
    });

    await nextTick();
    expect(state.phase.value).toBe('thinking');
    expect(state.viewType.value).toBe('terminal');

    isSummaryStreaming.value = true;
    await nextTick();

    expect(state.phase.value).toBe('summarizing');
    expect(state.headline.value).toBe('Composing report...');
    expect(state.viewType.value).toBe('report');

    state.dispose();
  });

  it('guards invalid phase transitions', () => {
    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
      isThinking: false,
      isActiveOperation: false,
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: ''
    });

    expect(state.setPhase('thinking')).toBe(true);
    expect(state.phase.value).toBe('thinking');
    expect(state.setPhase('summary_final')).toBe(false);
    expect(state.phase.value).toBe('thinking');

    state.dispose();
  });

  it('frame-batches rapid preview updates', async () => {
    const previewText = ref('');
    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
      isThinking: false,
      isActiveOperation: false,
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: computed(() => previewText.value)
    });

    previewText.value = 'chunk 1';
    await nextTick();
    expect(state.previewText.value).toBe('chunk 1');

    previewText.value = 'chunk 2';
    previewText.value = 'chunk 3';
    await nextTick();
    expect(state.previewText.value).toBe('chunk 1');

    await vi.advanceTimersByTimeAsync(20);
    expect(state.previewText.value).toBe('chunk 3');

    state.dispose();
  });

  it('resets stale streaming state to safe idle state', async () => {
    const isSummaryStreaming = ref(true);
    const summaryStreamText = ref('partial report');

    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming,
      summaryStreamText,
      isThinking: false,
      isActiveOperation: false,
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: '',
      staleTimeoutMs: 30000
    });

    await nextTick();
    expect(state.phase.value).toBe('summarizing');

    await vi.advanceTimersByTimeAsync(31000);
    expect(state.phase.value).toBe('idle');
    expect(state.previewText.value).toBe('');

    state.dispose();
  });
});
