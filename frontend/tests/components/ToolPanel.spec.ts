/**
 * Tests for ToolPanel component
 * Tests panel visibility, tool content display, and event handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import ToolPanel from '@/components/ToolPanel.vue'
import { mockToolContent } from '../mocks/api'
import type { PlanEventData } from '@/types/event'

// Mock composables
vi.mock('@/composables/useResizeObserver', () => ({
  useResizeObserver: () => ({
    size: ref(800),
  }),
}))

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
  },
}))

// Mock constants
vi.mock('@/constants/event', () => ({
  EVENT_SHOW_FILE_PANEL: 'show-file-panel',
  EVENT_SHOW_TOOL_PANEL: 'show-tool-panel',
  EVENT_TOOL_PANEL_STATE_CHANGE: 'tool-panel-state-change',
}))

// Mock child components
vi.mock('@/components/ToolPanelContent.vue', () => ({
  default: {
    name: 'ToolPanelContent',
    template: '<div class="mock-tool-panel-content"><slot /></div>',
    props: ['sessionId', 'realTime', 'toolContent', 'live', 'isShare'],
    emits: ['hide', 'jumpToRealTime'],
  },
}))

vi.mock('@/components/TaskProgressBar.vue', () => ({
  default: {
    name: 'TaskProgressBar',
    template: '<div class="mock-task-progress-bar" />',
    props: ['plan', 'isLoading', 'isThinking'],
  },
}))

describe('ToolPanel', () => {
  const defaultProps = {
    sessionId: 'session-123',
    realTime: true,
    isShare: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render when visible', () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    expect(wrapper.exists()).toBe(true)
  })

  it('should expose showToolPanel method', () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    expect(typeof wrapper.vm.showToolPanel).toBe('function')
  })

  it('should expose hideToolPanel method', () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    expect(typeof wrapper.vm.hideToolPanel).toBe('function')
  })

  it('should expose isShow ref', () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    expect(wrapper.vm.isShow).toBeDefined()
  })

  it('should show tool content when showToolPanel is called', async () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.isShow).toBe(true)
  })

  it('should hide panel when hideToolPanel is called', async () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    wrapper.vm.hideToolPanel()
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.isShow).toBe(false)
  })

  it('should emit panelStateChange when panel visibility changes', async () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('panelStateChange')).toBeTruthy()
    expect(wrapper.emitted('panelStateChange')?.[0]).toEqual([true])
  })

  it('should render ToolPanelContent when shown with content', async () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    const toolPanelContent = wrapper.findComponent({ name: 'ToolPanelContent' })
    expect(toolPanelContent.exists()).toBe(true)
  })

  it('should pass props to ToolPanelContent', async () => {
    const wrapper = mount(ToolPanel, {
      props: {
        ...defaultProps,
        sessionId: 'test-session',
        realTime: true,
        isShare: true,
      },
    })

    wrapper.vm.showToolPanel(mockToolContent, true)
    await wrapper.vm.$nextTick()

    const toolPanelContent = wrapper.findComponent({ name: 'ToolPanelContent' })
    expect(toolPanelContent.props('sessionId')).toBe('test-session')
    expect(toolPanelContent.props('realTime')).toBe(true)
    expect(toolPanelContent.props('isShare')).toBe(true)
    expect(toolPanelContent.props('live')).toBe(true)
  })

  it('should render TaskProgressBar when plan has steps', async () => {
    const plan: PlanEventData = {
      event_id: 'plan-1',
      timestamp: Date.now(),
      steps: [
        { event_id: 'step-1', timestamp: Date.now(), status: 'completed', id: '1', description: 'Step 1' },
        { event_id: 'step-2', timestamp: Date.now(), status: 'running', id: '2', description: 'Step 2' },
      ],
    }

    const wrapper = mount(ToolPanel, {
      props: {
        ...defaultProps,
        plan,
        isLoading: false,
        isThinking: false,
      },
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    const progressBar = wrapper.findComponent({ name: 'TaskProgressBar' })
    expect(progressBar.exists()).toBe(true)
  })

  it('should not render TaskProgressBar when plan has no steps', async () => {
    const plan: PlanEventData = {
      event_id: 'plan-1',
      timestamp: Date.now(),
      steps: [],
    }

    const wrapper = mount(ToolPanel, {
      props: {
        ...defaultProps,
        plan,
      },
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    const progressBar = wrapper.findComponent({ name: 'TaskProgressBar' })
    expect(progressBar.exists()).toBe(false)
  })

  it('should emit jumpToRealTime when ToolPanelContent emits it', async () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    const toolPanelContent = wrapper.findComponent({ name: 'ToolPanelContent' })
    toolPanelContent.vm.$emit('jumpToRealTime')

    expect(wrapper.emitted('jumpToRealTime')).toBeTruthy()
  })

  it('should apply correct styles when shown', async () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    wrapper.vm.showToolPanel(mockToolContent, false)
    await wrapper.vm.$nextTick()

    const panel = wrapper.find('[style]')
    expect(panel.attributes('style')).toContain('opacity: 1')
  })

  it('should apply correct styles when hidden', async () => {
    const wrapper = mount(ToolPanel, {
      props: defaultProps,
    })

    // Panel is initially hidden
    const panel = wrapper.find('[style]')
    expect(panel.attributes('style')).toContain('width: 0px')
    expect(panel.attributes('style')).toContain('opacity: 0')
  })
})
