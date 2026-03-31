import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SessionWarmupMessage from '@/components/SessionWarmupMessage.vue'

describe('SessionWarmupMessage', () => {
  it('renders pythinker header and initializing state by default', () => {
    const wrapper = mount(SessionWarmupMessage)

    expect(wrapper.text().toLowerCase()).toContain('pythinker')
    expect(wrapper.text()).toContain('Initializing your session')
    expect(wrapper.text()).not.toContain('Loading...')
    expect(wrapper.findAll('.warmup-dot')).toHaveLength(3)
  })

  it('shows timeout state and emits retry', async () => {
    const wrapper = mount(SessionWarmupMessage, {
      props: {
        state: 'timed_out',
      },
    })

    expect(wrapper.text()).toContain('Still getting your session ready')
    expect(wrapper.findAll('.warmup-dot')).toHaveLength(0)

    const retryButton = wrapper.find('[data-testid="warmup-retry"]')
    expect(retryButton.exists()).toBe(true)

    await retryButton.trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
  })

  it('shows thinking state text', () => {
    const wrapper = mount(SessionWarmupMessage, {
      props: {
        state: 'thinking',
      },
    })

    expect(wrapper.text()).toContain('Thinking')
    expect(wrapper.find('.warmup-thinking-indicator').exists()).toBe(true)
    expect(wrapper.findAll('.warmup-dot')).toHaveLength(0)
  })
})
