import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskCompletedFooter from '@/components/report/TaskCompletedFooter.vue'

describe('TaskCompletedFooter', () => {
  it('renders task completed status and rating prompt', () => {
    const wrapper = mount(TaskCompletedFooter)

    expect(wrapper.text()).toContain('Task completed')
    expect(wrapper.text()).toContain('How was this result?')
  })

  it('emits rate event after star click and submit', async () => {
    const wrapper = mount(TaskCompletedFooter)
    const starButtons = wrapper.findAll('button.star-btn')

    expect(starButtons.length).toBe(5)

    // Phase 1 → Phase 2: clicking a star expands the rating card
    await starButtons[3].trigger('click')
    expect(wrapper.emitted('rate')).toBeFalsy()

    // Phase 2 → Phase 3: clicking "Skip comment" emits the rating
    const skipBtn = wrapper.find('.btn-skip')
    await skipBtn.trigger('click')

    expect(wrapper.emitted('rate')).toBeTruthy()
    expect(wrapper.emitted('rate')?.[0]).toEqual([4])
  })
})
