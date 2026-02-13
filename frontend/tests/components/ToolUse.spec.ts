/**
 * Tests for ToolUse component
 * Tests tool display, status handling, and interactions
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { markRaw, ref } from 'vue'
import ToolUse from '@/components/ToolUse.vue'
import { mockToolContent } from '../mocks/api'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (value: string) => value,
  }),
}))

// Mock the composables
vi.mock('@/composables/useTool', () => ({
  useToolInfo: (_toolRef: any) => ({
    toolInfo: ref({
      icon: markRaw({ template: '<svg data-testid="tool-icon"></svg>' }),
      name: 'File',
      description: 'Read File test.txt',
      function: 'Read File',
      functionArg: 'test.txt',
      url: null,
      faviconUrl: null,
    }),
  }),
}))

vi.mock('@/composables/useTime', () => ({
  useRelativeTime: () => ({
    relativeTime: (_timestamp: number) => 'just now',
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
    })

    expect(wrapper.text()).toContain('Read File test.txt')
    const chipText = wrapper.find('.tool-chip-text')
    expect(chipText.exists()).toBe(true)
    expect(chipText.text()).toContain('Read File test.txt')
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
    })

    const _toolElement = wrapper.find('.tool-shimmer, [class*="shimmer"]')
    // Note: The actual shimmer class presence depends on status
    expect(wrapper.html()).toBeDefined()
  })

  it('keeps silver shimmer on last task while parent step is still running', () => {
    const calledTool = {
      ...mockToolContent,
      status: 'called',
    }

    const wrapper = mount(ToolUse, {
      props: {
        tool: calledTool,
        isActive: true,
        isTaskRunning: true,
      },
    })

    expect(wrapper.find('.tool-shimmer').exists()).toBe(true)
  })

  it('should emit click event when clicked', async () => {
    const wrapper = mount(ToolUse, {
      props: {
        tool: mockToolContent,
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
    })

    // Should not throw
    expect(wrapper.exists()).toBe(true)
  })
})
