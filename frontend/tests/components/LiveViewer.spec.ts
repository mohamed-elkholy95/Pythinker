import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import LiveViewer from '@/components/LiveViewer.vue'
import VNCViewer from '@/components/VNCViewer.vue'

describe('LiveViewer reconnection progress', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('passes reconnectAttempt=0 to VNCViewer initially', async () => {
    const wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
        prefer: 'vnc' as const
      },
      global: {
        stubs: {
          SandboxViewer: true,
          VNCViewer: {
            template: '<div class="vnc-viewer"></div>',
            props: ['sessionId', 'enabled', 'viewOnly', 'compactLoading', 'reconnectAttempt']
          }
        }
      }
    })

    await flushPromises()

    const vncViewer = wrapper.findComponent(VNCViewer)
    expect(vncViewer.exists()).toBe(true)
    expect(vncViewer.props('reconnectAttempt')).toBe(0)
  })

  it('increments reconnectAttempt when VNC disconnects', async () => {
    const wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
        prefer: 'vnc' as const
      },
      global: {
        stubs: {
          SandboxViewer: true
        }
      }
    })

    await flushPromises()

    const vncViewer = wrapper.findComponent(VNCViewer)
    expect(vncViewer.props('reconnectAttempt')).toBe(0)

    // Trigger disconnection
    vncViewer.vm.$emit('disconnected', 'test disconnect')
    await nextTick()

    // Wait for reconnection timer setup (immediate check)
    expect(vncViewer.props('reconnectAttempt')).toBe(1)
  })

  it('resets reconnectAttempt to 0 when VNC connects', async () => {
    const wrapper = mount(LiveViewer, {
      props: {
        sessionId: 'test-session',
        enabled: true,
        prefer: 'vnc' as const
      },
      global: {
        stubs: {
          SandboxViewer: true
        }
      }
    })

    await flushPromises()

    const vncViewer = wrapper.findComponent(VNCViewer)

    // Trigger disconnection
    vncViewer.vm.$emit('disconnected')
    await nextTick()
    expect(vncViewer.props('reconnectAttempt')).toBe(1)

    // Trigger successful connection
    vncViewer.vm.$emit('connected')
    await nextTick()
    expect(vncViewer.props('reconnectAttempt')).toBe(0)
  })
})
