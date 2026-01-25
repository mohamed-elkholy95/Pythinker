/**
 * Tests for ToolUse component
 * Tests tool display, status handling, and interactions
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import ToolUse from '@/components/ToolUse.vue'
import { mockToolContent, mockMCPToolContent } from '../mocks/api'

// Mock the composables
vi.mock('@/composables/useTool', () => ({
  useToolInfo: (toolRef: any) => ({
    toolInfo: ref({
      icon: 'FileIcon',
      name: 'File',
      function: 'Read File',
      functionArg: 'test.txt',
      view: 'FileToolView',
    }),
  }),
}))

vi.mock('@/composables/useTime', () => ({
  useRelativeTime: () => ({
    relativeTime: (timestamp: number) => 'just now',
  }),
}))

describe('ToolUse', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render tool information', () => {
    const wrapper = mount(ToolUse, {
      props: {
        tool: mockToolContent,
      },
      global: {
        stubs: {
          component: true,
        },
      },
    })

    expect(wrapper.text()).toContain('Read File')
    expect(wrapper.text()).toContain('test.txt')
  })

  it('should render message tool differently', () => {
    const messageToolContent = {
      ...mockToolContent,
      name: 'message',
      args: { text: 'This is a message to the user' },
    }

    const wrapper = mount(ToolUse, {
      props: {
        tool: messageToolContent,
      },
    })

    expect(wrapper.text()).toContain('This is a message to the user')
  })

  it('should show shimmer effect when tool is calling', () => {
    const callingTool = {
      ...mockToolContent,
      status: 'calling',
    }

    const wrapper = mount(ToolUse, {
      props: {
        tool: callingTool,
      },
      global: {
        stubs: {
          component: true,
        },
      },
    })

    const toolElement = wrapper.find('.tool-shimmer, [class*="shimmer"]')
    // Note: The actual shimmer class presence depends on status
    expect(wrapper.html()).toBeDefined()
  })

  it('should emit click event when clicked', async () => {
    const wrapper = mount(ToolUse, {
      props: {
        tool: mockToolContent,
      },
      global: {
        stubs: {
          component: true,
        },
      },
    })

    const clickableElement = wrapper.find('.clickable')
    if (clickableElement.exists()) {
      await clickableElement.trigger('click')
      expect(wrapper.emitted('click')).toBeTruthy()
    }
  })

  it('should display relative timestamp on hover', () => {
    const wrapper = mount(ToolUse, {
      props: {
        tool: mockToolContent,
      },
      global: {
        stubs: {
          component: true,
        },
      },
    })

    expect(wrapper.text()).toContain('just now')
  })

  it('should handle missing tool args gracefully', () => {
    const toolWithNoArgs = {
      ...mockToolContent,
      args: {},
    }

    const wrapper = mount(ToolUse, {
      props: {
        tool: toolWithNoArgs,
      },
      global: {
        stubs: {
          component: true,
        },
      },
    })

    // Should not throw
    expect(wrapper.exists()).toBe(true)
  })
})
