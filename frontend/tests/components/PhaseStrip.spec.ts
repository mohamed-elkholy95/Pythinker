import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PhaseStrip from '@/components/PhaseStrip.vue'

describe('PhaseStrip', () => {
  const defaultProps = {
    currentPhase: 'planning' as const,
    startTime: Date.now() - 5000,
    stepProgress: null as { current: number; total: number } | null,
  }

  it('renders all phase labels', () => {
    const wrapper = mount(PhaseStrip, { props: defaultProps })
    expect(wrapper.text()).toContain('Planning')
    expect(wrapper.text()).toContain('Searching')
    expect(wrapper.text()).toContain('Writing')
  })

  it('marks current phase as active', () => {
    const wrapper = mount(PhaseStrip, { props: defaultProps })
    const active = wrapper.find('[data-phase="planning"]')
    expect(active.classes()).toContain('phase--active')
  })

  it('marks completed phases', () => {
    const wrapper = mount(PhaseStrip, {
      props: { ...defaultProps, currentPhase: 'searching' as const },
    })
    const planning = wrapper.find('[data-phase="planning"]')
    expect(planning.classes()).toContain('phase--completed')
  })

  it('shows elapsed time', () => {
    const wrapper = mount(PhaseStrip, { props: defaultProps })
    expect(wrapper.text()).toMatch(/\d+s/)
  })

  it('shows determinate step progress when available', () => {
    const wrapper = mount(PhaseStrip, {
      props: {
        ...defaultProps,
        currentPhase: 'searching' as const,
        stepProgress: { current: 2, total: 4 },
      },
    })
    expect(wrapper.text()).toContain('2 / 4')
  })

  it('marks pending phases', () => {
    const wrapper = mount(PhaseStrip, { props: defaultProps })
    const done = wrapper.find('[data-phase="done"]')
    expect(done.classes()).toContain('phase--pending')
  })

  it('shows progress bar when step progress is available', () => {
    const wrapper = mount(PhaseStrip, {
      props: {
        currentPhase: 'searching' as const,
        startTime: Date.now(),
        stepProgress: { current: 2, total: 4 },
      },
    })
    const bar = wrapper.find('.progress-fill')
    expect(bar.exists()).toBe(true)
    expect(bar.attributes('style')).toContain('width: 50%')
  })

  it('hides progress bar when no step progress', () => {
    const wrapper = mount(PhaseStrip, {
      props: {
        currentPhase: 'planning' as const,
        startTime: Date.now(),
        stepProgress: null,
      },
    })
    expect(wrapper.find('.progress-bar').exists()).toBe(false)
  })
})
