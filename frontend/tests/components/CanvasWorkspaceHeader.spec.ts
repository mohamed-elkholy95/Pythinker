import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CanvasWorkspaceHeader from '@/components/canvas/CanvasWorkspaceHeader.vue'

describe('CanvasWorkspaceHeader', () => {
  it('renders project, sync, mode, session, and version metadata', () => {
    const wrapper = mount(CanvasWorkspaceHeader, {
      props: {
        projectName: 'Studio Board',
        syncStatus: 'live',
        mode: 'agent',
        sessionId: 'session-123456',
        version: 7,
        elementCount: 18,
        primaryActionLabel: 'Open Studio',
      },
    })

    expect(wrapper.text()).toContain('Studio Board')
    expect(wrapper.text()).toContain('Live')
    expect(wrapper.text()).toContain('Agent')
    expect(wrapper.text()).toContain('session-123456')
    expect(wrapper.text()).toContain('v7')
    expect(wrapper.text()).toContain('18 elements')
  })

  it('emits primary and secondary actions', async () => {
    const wrapper = mount(CanvasWorkspaceHeader, {
      props: {
        projectName: 'Studio Board',
        syncStatus: 'saved',
        mode: 'manual',
        version: 3,
        primaryActionLabel: 'Export',
        secondaryActionLabel: 'Return to Chat',
      },
    })

    await wrapper.get('[data-testid="canvas-header-primary"]').trigger('click')
    await wrapper.get('[data-testid="canvas-header-secondary"]').trigger('click')

    expect(wrapper.emitted('primary-action')).toHaveLength(1)
    expect(wrapper.emitted('secondary-action')).toHaveLength(1)
  })
})
