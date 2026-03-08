import { defineComponent, nextTick } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import ToolPanelContent from '@/components/ToolPanelContent.vue';
import type { CanvasUpdateEventData } from '@/types/event';
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

  it('updates browser chrome device mode when child emits update:device', async () => {
    const BrowserChromeStub = defineComponent({
      name: 'BrowserChrome',
      props: {
        device: {
          type: String,
          required: true,
        },
      },
      emits: ['update:device'],
      template: `
        <button data-test="device-toggle" @click="$emit('update:device', 'mobile')">
          {{ device }}
        </button>
      `,
    });

    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = shallowMount(ToolPanelContent, {
      props: {
        sessionId: 'session-1',
        realTime: true,
        toolContent: {
          ...baseToolContent,
          name: 'browser',
          function: 'browser_navigate',
          args: { url: 'https://example.com' },
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
          LiveViewer: true,
          BrowserChrome: BrowserChromeStub,
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

    const toggle = wrapper.find('[data-test="device-toggle"]');
    expect(toggle.exists()).toBe(true);
    expect(toggle.text()).toBe('desktop');

    await toggle.trigger('click');
    await nextTick();

    expect(wrapper.find('[data-test="device-toggle"]').text()).toBe('mobile');
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
          CanvasLiveView: CanvasLiveViewStub,
        },
      },
    });

    await nextTick();

    const canvasLiveView = wrapper.find('[data-test="canvas-live"]');
    expect(canvasLiveView.attributes('data-project-id')).toBe('live-project');
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
});
