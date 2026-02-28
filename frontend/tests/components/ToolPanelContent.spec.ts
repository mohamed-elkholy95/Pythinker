import { describe, expect, it } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import ToolPanelContent from '@/components/ToolPanelContent.vue';
import type { ToolContent } from '@/types/message';

const baseToolContent: ToolContent = {
  event_id: 'tool-1',
  timestamp: Date.now(),
  tool_call_id: 'tool-call-1',
  name: 'browser',
  function: 'browser_navigate',
  args: { url: 'https://example.com' },
  status: 'calling',
};

const mountToolPanelContent = (overrides: Record<string, unknown> = {}) => (
  (() => {
    const pinia = createPinia();
    setActivePinia(pinia);
    return shallowMount(ToolPanelContent, {
      props: {
        sessionId: 'session-1',
        realTime: true,
        toolContent: baseToolContent,
        live: true,
        isShare: false,
        ...overrides,
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
          StreamingReportView: true,
          WideResearchOverlay: true,
          ScreenshotReplayViewer: true,
        },
      },
    });
  })()
);

describe('ToolPanelContent', () => {
  it('shows composing report activity during summary streaming', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: true,
      summaryStreamText: 'partial summary',
    });

    expect(wrapper.text()).toContain('Composing report...');
    expect(wrapper.find('streaming-report-view-stub').exists()).toBe(true);
  });

  it('renders standardized tool activity label when not summary streaming', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.text()).toContain('Pythinker is using Browser');
    expect(wrapper.text()).toContain('Browsing');
  });

  it('keeps streaming report visible when summary text is buffered after stream end', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: false,
      summaryStreamText: 'finalized summary',
    });

    expect(wrapper.find('streaming-report-view-stub').exists()).toBe(true);
    expect(wrapper.text()).toContain('Report complete');
  });
});
