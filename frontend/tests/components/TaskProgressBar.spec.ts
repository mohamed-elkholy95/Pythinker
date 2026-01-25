/**
 * Tests for TaskProgressBar component
 * Tests progress display, timer, morphing shapes, and expand/collapse
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskProgressBar from '@/components/TaskProgressBar.vue'
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
  Check: {
    name: 'Check',
    template: '<span class="mock-check" />',
  },
}))

describe('TaskProgressBar', () => {
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
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should not render when isLoading is false', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: false,
        isThinking: false,
      },
    })

    expect(wrapper.find('.task-progress-bar').exists()).toBe(false)
  })

  it('should not render when plan has no steps', () => {
    const plan = createMockPlan([])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.find('.task-progress-bar').exists()).toBe(false)
  })

  it('should render when isLoading and has steps', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.find('.task-progress-bar').exists()).toBe(true)
  })

  it('should display current task description', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Analyzing data', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.text()).toContain('Analyzing data')
  })

  it('should display progress text', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
      { id: '3', description: 'Step 3', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.text()).toContain('2 / 3')
  })

  it('should show "Processing" when not thinking', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.text()).toContain('Processing')
  })

  it('should show "Thinking" when thinking', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: true,
      },
    })

    expect(wrapper.text()).toContain('Thinking')
  })

  it('should display timer starting at 0:00', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.text()).toContain('0:00')
  })

  it('should update timer as time passes', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    vi.advanceTimersByTime(5000) // 5 seconds
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('0:05')
  })

  it('should expand when clicked', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    // Click to expand
    await wrapper.find('.cursor-pointer').trigger('click')

    // Should show "Task Progress" header when expanded
    expect(wrapper.text()).toContain('Task Progress')
  })

  it('should show all steps when expanded', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'First step', status: 'completed' },
      { id: '2', description: 'Second step', status: 'running' },
      { id: '3', description: 'Third step', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    // Click to expand
    await wrapper.find('.cursor-pointer').trigger('click')

    expect(wrapper.text()).toContain('First step')
    expect(wrapper.text()).toContain('Second step')
    expect(wrapper.text()).toContain('Third step')
  })

  it('should show check icon for completed steps when expanded', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    // Click to expand
    await wrapper.find('.cursor-pointer').trigger('click')

    const checkIcon = wrapper.findComponent({ name: 'Check' })
    expect(checkIcon.exists()).toBe(true)
  })

  it('should collapse when clicking collapse button', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    // Expand first
    await wrapper.find('.cursor-pointer').trigger('click')
    expect(wrapper.text()).toContain('Task Progress')

    // Click collapse button
    const collapseButton = wrapper.find('button')
    await collapseButton.trigger('click')

    // ChevronUp should now be visible (collapsed state)
    const chevronUp = wrapper.findComponent({ name: 'ChevronUp' })
    expect(chevronUp.exists()).toBe(true)
  })

  it('should have thinking-shape element', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: true,
      },
    })

    const thinkingShape = wrapper.find('.thinking-shape')
    expect(thinkingShape.exists()).toBe(true)
  })

  it('should show step numbers when expanded', async () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    // Expand
    await wrapper.find('.cursor-pointer').trigger('click')

    // Step numbers should be visible
    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('2')
  })

  it('should show pending step description as current task', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Completed task', status: 'completed' },
      { id: '2', description: 'Next pending task', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.text()).toContain('Next pending task')
  })

  it('should show "Processing..." when no running or pending steps', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Completed task', status: 'completed' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    // All steps are completed but still loading
    expect(wrapper.text()).toContain('Processing...')
  })
})
