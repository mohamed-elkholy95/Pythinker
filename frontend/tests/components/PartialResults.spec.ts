import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PartialResults from '@/components/PartialResults.vue'

describe('PartialResults', () => {
  it('renders nothing when results empty', () => {
    const wrapper = mount(PartialResults, { props: { results: [] } })
    expect(wrapper.find('.partial-results').exists()).toBe(false)
  })

  it('renders headline for each result', () => {
    const wrapper = mount(PartialResults, {
      props: {
        results: [
          { stepIndex: 0, stepTitle: 'Search', headline: 'Found 12 results', sourcesCount: 12 },
          { stepIndex: 1, stepTitle: 'Read', headline: 'Visited: AI Guide', sourcesCount: 0 },
        ],
      },
    })
    expect(wrapper.text()).toContain('Found 12 results')
    expect(wrapper.text()).toContain('Visited: AI Guide')
    expect(wrapper.text()).toContain('12 sources')
  })

  it('does not render the findings header', () => {
    const wrapper = mount(PartialResults, {
      props: {
        results: [{ stepIndex: 0, stepTitle: 'Search', headline: 'Found results', sourcesCount: 3 }],
      },
    })
    expect(wrapper.text()).not.toContain('Findings so far')
    expect(wrapper.find('.partial-results-header').exists()).toBe(false)
  })

  it('hides sources count when zero', () => {
    const wrapper = mount(PartialResults, {
      props: {
        results: [{ stepIndex: 0, stepTitle: 'Read', headline: 'Visited page', sourcesCount: 0 }],
      },
    })
    expect(wrapper.text()).not.toContain('sources')
  })
})
