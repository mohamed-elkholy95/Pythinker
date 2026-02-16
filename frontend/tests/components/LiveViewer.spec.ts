import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LiveViewer from '@/components/LiveViewer.vue'

describe('LiveViewer (CDP-only)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders SandboxViewer with correct props', async () => {
    const wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
        viewOnly: true,
        quality: 80,
        maxFps: 20,
      },
      global: {
        stubs: {
          SandboxViewer: {
            template: '<div class="sandbox-viewer"></div>',
            props: ['sessionId', 'enabled', 'viewOnly', 'quality', 'maxFps', 'showStats'],
          },
        },
      },
    })

    await flushPromises()

    const viewer = wrapper.find('.sandbox-viewer')
    expect(viewer.exists()).toBe(true)
  })

  it('emits connected event from SandboxViewer', async () => {
    const wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
      },
      global: {
        stubs: {
          SandboxViewer: {
            template: '<div class="sandbox-viewer"></div>',
            emits: ['connected', 'disconnected', 'error'],
          },
        },
      },
    })

    await flushPromises()

    const sandboxViewer = wrapper.findComponent({ name: 'SandboxViewer' })
    sandboxViewer.vm.$emit('connected')
    expect(wrapper.emitted('connected')).toHaveLength(1)
  })

  it('emits disconnected event from SandboxViewer', async () => {
    const wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
      },
      global: {
        stubs: {
          SandboxViewer: {
            template: '<div class="sandbox-viewer"></div>',
            emits: ['connected', 'disconnected', 'error'],
          },
        },
      },
    })

    await flushPromises()

    const sandboxViewer = wrapper.findComponent({ name: 'SandboxViewer' })
    sandboxViewer.vm.$emit('disconnected', 'connection lost')
    expect(wrapper.emitted('disconnected')).toHaveLength(1)
    expect(wrapper.emitted('disconnected')![0]).toEqual(['connection lost'])
  })
})
