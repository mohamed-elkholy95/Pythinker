import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PythinkerLogoTextIcon from '../PythinkerLogoTextIcon.vue'

describe('PythinkerLogoTextIcon', () => {
  it('renders a left-aligned scalable wordmark svg', () => {
    const wrapper = mount(PythinkerLogoTextIcon, {
      props: {
        width: 120,
        height: 24,
      },
    })

    const svg = wrapper.get('[data-testid="pythinker-wordmark"]')
    const text = wrapper.get('text')

    expect(svg.attributes('viewBox')).toBe('0 0 164 32')
    expect(svg.attributes('preserveAspectRatio')).toBe('xMinYMid meet')
    expect(text.attributes('text-anchor')).toBe('start')
    expect(text.text()).toBe('Pythinker')
  })

  it('splits the wordmark into styled spans for a more polished look', () => {
    const wrapper = mount(PythinkerLogoTextIcon)
    const spans = wrapper.findAll('tspan')

    expect(spans).toHaveLength(2)
    expect(spans[0].text()).toBe('Py')
    expect(spans[1].text()).toBe('thinker')
  })
})
