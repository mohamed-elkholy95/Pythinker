import { shallowMount } from '@vue/test-utils';
import { computed, ref } from 'vue';
import { describe, expect, it, vi } from 'vitest';

import type { ToolContent } from '@/types/message';

vi.mock('@/composables/useContentConfig', () => ({
  useContentConfig: () => ({
    contentConfig: computed(() => null),
    viewModeIndex: ref(0),
    currentViewType: computed(() => 'generic'),
    hasNewOutput: ref(false),
    setViewModeByIndex: vi.fn(),
    markNewOutput: vi.fn(),
  }),
}));

vi.mock('@/composables/useCanvasLiveSync', () => ({
  useCanvasLiveSync: () => ({
    latestCanvasUpdate: ref(null),
    resolvedProjectId: ref(null),
    refreshToken: ref(0),
  }),
}));

vi.mock('@/composables/useStreamingPresentationState', () => ({
  useStreamingPresentationState: () => ({
    isSummaryPhase: computed(() => false),
    headline: computed(() => 'Thinking'),
  }),
}));

vi.mock('@/composables/useWideResearch', () => ({
  useWideResearchGlobal: () => ({
    overlayState: ref(null),
  }),
}));

vi.mock('@/composables/useElapsedTimer', () => ({
  useElapsedTimer: () => ({
    start: vi.fn(),
    stop: vi.fn(),
    formatted: ref('00:00'),
  }),
}));

vi.mock('@/stores/connectionStore', () => ({
  useConnectionStore: () => ({
    phase: 'idle',
  }),
}));

vi.mock('@/utils/livePreviewSelection', () => ({
  resolveLivePreviewViewType: () => 'generic',
}));

vi.mock('@/utils/searchResults', () => ({
  normalizeSearchResults: () => [],
}));

vi.mock('@/utils/viewRouting', () => ({
  isCanvasDomainTool: () => false,
}));

vi.mock('@/types/streaming', () => ({
  detectContentType: () => 'text',
  detectLanguage: () => 'text',
}));

vi.mock('@/utils/toolDisplay', () => ({
  getToolDisplay: () => ({
    displayName: 'Editor',
    description: 'path/file.tsx',
    actionLabel: 'Edit',
    resourceLabel: 'path/file.tsx',
    toolKey: 'file',
    icon: null,
  }),
  extractToolUrl: () => null,
}));

vi.mock('@/api/agent', () => ({
  viewFile: vi.fn(),
  viewShellSession: vi.fn(),
  browseUrl: vi.fn(),
  startTakeover: vi.fn(),
}));

import ToolPanelContent from '../ToolPanelContent.vue';

describe('ToolPanelContent', () => {
  it('shows the activity line in the simplified header instead of a separate status bar', () => {
    const toolContent: ToolContent = {
      timestamp: 1,
      tool_call_id: 'tool-1',
      name: 'file',
      function: 'file_write',
      args: {
        file: '/workspace/path/file.tsx',
      },
      status: 'calling',
    };

    const wrapper = shallowMount(ToolPanelContent, {
      props: {
        realTime: true,
        toolContent,
        live: true,
        isShare: false,
      },
    });

    const headerText = wrapper.find('.live-shell__header').text();

    expect(wrapper.find('.live-shell__statusbar').exists()).toBe(false);
    expect(headerText).toContain('Pythinker is using Editor');
    expect(headerText).toContain('path/file.tsx');
  });
});
