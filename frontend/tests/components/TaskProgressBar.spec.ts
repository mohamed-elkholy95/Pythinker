/**
 * Tests for TaskProgressBar component
 * Tests progress display, timer, morphing shapes, and expand/collapse
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskProgressBar from '@/components/TaskProgressBar.vue'
import type { PlanEventData } from '@/types/event'

// Mock xterm to avoid canvas issues in jsdom
vi.mock('xterm', () => ({
  Terminal: vi.fn().mockImplementation(() => ({
    open: vi.fn(),
    write: vi.fn(),
    dispose: vi.fn(),
    onData: vi.fn(),
    onResize: vi.fn(),
    loadAddon: vi.fn(),
  })),
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn().mockImplementation(() => ({
    fit: vi.fn(),
    dispose: vi.fn(),
  })),
}))

vi.mock('@xterm/addon-web-links', () => ({
  WebLinksAddon: vi.fn().mockImplementation(() => ({
    dispose: vi.fn(),
  })),
}))

// Mock vue-i18n
vi.mock('vue-i18n', () => ({
  createI18n: () => ({
    global: {
      t: (key: string) => key,
      locale: { value: 'en' },
    },
    install: () => {},
  }),
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

// Mock lucide-vue-next
vi.mock('lucide-vue-next', async () => {
  const actual = await vi.importActual<typeof import('lucide-vue-next')>('lucide-vue-next')
  return {
    ...actual,
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
  Terminal: {
    name: 'Terminal',
    template: '<span class="mock-terminal" />',
  },
  Globe: {
    name: 'Globe',
    template: '<span class="mock-globe" />',
  },
  Search: {
    name: 'Search',
    template: '<span class="mock-search" />',
  },
  FileText: {
    name: 'FileText',
    template: '<span class="mock-file-text" />',
  },
  Loader2: {
    name: 'Loader2',
    template: '<span class="mock-loader2" />',
  },
  CircleCheck: {
    name: 'CircleCheck',
    template: '<span class="mock-circle-check" />',
  },
  MonitorPlay: {
    name: 'MonitorPlay',
    template: '<span class="mock-monitor-play" />',
  },
}})

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

  it('should render even when isLoading is false if plan has steps', () => {
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

    // Component is visible if plan has steps, regardless of isLoading
    expect(wrapper.find('.task-progress-bar').exists()).toBe(true)
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

    // Collapsed counter shows "currentCount / totalCount".
    // Running step is at index 1, so currentCount = 2, totalCount = 3.
    const compactProgress = wrapper.find('.collapsed-counter').text().replace(/\s+/g, '')
    expect(compactProgress).toBe('2/3')
  })

  it('shows 0/total while loading at initial pending-only state', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'pending' },
      { id: '2', description: 'Step 2', status: 'pending' },
      { id: '3', description: 'Step 3', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    // No running step and 0 completed, so currentCount = 0
    const compactProgress = wrapper.find('.collapsed-counter').text().replace(/\s+/g, '')
    expect(compactProgress).toBe('0/3')
  })

  it('shows 0/total at initial pending-only state when idle', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'pending' },
      { id: '2', description: 'Step 2', status: 'pending' },
      { id: '3', description: 'Step 3', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: false,
        isThinking: false,
      },
    })

    const compactProgress = wrapper.find('.collapsed-counter').text().replace(/\s+/g, '')
    expect(compactProgress).toBe('0/3')
  })

  it('should show running task description in collapsed view', () => {
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

    // Collapsed view shows task description and counter
    expect(wrapper.text()).toContain('Step 1')
    expect(wrapper.find('.collapsed-counter').exists()).toBe(true)
  })

  it('should show running dot indicator when a step is running', () => {
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

    // Collapsed view shows a running dot for active steps
    expect(wrapper.find('.collapsed-running-dot').exists()).toBe(true)
  })

  it('should display timer in expanded view starting at 0:00', async () => {
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

    // Expand to see timer
    await wrapper.find('.progress-bar-collapsed').trigger('click')

    expect(wrapper.text()).toContain('0:00')
  })

  it('should update timer as time passes in expanded view', async () => {
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

    // Expand to see timer
    await wrapper.find('.progress-bar-collapsed').trigger('click')

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
    await wrapper.find('.progress-bar-collapsed').trigger('click')

    // Should show header when expanded (component uses "Pythinker's computer" header)
    expect(wrapper.text()).toContain("Pythinker's computer")
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
    await wrapper.find('.progress-bar-collapsed').trigger('click')

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
    await wrapper.find('.progress-bar-collapsed').trigger('click')

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
    await wrapper.find('.progress-bar-collapsed').trigger('click')
    expect(wrapper.text()).toContain("Pythinker's computer")

    // Click collapse button (ChevronDown in expanded state)
    const collapseButton = wrapper.findComponent({ name: 'ChevronDown' })
    await collapseButton.trigger('click')

    // ChevronUp should now be visible (collapsed state)
    const chevronUp = wrapper.findComponent({ name: 'ChevronUp' })
    expect(chevronUp.exists()).toBe(true)
  })

  it('should not render status morph animation element in collapsed view', () => {
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

    const statusMorph = wrapper.find('.status-morph')
    expect(statusMorph.exists()).toBe(false)
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
    await wrapper.find('.progress-bar-collapsed').trigger('click')

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

  it('should show completed step description when all steps completed', () => {
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

    // When all steps are completed, shows the completed task description
    expect(wrapper.text()).toContain('Completed task')
  })

  it('renders a bare completed check in collapsed state when all tasks are complete', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Completed task', status: 'completed' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: false,
        isThinking: false,
      },
    })

    const statusIcon = wrapper.find('.collapsed-status-icon')
    const checkIcon = wrapper.find('.mock-check')

    expect(statusIcon.classes()).toContain('collapsed-status-icon-complete')
    expect(checkIcon.classes()).toContain('collapsed-complete-check')
  })

  it('shows task description while summary is streaming', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Draft report', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
        isSummaryStreaming: true,
        summaryStreamText: '## Partial summary',
      },
    })

    // Collapsed view shows the running step description
    expect(wrapper.text()).toContain('Draft report')
  })

  it('forwards summary stream text to mini preview', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'running' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
        showThumbnail: true,
        sessionId: 'session-1',
        isSummaryStreaming: true,
        summaryStreamText: 'summary text',
      },
    })

    const miniPreview = wrapper.findComponent({ name: 'LiveMiniPreview' })
    expect(miniPreview.exists()).toBe(true)
    expect(miniPreview.props('summaryStreamText')).toBe('summary text')
  })

  it('does not render collapsed timeline rail', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'running' },
      { id: '3', description: 'Step 3', status: 'pending' },
      { id: '4', description: 'Step 4', status: 'pending' },
      { id: '5', description: 'Step 5', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    expect(wrapper.find('.collapsed-step-rail').exists()).toBe(false)
    expect(wrapper.find('.collapsed-step-node').exists()).toBe(false)
    expect(wrapper.find('.collapsed-step-line').exists()).toBe(false)
  })

  it('shows completedCount in gap state when loading (no running step)', () => {
    // After step 1 completes but step 2 hasn't started running yet,
    // currentCount = completedCount (no running step to anchor on)
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'pending' },
      { id: '3', description: 'Step 3', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    const compactProgress = wrapper.find('.collapsed-counter').text().replace(/\s+/g, '')
    expect(compactProgress).toBe('1/3')
  })

  it('does not advance counter past total when all steps completed and loading', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'completed' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: true,
        isThinking: false,
      },
    })

    const compactProgress = wrapper.find('.collapsed-counter').text().replace(/\s+/g, '')
    expect(compactProgress).toBe('2/2')
  })

  it('shows completedCount when idle between steps (not loading)', () => {
    const plan = createMockPlan([
      { id: '1', description: 'Step 1', status: 'completed' },
      { id: '2', description: 'Step 2', status: 'pending' },
    ])

    const wrapper = mount(TaskProgressBar, {
      props: {
        plan,
        isLoading: false,
        isThinking: false,
      },
    })

    // When idle, show actual completedCount without advancing
    const compactProgress = wrapper.find('.collapsed-counter').text().replace(/\s+/g, '')
    expect(compactProgress).toBe('1/2')
  })

  it('renders expanded dotted connectors between task nodes', async () => {
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

    await wrapper.find('.progress-bar-collapsed').trigger('click')

    const connectors = wrapper.findAll('.task-timeline-line')
    expect(connectors).toHaveLength(2)
  })
})
