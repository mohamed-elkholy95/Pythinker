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
})
