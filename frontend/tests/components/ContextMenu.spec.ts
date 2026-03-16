import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ContextMenu from '@/components/ui/ContextMenu.vue'
import { useContextMenu, createMenuItem } from '@/composables/useContextMenu'

describe('ContextMenu', () => {
  const { showContextMenu, hideContextMenu } = useContextMenu()
  let target: HTMLButtonElement

  beforeEach(() => {
    target = document.createElement('button')
    document.body.appendChild(target)
    Object.defineProperty(target, 'getBoundingClientRect', {
      value: () => ({
        left: 100,
        top: 100,
        right: 140,
        bottom: 140,
        width: 40,
        height: 40,
        x: 100,
        y: 100,
        toJSON: () => ({}),
      }),
      configurable: true,
    })
  })

  afterEach(() => {
    hideContextMenu()
    target.remove()
  })

  it('renders menu above mobile sidebar layers with elevated z-index', async () => {
    showContextMenu('session-1', target, [createMenuItem('rename', 'Rename')])

    const wrapper = mount(ContextMenu)
    await nextTick()

    const menu = wrapper.find('[role="dialog"]')
    expect(menu.exists()).toBe(true)
    expect(menu.attributes('style')).toContain('z-index: 80')
  })
})
