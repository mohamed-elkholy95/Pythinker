import { describe, expect, it } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import VncMiniPreview from '@/components/VncMiniPreview.vue'

describe('VncMiniPreview', () => {
  it('does not render live VNC without tool context', () => {
    const wrapper = shallowMount(VncMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
      },
    })

    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(false)
  })

  it('renders live VNC when browser tool context is active', () => {
    const wrapper = shallowMount(VncMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        toolName: 'browser',
        toolFunction: 'browser_navigate',
        isActive: true,
      },
    })

    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(true)
  })

  it('does not render live VNC while initializing', () => {
    const wrapper = shallowMount(VncMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        toolName: 'browser',
        toolFunction: 'browser_navigate',
        isActive: true,
        isInitializing: true,
      },
    })

    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(false)
  })

  it('renders final replay screenshot when session is complete', () => {
    const wrapper = shallowMount(VncMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSessionComplete: true,
        replayScreenshotUrl: 'blob:final-screenshot',
        isActive: false,
      },
    })

    expect(wrapper.find('.final-screenshot-image').exists()).toBe(true)
    expect(wrapper.find('.completion-badge').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(false)
  })

  it('renders completed placeholder when replay screenshot is unavailable', () => {
    const wrapper = shallowMount(VncMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSessionComplete: true,
        isActive: false,
      },
    })

    expect(wrapper.find('.final-screenshot-placeholder').exists()).toBe(true)
    expect(wrapper.text()).toContain('Session Complete')
  })

  it('does not show initializing dots when session is complete', () => {
    const wrapper = shallowMount(VncMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSessionComplete: true,
        isActive: false,
      },
    })

    expect(wrapper.find('.init-loading-dots').exists()).toBe(false)
  })
})
