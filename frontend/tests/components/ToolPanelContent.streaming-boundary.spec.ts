import { describe, expect, it, vi } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';

vi.mock('@/composables/useStreamingPresentationState', async () => {
  const vue = await import('vue');

  return {
    useStreamingPresentationState: () => ({
      phase: vue.ref('idle'),
      previousPhase: vue.ref(null),
      lastUpdatedAt: vue.ref(Date.now()),
      updateCount: vue.ref(0),
      headline: vue.computed(() => 'Waiting'),
      subtitle: vue.computed(() => ''),
      viewType: vue.computed(() => 'generic'),
      previewText: vue.ref(''),
      isStreaming: vue.computed(() => false),
      isSummaryPhase: vue.computed(() => false),
      // Simulate a stale / partially-updated composable return shape.
      showReplayFrame: vue.computed(() => false),
      setPhase: vi.fn(),
      setPreviewText: vi.fn(),
      setToolDisplayName: vi.fn(),
      setToolDescription: vi.fn(),
      resetToSafeState: vi.fn(),
      dispose: vi.fn(),
    }),
  };
});

import ToolPanelContent from '@/components/ToolPanelContent.vue';
import type { ToolContent } from '@/types/message';

const baseToolContent: ToolContent = {
  event_id: 'tool-1',
  timestamp: Date.now(),
  tool_call_id: 'tool-call-1',
  name: 'browser',
  function: 'browser_navigate',
  args: { url: 'https://example.com' },
  status: 'called',
};

const mountToolPanelContent = () => {
  const pinia = createPinia();
  setActivePinia(pinia);

  return shallowMount(ToolPanelContent, {
    props: {
      sessionId: 'session-1',
      realTime: true,
      toolContent: baseToolContent,
      live: true,
      isShare: false,
    },
    global: {
      plugins: [pinia],
      config: {
        globalProperties: {
          $t: (key: string) => key,
        },
      },
      stubs: {
        TimelineControls: true,
        TaskProgressBar: true,
        LiveViewer: true,
        LoadingState: true,
        InactiveState: true,
        TerminalContentView: true,
        EditorContentView: true,
        SearchContentView: true,
        GenericContentView: true,
        WideResearchOverlay: true,
        ScreenshotReplayViewer: true,
      },
    },
  });
};

describe('ToolPanelContent streaming boundary hardening', () => {
  it('does not crash when the streaming presentation composable omits isPlanningPhase', () => {
    expect(() => mountToolPanelContent()).not.toThrow();
  });
});
