import { defineComponent, nextTick } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import ToolPanelContent from '@/components/ToolPanelContent.vue';
import type { CanvasUpdateEventData } from '@/types/event';
import type { ToolContent } from '@/types/message';

vi.mock('lucide-vue-next', async () => {
  const actual = await vi.importActual<typeof import('lucide-vue-next')>('lucide-vue-next');
  return {
    ...actual,
    Loader2: {
      name: 'Loader2',
      template: '<span class="mock-loader2" />',
    },
    FileText: {
      name: 'FileText',
      template: '<span class="mock-file-text" />',
    },
  };
});

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
          Transition: { template: '<div><slot /></div>' },
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
          PlanPresentationView: true,
          TerminalLiveView: true,
          DealContentView: true,
          ChartToolView: true,
          CanvasLiveView: true,
          UnifiedStreamingView: true,
        },
      },
    });
  })()
);

describe('ToolPanelContent', () => {
  it('shows writing report activity during summary streaming', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: true,
      summaryStreamText: 'partial summary',
    });

    expect(wrapper.text()).toContain('Writing report...');
    expect(wrapper.find('[data-testid="report-overlay"]').exists()).toBe(true);
  });

  it('uses a report icon instead of the loader spinner during report activity', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: true,
      summaryStreamText: 'partial summary',
    });

    expect(wrapper.findComponent({ name: 'FileText' }).exists()).toBe(true);
    expect(wrapper.findComponent({ name: 'Loader2' }).exists()).toBe(false);
  });

  it('suppresses placeholder undefined activity detail text', () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        display_command: 'undefined',
      },
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.text()).not.toContain('undefined');
  });

  it('renders standardized tool activity label when not summary streaming', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.text()).toContain('Pythinker is using Browser');
    expect(wrapper.text()).toContain('Browsing');
  });

  it('keeps report visible from final report text after stream ends', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: false,
      summaryStreamText: '',
      finalReportText: '# Finalized report',
    });

    expect(wrapper.find('[data-testid="report-overlay"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Report');
  });

  it('keeps report-complete view visible from persisted final report text after summary stream clears', () => {
    const wrapper = mountToolPanelContent({
      isSummaryStreaming: false,
      summaryStreamText: '',
      finalReportText: '# Final report',
      replayScreenshotUrl: 'blob:final-screenshot',
      isLoading: false,
    });

    expect(wrapper.find('[data-testid="report-overlay"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Report');
  });

  it('hides URL status bar in live preview (X11 screencast captures native Chrome address bar)', () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        name: 'browser',
        function: 'browser_navigate',
        args: { url: 'https://example.com' },
      },
    });

    expect(wrapper.find('.url-status-bar').exists()).toBe(false);
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

  it('URL status bar stays hidden even when browser tool URL changes', async () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        name: 'browser',
        function: 'browser_navigate',
        args: { url: 'https://example.com' },
      },
    });

    expect(wrapper.find('.url-status-bar').exists()).toBe(false);

    await wrapper.setProps({
      toolContent: {
        ...baseToolContent,
        name: 'browser',
        function: 'browser_navigate',
        args: { url: 'https://other-site.com' },
      },
    });

    expect(wrapper.find('.url-status-bar').exists()).toBe(false);
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
          PlanPresentationView: true,
          TerminalLiveView: true,
          DealContentView: true,
          ChartToolView: true,
          CanvasLiveView: true,
          UnifiedStreamingView: true,
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
          PlanPresentationView: true,
          TerminalLiveView: true,
          DealContentView: true,
          ChartToolView: true,
          CanvasLiveView: true,
          UnifiedStreamingView: true,
        },
      },
    });

    expect(processToolEvent).not.toHaveBeenCalled();

    await wrapper.setProps({ sessionId: 'session-1' });
    await nextTick();

    expect(processToolEvent).toHaveBeenCalledTimes(1);
  });

  it('passes the active canvas update project id through to CanvasLiveView', async () => {
    const CanvasLiveViewStub = defineComponent({
      name: 'CanvasLiveView',
      props: {
        projectId: {
          type: String,
          required: true,
        },
        refreshToken: {
          type: Number,
          required: true,
        },
      },
      template: '<div data-test="canvas-live" :data-project-id="projectId" :data-refresh-token="refreshToken" />',
    });

    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = shallowMount(ToolPanelContent, {
      props: {
        sessionId: 'session-1',
        realTime: true,
        toolContent: {
          ...baseToolContent,
          name: 'canvas',
          function: 'canvas_add_element',
          args: { project_id: 'tool-project' },
          content: { project_id: 'tool-project', element_count: 1 },
          status: 'called',
        },
        live: true,
        isShare: false,
        activeCanvasUpdate: {
          event_id: 'canvas-event-1',
          timestamp: Date.now(),
          project_id: 'live-project',
          operation: 'add_element',
          element_count: 2,
          version: 3,
        } satisfies CanvasUpdateEventData,
      },
      global: {
        plugins: [pinia],
        config: {
          globalProperties: {
            $t: (key: string) => key,
          },
        },
        stubs: {
          Transition: { template: '<div><slot /></div>' },
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
          PlanPresentationView: true,
          TerminalLiveView: true,
          DealContentView: true,
          ChartToolView: true,
          UnifiedStreamingView: true,
          CanvasLiveView: CanvasLiveViewStub,
        },
      },
    });

    await nextTick();

    const canvasLiveView = wrapper.find('[data-test="canvas-live"]');
    expect(canvasLiveView.attributes('data-project-id')).toBe('live-project');
  });

  it('shows planning overlay when planPresentationText is present', () => {
    const wrapper = mountToolPanelContent({
      planPresentationText: '# Plan Content\n## Step 1',
      isPlanStreaming: true,
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.find('[data-testid="plan-overlay"]').exists()).toBe(true);
    expect(wrapper.find('plan-presentation-view-stub').exists()).toBe(true);
  });

  it('report overlay still has higher priority than planning overlay', () => {
    const wrapper = mountToolPanelContent({
      planPresentationText: '# Plan Content',
      isPlanStreaming: false,
      isSummaryStreaming: true,
      summaryStreamText: 'report text',
    });

    // Report overlay should win — planning overlay should not render
    expect(wrapper.find('[data-testid="report-overlay"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="plan-overlay"]').exists()).toBe(false);
  });

  it('planning header shows "Creating plan..." while streaming', () => {
    const wrapper = mountToolPanelContent({
      planPresentationText: '# Plan...',
      isPlanStreaming: true,
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.text()).toContain('Creating plan...');
  });

  it('planning header shows "Plan ready" after final chunk', () => {
    const wrapper = mountToolPanelContent({
      planPresentationText: '# Final Plan\n## Step 1',
      isPlanStreaming: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.text()).toContain('Plan ready');
  });

  it('renders the header for a synthetic planning tool when the plan overlay is active', () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        name: 'planning',
        function: 'create_plan',
        args: {},
        status: 'running',
      },
      planPresentationText: '# Plan Content\n## Step 1',
      isPlanStreaming: true,
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.find('[data-testid="plan-overlay"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Creating plan...');
  });

  it('bumps the CanvasLiveView refresh token for same-project canvas updates', async () => {
    const CanvasLiveViewStub = defineComponent({
      name: 'CanvasLiveView',
      props: {
        projectId: {
          type: String,
          required: true,
        },
        refreshToken: {
          type: Number,
          required: true,
        },
      },
      template: '<div data-test="canvas-live" :data-project-id="projectId" :data-refresh-token="refreshToken" />',
    });

    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = shallowMount(ToolPanelContent, {
      props: {
        sessionId: 'session-1',
        realTime: true,
        toolContent: {
          ...baseToolContent,
          name: 'canvas',
          function: 'canvas_add_element',
          args: { project_id: 'project-1' },
          content: { project_id: 'project-1', element_count: 1 },
          status: 'called',
        },
        live: true,
        isShare: false,
        activeCanvasUpdate: {
          event_id: 'canvas-event-1',
          timestamp: Date.now(),
          project_id: 'project-1',
          operation: 'add_element',
          element_count: 1,
          version: 2,
        } satisfies CanvasUpdateEventData,
      },
      global: {
        plugins: [pinia],
        config: {
          globalProperties: {
            $t: (key: string) => key,
          },
        },
        stubs: {
          Transition: { template: '<div><slot /></div>' },
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
          PlanPresentationView: true,
          TerminalLiveView: true,
          DealContentView: true,
          ChartToolView: true,
          UnifiedStreamingView: true,
          CanvasLiveView: CanvasLiveViewStub,
        },
      },
    });

    await nextTick();

    const firstToken = Number(wrapper.find('[data-test="canvas-live"]').attributes('data-refresh-token'));

    await wrapper.setProps({
      activeCanvasUpdate: {
        event_id: 'canvas-event-2',
        timestamp: Date.now() + 1,
        project_id: 'project-1',
        operation: 'modify_element',
        element_count: 2,
        version: 3,
      } satisfies CanvasUpdateEventData,
    });
    await nextTick();

    const secondToken = Number(wrapper.find('[data-test="canvas-live"]').attributes('data-refresh-token'));
    expect(secondToken).toBeGreaterThan(firstToken);
  });

  it('does not render a transition shell for live-preview pass-through mode', () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        name: 'browser',
        function: 'browser_navigate',
        args: { url: 'https://example.com' },
        status: 'called',
      },
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.find('[data-testid="panel-transition-shell"]').exists()).toBe(false);
  });

  it('switches from plan overlay to search view when props change', async () => {
    const wrapper = mountToolPanelContent({
      toolContent: {
        ...baseToolContent,
        name: 'planning',
        function: 'create_plan',
        args: {},
        status: 'running',
      },
      planPresentationText: '# Plan',
      isPlanStreaming: false,
      isSummaryStreaming: false,
      summaryStreamText: '',
    });

    expect(wrapper.find('[data-testid="plan-overlay"]').exists()).toBe(true);

    await wrapper.setProps({
      toolContent: {
        ...baseToolContent,
        name: 'search',
        function: 'web_search',
        args: { query: 'rust 2026' },
        status: 'called',
        content: { results: [] },
      },
      planPresentationText: '',
    });

    expect(wrapper.find('[data-testid="plan-overlay"]').exists()).toBe(false);
    expect(wrapper.find('search-content-view-stub').exists()).toBe(true);
  });
});
