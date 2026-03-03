import { defineComponent, nextTick } from 'vue';
import { describe, expect, it, vi } from 'vitest';
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
          BrowserChrome: true,
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

  it('shows browser chrome in live preview for browser tools', () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        name: 'browser',
        function: 'browser_navigate',
        args: { url: 'https://example.com' },
      },
    });

    expect(wrapper.find('browser-chrome-stub').exists()).toBe(true);
  });

  it('hides browser chrome for non-browser tool views', () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        name: 'shell',
        function: 'shell_exec',
        args: { command: 'echo hello' },
      },
    });

    expect(wrapper.find('browser-chrome-stub').exists()).toBe(false);
  });

  it('forwards browser tool events to persistent LiveViewer for overlay rendering', async () => {
    const processToolEvent = vi.fn();
    const LiveViewerStub = defineComponent({
      name: 'LiveViewer',
      setup(_props, { expose }) {
        expose({ processToolEvent });
        return () => null;
      },
    });

    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = shallowMount(ToolPanelContent, {
      props: {
        sessionId: 'session-1',
        realTime: true,
        toolContent: {
          ...baseToolContent,
          function: 'browser_click',
          args: { index: 1 },
          status: 'calling',
        },
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
          LiveViewer: LiveViewerStub,
          BrowserChrome: true,
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

    await nextTick();

    await wrapper.setProps({
      toolContent: {
        ...baseToolContent,
        function: 'browser_click',
        status: 'called',
        args: { coordinate_x: 120, coordinate_y: 240 },
      },
    });

    await nextTick();
    expect(processToolEvent).toHaveBeenCalled();
  });

  it('forwards latest tool event after session id becomes available', async () => {
    const processToolEvent = vi.fn();
    const LiveViewerStub = defineComponent({
      name: 'LiveViewer',
      setup(_props, { expose }) {
        expose({ processToolEvent });
        return () => null;
      },
    });

    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = shallowMount(ToolPanelContent, {
      props: {
        sessionId: '',
        realTime: true,
        toolContent: {
          ...baseToolContent,
          function: 'browser_click',
          status: 'called',
          args: { coordinate_x: 120, coordinate_y: 240 },
        },
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
          LiveViewer: LiveViewerStub,
          BrowserChrome: true,
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

    expect(processToolEvent).not.toHaveBeenCalled();

    await wrapper.setProps({ sessionId: 'session-1' });
    await nextTick();

    expect(processToolEvent).toHaveBeenCalledTimes(1);
  });
});
