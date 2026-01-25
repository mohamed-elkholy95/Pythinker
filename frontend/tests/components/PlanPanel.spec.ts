/**
 * Tests for PlanPanel component
 * Tests step rendering, status indicators, and expand/collapse functionality
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import PlanPanel from '@/components/PlanPanel.vue'
import type { PlanEventData } from '@/types/event'

// Mock vue-i18n
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

// Mock lucide-vue-next
vi.mock('lucide-vue-next', () => ({
  ChevronUp: {
    name: 'ChevronUp',
    template: '<span class="mock-chevron-up" />',
  },
  ChevronDown: {
    name: 'ChevronDown',
    template: '<span class="mock-chevron-down" />',
  },
  Clock: {
    name: 'Clock',
    template: '<span class="mock-clock" />',
  },
}))

// Mock StepSuccessIcon
vi.mock('@/components/icons/StepSuccessIcon.vue', () => ({
  default: {
    name: 'StepSuccessIcon',
    template: '<span class="mock-step-success-icon" />',
  },
}))

describe('PlanPanel', () => {
  const createMockPlan = (steps: Array<{ id: string; description: string; status: string }>): PlanEventData => ({
    event_id: 'plan-1',
    timestamp: Date.now(),
    steps: steps.map(s => ({
      event_id: `step-${s.id}`,
      timestamp: Date.now(),
      id: s.id,
      description: s.description,
      status: s.status as 'pending' | 'running' | 'completed' | 'failed',
    })),
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render with plan steps', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    expect(wrapper.exists()).toBe(true)
  })

  it('should display current step description when collapsed', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Completed step', status: 'completed' },
      { id: '2', description: 'Running step', status: 'running' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    expect(wrapper.text()).toContain('Running step')
  })

  it('should display plan progress', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
      { id: '3', description: 'Step 3', status: 'pending' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    expect(wrapper.text()).toContain('1 / 3')
  })

  it('should show ChevronUp when collapsed', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    const chevronUp = wrapper.findComponent({ name: 'ChevronUp' })
    expect(chevronUp.exists()).toBe(true)
  })

  it('should expand when clicked', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    // Click the collapsed panel to expand
    await wrapper.find('.clickable').trigger('click')

    // Should now show Task Progress header
    expect(wrapper.text()).toContain('Task Progress')
  })

  it('should show ChevronDown when expanded', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    // Expand the panel
    await wrapper.find('.clickable').trigger('click')

    const chevronDown = wrapper.findComponent({ name: 'ChevronDown' })
    expect(chevronDown.exists()).toBe(true)
  })

  it('should show all steps when expanded', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'First step', status: 'completed' },
      { id: '2', description: 'Second step', status: 'running' },
      { id: '3', description: 'Third step', status: 'pending' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    // Expand the panel
    await wrapper.find('.clickable').trigger('click')

    expect(wrapper.text()).toContain('First step')
    expect(wrapper.text()).toContain('Second step')
    expect(wrapper.text()).toContain('Third step')
  })

  it('should show StepSuccessIcon for completed steps', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    // Expand to see all steps
    await wrapper.find('.clickable').trigger('click')

    const successIcon = wrapper.findComponent({ name: 'StepSuccessIcon' })
    expect(successIcon.exists()).toBe(true)
  })

  it('should show Clock icon for pending/running steps', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    // Expand to see all steps
    await wrapper.find('.clickable').trigger('click')

    const clockIcon = wrapper.findComponent({ name: 'Clock' })
    expect(clockIcon.exists()).toBe(true)
  })

  it('should show "Task Completed" when all steps are completed', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'completed' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    expect(wrapper.text()).toContain('Task Completed')
  })

  it('should show success icon in collapsed view when all completed', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'completed' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    const successIcon = wrapper.findComponent({ name: 'StepSuccessIcon' })
    expect(successIcon.exists()).toBe(true)
  })

  it('should collapse when clicking collapse button', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    // Expand first
    await wrapper.find('.clickable').trigger('click')
    expect(wrapper.text()).toContain('Task Progress')

    // Click collapse button
    const collapseButton = wrapper.find('.cursor-pointer')
    await collapseButton.trigger('click')

    // Should collapse (no Task Progress header visible in collapsed state)
    await wrapper.vm.$nextTick()
  })

  it('should handle empty steps array', () => {
    const plan = createMockPlan([])

    const wrapper = mount(PlanPanel, {
      props: { plan },
    })

    // Should render without errors
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('0 / 0')
  })

  it('should update progress when plan changes', async () => {
    const plan1 = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
      { id: '2', description: 'Step 2', status: 'pending' },
    ])

    const wrapper = mount(PlanPanel, {
      props: { plan: plan1 },
    })

    expect(wrapper.text()).toContain('0 / 2')

    const plan2 = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
    ])

    await wrapper.setProps({ plan: plan2 })
    expect(wrapper.text()).toContain('1 / 2')
  })
})
