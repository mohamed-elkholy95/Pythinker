import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PlanningCard from '@/components/PlanningCard.vue'
import type { PlanningPhase } from '@/types/event'

describe('PlanningCard', () => {
  it('renders simple agent-thinking language and phase description', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'planning',
        message: 'Collecting trusted sources and organizing plan steps.',
        progressPercent: 47,
      },
    })

    expect(wrapper.text()).toContain('Agent is thinking')
    // When a non-empty message is provided, it replaces the phase description
    expect(wrapper.text()).toContain('Collecting trusted sources and organizing plan steps.')
  })

  it('falls back to phase-specific guidance when progress message is empty', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'analyzing',
        message: '   ',
        progressPercent: 24,
      },
    })

    expect(wrapper.text()).toContain('Breaking down your request')
  })

  it('always shows a clamped progress value', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'received',
        message: 'Starting.',
        progressPercent: 180,
      },
    })

    expect(wrapper.text()).toContain('100%')
  })

  it('shows indeterminate progress when percent is not available yet', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'received',
        message: 'Evaluating your request details.',
      },
    })

    expect(wrapper.text()).not.toContain('%')
    expect(wrapper.find('.progress-fill--indeterminate').exists()).toBe(true)
  })

  it('renders verifying phase with correct description', () => {
    // With a non-empty message, the message is shown instead of phase description
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'verifying' as PlanningPhase,
        message: 'Checking plan quality...',
      },
    })
    expect(wrapper.text()).toContain('Checking plan quality...')

    // With empty message, phase description is used as fallback
    const fallbackWrapper = mount(PlanningCard, {
      props: {
        phase: 'verifying' as PlanningPhase,
        message: '  ',
      },
    })
    expect(fallbackWrapper.text()).toContain('Verifying plan quality')
  })

  it('renders executing_setup phase', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        phase: 'executing_setup' as PlanningPhase,
        message: 'Preparing to execute...',
      },
    })
    expect(wrapper.text()).toContain('Preparing to execute...')

    // With empty message, phase description is used as fallback
    const fallbackWrapper = mount(PlanningCard, {
      props: {
        phase: 'executing_setup' as PlanningPhase,
        message: '',
      },
    })
    expect(fallbackWrapper.text()).toContain('Starting execution')
  })

  it('renders a custom title for plan-ready handoff state', () => {
    const wrapper = mount(PlanningCard, {
      props: {
        title: 'Plan ready',
        phase: 'executing_setup' as PlanningPhase,
        message: 'Starting execution from the approved plan.',
        progressPercent: 100,
      },
    })

    expect(wrapper.text()).toContain('Plan ready')
    expect(wrapper.text()).not.toContain('Agent is thinking')
  })
})
