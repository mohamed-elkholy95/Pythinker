import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import LiveViewer from '@/components/LiveViewer.vue'

describe('LiveViewer (CDP-only)', () => {
  let wrapper: VueWrapper | null = null

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    // Clean up: unmount wrapper to prevent cross-test contamination
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
  })

  it('renders SandboxViewer with correct props', async () => {
    wrapper = mount(LiveViewer, {
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
            name: 'SandboxViewer',
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
    wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
      },
      global: {
        stubs: {
          SandboxViewer: {
            name: 'SandboxViewer',
            template: '<div class="sandbox-viewer"></div>',
            emits: ['connected', 'disconnected', 'error'],
          },
        },
      },
    })

    await flushPromises()

    const sandboxViewer = wrapper.getComponent({ name: 'SandboxViewer' })
    sandboxViewer.vm.$emit('connected')
    expect(wrapper.emitted('connected')).toHaveLength(1)
  })

  it('emits disconnected event from SandboxViewer', async () => {
    wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
      },
      global: {
        stubs: {
          SandboxViewer: {
            name: 'SandboxViewer',
            template: '<div class="sandbox-viewer"></div>',
            emits: ['connected', 'disconnected', 'error'],
          },
        },
      },
    })

    await flushPromises()

    const sandboxViewer = wrapper.getComponent({ name: 'SandboxViewer' })
    sandboxViewer.vm.$emit('disconnected', 'connection lost')
    expect(wrapper.emitted('disconnected')).toHaveLength(1)
    expect(wrapper.emitted('disconnected')![0]).toEqual(['connection lost'])
  })

  it('exposes processToolEvent and forwards events to SandboxViewer', async () => {
    const processToolEvent = vi.fn()
    wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
      },
      global: {
        stubs: {
          SandboxViewer: {
            name: 'SandboxViewer',
            template: '<div class="sandbox-viewer"></div>',
            setup(_props, { expose }) {
              expose({ processToolEvent })
              return {}
            },
          },
        },
      },
    })

    await flushPromises()
    ;(wrapper.vm as unknown as { processToolEvent: (event: Record<string, unknown>) => void }).processToolEvent({
      tool_call_id: 'abc',
      status: 'calling',
      function: 'browser_click',
      args: { coordinate_x: 10, coordinate_y: 20 },
    })
    expect(processToolEvent).toHaveBeenCalledTimes(1)
  })
})
