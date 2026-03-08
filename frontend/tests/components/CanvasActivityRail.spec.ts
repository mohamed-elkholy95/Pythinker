import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CanvasActivityRail from '@/components/canvas/CanvasActivityRail.vue'

describe('CanvasActivityRail', () => {
  it('renders session, version, operation, and changed element metadata', () => {
    const wrapper = mount(CanvasActivityRail, {
      props: {
        sessionId: 'session-123456',
        serverVersion: 6,
        pendingRemoteVersion: 7,
        elementCount: 24,
        lastOperation: 'Modified hero image',
        lastSource: 'agent',
        changedElementIds: ['el-1', 'el-2', 'el-3'],
        updatedAt: '2026-03-08T16:00:00Z',
      },
    })

    expect(wrapper.text()).toContain('session-123456')
    expect(wrapper.text()).toContain('v6')
    expect(wrapper.text()).toContain('v7 pending')
    expect(wrapper.text()).toContain('24 elements')
    expect(wrapper.text()).toContain('Modified hero image')
    expect(wrapper.text()).toContain('3 changed')
  })
})
