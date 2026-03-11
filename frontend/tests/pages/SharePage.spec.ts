import { defineComponent, h, ref } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SharePage from '@/pages/SharePage.vue'

const mockGetSharedSession = vi.fn()

vi.mock('@/api/agent', () => ({
  getSharedSession: (...args: unknown[]) => mockGetSharedSession(...args),
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({
      currentRoute: ref({ params: { sessionId: 'shared-session-1' } }),
    }),
  }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/composables/useSessionFileList', () => ({
  useSessionFileList: () => ({
    showSessionFileList: vi.fn(),
  }),
}))

vi.mock('@/composables/useFilePanel', () => ({
  useFilePanel: () => ({
    hideFilePanel: vi.fn(),
  }),
}))

vi.mock('@/utils/toast', () => ({
  showErrorToast: vi.fn(),
  showSuccessToast: vi.fn(),
}))

vi.mock('@/utils/dom', () => ({
  copyToClipboard: vi.fn(),
}))

const replayScreenshots = ref([
  {
    id: 'shot-1',
    session_id: 'shared-session-1',
    sequence_number: 0,
    timestamp: 100,
    trigger: 'session_start',
    size_bytes: 10,
    has_thumbnail: false,
  },
  {
    id: 'shot-2',
    session_id: 'shared-session-1',
    sequence_number: 1,
    timestamp: 130,
    trigger: 'periodic',
    tool_call_id: 'tool-1',
    size_bytes: 20,
    has_thumbnail: false,
  },
])

const replayCurrentIndex = ref(1)
const mockLoadScreenshots = vi.fn(async () => undefined)
const mockReplayStepForward = vi.fn()
const mockReplayStepBackward = vi.fn()
const mockReplaySeekByProgress = vi.fn()

vi.mock('@/composables/useScreenshotReplay', () => ({
  useScreenshotReplay: () => ({
    screenshots: replayScreenshots,
    currentIndex: replayCurrentIndex,
    currentScreenshot: ref(replayScreenshots.value[1]),
    currentScreenshotUrl: ref('blob:shared-shot-2'),
    progress: ref(100),
    canStepForward: ref(false),
    canStepBackward: ref(true),
    currentTimestamp: ref(130),
    hasScreenshots: ref(true),
    isLoading: ref(false),
    loadScreenshots: mockLoadScreenshots,
    stepForward: mockReplayStepForward,
    stepBackward: mockReplayStepBackward,
    seekByProgress: mockReplaySeekByProgress,
  }),
}))

const TimelinePlayerStub = defineComponent({
  name: 'TimelinePlayer',
  props: {
    events: {
      type: Array,
      required: true,
    },
  },
  template: '<div data-test="timeline-player">{{ events.length }}</div>',
})

const ChatMessageStub = defineComponent({
  name: 'ChatMessage',
  props: {
    message: {
      type: Object,
      required: true,
    },
  },
  setup(props) {
    return () => h('div', {
      'data-message-type': props.message.type,
      'data-message-content': JSON.stringify(props.message.content),
    })
  },
})

const SimpleBarStub = defineComponent({
  name: 'SimpleBar',
  emits: ['scroll'],
  setup(_props, { expose, slots }) {
    expose({
      scrollToBottom: vi.fn(),
    })
    return () => h('div', slots.default?.())
  },
})

const ToolPanelStub = defineComponent({
  name: 'ToolPanel',
  props: {
    isReplayMode: Boolean,
    replayScreenshots: {
      type: Array,
      default: () => [],
    },
  },
  setup(_props, { expose }) {
    expose({
      hideToolPanel: vi.fn(),
    })
    return () => null
  },
})

describe('SharePage replay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGetSharedSession.mockReset()
    mockLoadScreenshots.mockClear()
    mockReplayStepForward.mockClear()
    mockReplayStepBackward.mockClear()
    mockReplaySeekByProgress.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('filters stream events from timeline replay and renders report events', async () => {
    mockGetSharedSession.mockResolvedValue({
      session_id: 'shared-session-1',
      title: 'Shared replay',
      status: 'completed',
      events: [
        {
          event: 'message',
          data: {
            event_id: 'message-1',
            timestamp: 100,
            role: 'assistant',
            content: 'Starting analysis',
          },
        },
        {
          event: 'progress',
          data: {
            event_id: 'progress-1',
            timestamp: 110,
            phase: 'planning',
            message: 'Planning the workflow',
          },
        },
        {
          event: 'progress',
          data: {
            event_id: 'progress-heartbeat-1',
            timestamp: 111,
            phase: 'heartbeat',
            message: 'Still alive',
          },
        },
        {
          event: 'progress',
          data: {
            event_id: 'progress-waiting-1',
            timestamp: 112,
            phase: 'waiting',
            message: 'Still working on your request...',
          },
        },
        {
          event: 'stream',
          data: {
            event_id: 'stream-1',
            timestamp: 120,
            content: 'token chunk',
            phase: 'thinking',
            is_final: false,
          },
        },
        {
          event: 'tool_stream',
          data: {
            event_id: 'tool-stream-1',
            timestamp: 125,
            tool_call_id: 'tool-1',
            tool_name: 'file',
            function_name: 'file_write',
            partial_content: 'draft',
          },
        },
        {
          event: 'report',
          data: {
            event_id: 'report-event-1',
            timestamp: 130,
            id: 'report-1',
            title: 'Final Report',
            content: '# Final report',
            attachments: [],
            sources: [],
          },
        },
      ],
      is_shared: true,
    })

    const wrapper = shallowMount(SharePage, {
      global: {
        stubs: {
          SimpleBar: SimpleBarStub,
          ChatMessage: ChatMessageStub,
          LoadingIndicator: true,
          PlanPanel: true,
          TimelinePlayer: TimelinePlayerStub,
          ToolPanel: ToolPanelStub,
          Bot: true,
          PythinkerLogoTextIcon: true,
          Link: true,
          FileSearch: true,
          ArrowDown: true,
        },
      },
    })

    await flushPromises()
    await vi.advanceTimersByTimeAsync(4000)
    await flushPromises()

    const renderedTypes = wrapper
      .findAll('[data-message-type]')
      .map((node) => node.attributes('data-message-type'))

    expect(renderedTypes).toContain('report')

    const timeline = wrapper.find('[data-test="timeline-player"]')
    expect(timeline.exists()).toBe(true)
    expect(timeline.text()).toBe('3')

    const toolPanel = wrapper.findComponent(ToolPanelStub)
    expect(toolPanel.props('isReplayMode')).toBe(true)
    expect((toolPanel.props('replayScreenshots') as unknown[])).toHaveLength(2)
    expect(mockLoadScreenshots).toHaveBeenCalled()
  })

  it('renders persisted phase, thought, and tool progress events during shared replay', async () => {
    mockGetSharedSession.mockResolvedValue({
      session_id: 'shared-session-1',
      title: 'Shared replay',
      status: 'completed',
      events: [
        {
          event: 'phase',
          data: {
            event_id: 'phase-1',
            timestamp: 100,
            phase_id: 'phase-a',
            phase_type: 'research',
            label: 'Research',
            status: 'started',
          },
        },
        {
          event: 'step',
          data: {
            event_id: 'step-1',
            timestamp: 110,
            id: 'step-a',
            description: 'Inspect the site',
            status: 'running',
            phase_id: 'phase-a',
          },
        },
        {
          event: 'tool',
          data: {
            event_id: 'tool-1',
            timestamp: 120,
            tool_call_id: 'tool-a',
            name: 'browser',
            function: 'browser_navigate',
            args: { url: 'https://example.com' },
            status: 'calling',
          },
        },
        {
          event: 'tool_progress',
          data: {
            event_id: 'tool-progress-1',
            timestamp: 125,
            tool_call_id: 'tool-a',
            tool_name: 'browser',
            function_name: 'browser_navigate',
            progress_percent: 60,
            current_step: 'Collecting DOM',
            steps_completed: 3,
            steps_total: 5,
            elapsed_ms: 2500,
          },
        },
        {
          event: 'thought',
          data: {
            event_id: 'thought-1',
            timestamp: 130,
            status: 'thought',
            thought_type: 'analysis',
            content: 'The navigation succeeded and the page is stable.',
          },
        },
      ],
      is_shared: true,
    })

    const wrapper = shallowMount(SharePage, {
      global: {
        stubs: {
          SimpleBar: SimpleBarStub,
          ChatMessage: ChatMessageStub,
          LoadingIndicator: true,
          PlanPanel: true,
          TimelinePlayer: TimelinePlayerStub,
          ToolPanel: ToolPanelStub,
          Bot: true,
          PythinkerLogoTextIcon: true,
          Link: true,
          FileSearch: true,
          ArrowDown: true,
        },
      },
    })

    await flushPromises()

    const renderedTypes = wrapper
      .findAll('[data-message-type]')
      .map((node) => node.attributes('data-message-type'))

    expect(renderedTypes).toContain('phase')

    const stepMessage = wrapper
      .findAll('[data-message-type="step"]')
      .at(0)

    expect(stepMessage).toBeDefined()

    const stepContent = JSON.parse(stepMessage!.attributes('data-message-content') || '{}') as {
      tools?: Array<{ progress_percent?: number; current_step?: string }>
      items?: Array<{ type?: string }>
    }

    expect(stepContent.tools?.[0]?.progress_percent).toBe(60)
    expect(stepContent.tools?.[0]?.current_step).toBe('Collecting DOM')
    expect(stepContent.items?.some((item) => item.type === 'thought')).toBe(true)
  })
})
