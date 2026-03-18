import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CanvasSyncBanner from '@/components/canvas/CanvasSyncBanner.vue'

describe('CanvasSyncBanner', () => {
  it('renders conflict copy and emits conflict actions', async () => {
    const wrapper = mount(CanvasSyncBanner, {
      props: {
        status: 'conflict',
        title: 'Agent updated this canvas',
        description: 'A newer remote version is available.',
        primaryActionLabel: 'Apply latest',
        secondaryActionLabel: 'Keep my draft',
      },
    })

    expect(wrapper.text()).toContain('Agent updated this canvas')
    expect(wrapper.text()).toContain('Apply latest')
    expect(wrapper.text()).toContain('Keep my draft')

    await wrapper.get('[data-testid="canvas-sync-primary"]').trigger('click')
    await wrapper.get('[data-testid="canvas-sync-secondary"]').trigger('click')

    expect(wrapper.emitted('primary-action')).toHaveLength(1)
    expect(wrapper.emitted('secondary-action')).toHaveLength(1)
  })

  it('renders stale status without secondary action', () => {
    const wrapper = mount(CanvasSyncBanner, {
      props: {
        status: 'stale',
        title: 'Your draft is behind the latest agent canvas',
        description: 'Apply the newer server version when you are ready.',
        primaryActionLabel: 'Reload canvas',
      },
    })

    expect(wrapper.text()).toContain('Your draft is behind the latest agent canvas')
    expect(wrapper.find('[data-testid="canvas-sync-secondary"]').exists()).toBe(false)
  })
})
