import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import VNCViewer from '@/components/VNCViewer.vue'

describe('VNCViewer reconnection progress', () => {
  it('accepts reconnectAttempt prop with default value 0', () => {
    const wrapper = mount(VNCViewer, {
      props: { sessionId: 'test-session' },
      global: {
        stubs: {
          LoadingState: true
        }
      }
    })

    expect(wrapper.props('reconnectAttempt')).toBe(0)
  })

  it('accepts reconnectAttempt prop when provided', () => {
    const wrapper = mount(VNCViewer, {
      props: {
        sessionId: 'test-session',
        reconnectAttempt: 5
      },
      global: {
        stubs: {
          LoadingState: true
        }
      }
    })

    expect(wrapper.props('reconnectAttempt')).toBe(5)
  })

  it('shows "Connecting..." when reconnectAttempt is 0', async () => {
    const wrapper = mount(VNCViewer, {
      props: {
        sessionId: 'test-session',
        reconnectAttempt: 0
      },
      global: {
        stubs: {
          LoadingState: true
        }
      }
    })

    await wrapper.vm.$nextTick()

    // Check internal statusText value through component instance
    // The watcher should set statusText to "Connecting..." when reconnectAttempt is 0
    const vm = wrapper.vm as any
    expect(vm.statusText).toBe('Connecting...')
  })

  it('shows reconnection progress when reconnectAttempt > 0', async () => {
    const wrapper = mount(VNCViewer, {
      props: {
        sessionId: 'test-session',
        reconnectAttempt: 5
      },
      global: {
        stubs: {
          LoadingState: true
        }
      }
    })

    await wrapper.vm.$nextTick()

    // Check internal statusText value
    const vm = wrapper.vm as any
    expect(vm.statusText).toBe('Reconnecting (attempt 5/30)...')
  })

  it('updates statusText when reconnectAttempt prop changes', async () => {
    const wrapper = mount(VNCViewer, {
      props: {
        sessionId: 'test-session',
        reconnectAttempt: 1
      },
      global: {
        stubs: {
          LoadingState: true
        }
      }
    })

    await wrapper.vm.$nextTick()
    const vm = wrapper.vm as any
    expect(vm.statusText).toBe('Reconnecting (attempt 1/30)...')

    // Change prop
    await wrapper.setProps({ reconnectAttempt: 10 })
    await wrapper.vm.$nextTick()

    expect(vm.statusText).toBe('Reconnecting (attempt 10/30)...')
  })

  it('resets to "Connecting..." when reconnectAttempt goes to 0', async () => {
    const wrapper = mount(VNCViewer, {
      props: {
        sessionId: 'test-session',
        reconnectAttempt: 5
      },
      global: {
        stubs: {
          LoadingState: true
        }
      }
    })

    await wrapper.vm.$nextTick()
    const vm = wrapper.vm as any
    expect(vm.statusText).toBe('Reconnecting (attempt 5/30)...')

    // Reset to 0
    await wrapper.setProps({ reconnectAttempt: 0 })
    await wrapper.vm.$nextTick()

    expect(vm.statusText).toBe('Connecting...')
  })
})
