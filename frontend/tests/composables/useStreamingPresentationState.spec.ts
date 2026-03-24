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
    expect(state.headline.value).toBe('Writing report...');
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

  // ── Planning phase tests ──────────────────────────────────────

  it('activates planning phase when planPresentationText is present', async () => {
    const planPresentationText = ref('# Planning...\n> Analyzing...');
    const isPlanStreaming = ref(true);

    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
      isThinking: false,
      isActiveOperation: false,
      isPlanStreaming,
      planPresentationText,
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: ''
    });

    await nextTick();
    expect(state.phase.value).toBe('planning');
    expect(state.isPlanningPhase.value).toBe(true);

    state.dispose();
  });

  it('shows "Planning" headline while isPlanStreaming=true', async () => {
    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
      isThinking: false,
      isActiveOperation: false,
      isPlanStreaming: true,
      planPresentationText: '# Planning...',
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: ''
    });

    await nextTick();
    expect(state.headline.value).toBe('Planning');

    state.dispose();
  });

  it('shows "Plan ready" headline when isPlanStreaming=false with retained planPresentationText', async () => {
    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
      isThinking: false,
      isActiveOperation: false,
      isPlanStreaming: false,
      planPresentationText: '# AI Agent Frameworks\n## Step 1',
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: ''
    });

    await nextTick();
    expect(state.phase.value).toBe('planning');
    expect(state.headline.value).toBe('Plan ready');

    state.dispose();
  });

  it('summary streaming still overrides planning', async () => {
    const isSummaryStreaming = ref(true);
    const summaryStreamText = ref('partial report');

    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming,
      summaryStreamText,
      isThinking: false,
      isActiveOperation: false,
      isPlanStreaming: true,
      planPresentationText: '# Plan...',
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: ''
    });

    await nextTick();
    expect(state.phase.value).toBe('summarizing');

    state.dispose();
  });

  it('planning preview text comes from planPresentationText, not tool preview text', async () => {
    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
      isThinking: false,
      isActiveOperation: false,
      isPlanStreaming: true,
      planPresentationText: '# My Plan Content',
      toolDisplayName: '',
      toolDescription: '',
      baseViewType: 'generic',
      isSessionComplete: false,
      replayScreenshotUrl: '',
      previewText: 'tool preview text'
    });

    await nextTick();
    await vi.advanceTimersByTimeAsync(20);
    expect(state.previewText.value).toBe('# My Plan Content');

    state.dispose();
  });

  it('transitions allow idle -> planning -> thinking and planning -> idle', async () => {
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

    expect(state.phase.value).toBe('idle');

    // idle -> planning
    expect(state.setPhase('planning')).toBe(true);
    expect(state.phase.value).toBe('planning');

    // planning -> thinking
    expect(state.setPhase('thinking')).toBe(true);
    expect(state.phase.value).toBe('thinking');

    // Reset to idle, then test planning -> idle
    state.setPhase('idle');
    expect(state.setPhase('planning')).toBe(true);
    expect(state.setPhase('idle')).toBe(true);

    state.dispose();
  });

  it('uses persisted final report text after summary streaming has been cleared', async () => {
    const finalReportText = ref('');

    const state = useStreamingPresentationState({
      isInitializing: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
      finalReportText,
      isThinking: false,
      isActiveOperation: false,
      toolDisplayName: 'Browser',
      toolDescription: 'Browsing',
      baseViewType: 'live_preview',
      isSessionComplete: true,
      replayScreenshotUrl: 'blob:final-frame',
      previewText: ''
    });

    finalReportText.value = '# Final report';
    await nextTick();

    expect(state.phase.value).toBe('summary_final');
    expect(state.headline.value).toBe('Report complete');
    expect(state.viewType.value).toBe('report');

    await vi.advanceTimersByTimeAsync(20);
    expect(state.previewText.value).toBe('# Final report');

    state.dispose();
  });
});
