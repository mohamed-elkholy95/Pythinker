import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SharePage from '@/pages/SharePage.vue'

const { mockGetSharedSession, mockShowInfoToast } = vi.hoisted(() => ({
  mockGetSharedSession: vi.fn(),
  mockShowInfoToast: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    currentRoute: ref({ params: { sessionId: 'shared-session-1' } }),
    push: vi.fn(),
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (!params) return key
      return key.replace('{countdown}', String(params.countdown ?? ''))
    },
  }),
}))

vi.mock('@/api/agent', () => ({
  getSharedSession: mockGetSharedSession,
}))

vi.mock('@/utils/toast', () => ({
  showErrorToast: vi.fn(),
  showSuccessToast: vi.fn(),
  showInfoToast: mockShowInfoToast,
}))

vi.mock('@/components/SimpleBar.vue', () => ({
  default: defineComponent({
    name: 'SimpleBar',
    setup(_, { expose, slots }) {
      expose({
        scrollToBottom: vi.fn(),
        isScrolledToBottom: vi.fn(() => true),
      })
      return () => slots.default?.()
    },
  }),
}))

vi.mock('@/components/ChatMessage.vue', () => ({
  default: defineComponent({
    name: 'ChatMessage',
    template: '<div />',
  }),
}))

vi.mock('@/components/ToolPanel.vue', () => ({
  default: defineComponent({
    name: 'ToolPanel',
    setup(_, { expose }) {
      expose({
        hideToolPanel: vi.fn(),
      })
      return () => null
    },
  }),
}))

vi.mock('@/components/PlanPanel.vue', () => ({
  default: defineComponent({
    name: 'PlanPanel',
    template: '<div />',
  }),
}))

vi.mock('@/components/timeline/TimelinePlayer.vue', () => ({
  default: defineComponent({
    name: 'TimelinePlayer',
    template: '<div />',
  }),
}))

vi.mock('@/components/icons/PythinkerLogoTextIcon.vue', () => ({
  default: defineComponent({
    name: 'PythinkerLogoTextIcon',
    template: '<div />',
  }),
}))

vi.mock('@/components/ui/LoadingIndicator.vue', () => ({
  default: defineComponent({
    name: 'LoadingIndicator',
    template: '<div />',
  }),
}))

vi.mock('lucide-vue-next', () => ({
  ArrowDown: defineComponent({ name: 'ArrowDown', template: '<span />' }),
  FileSearch: defineComponent({ name: 'FileSearch', template: '<span />' }),
  Link: defineComponent({ name: 'LinkIconStub', template: '<span />' }),
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

vi.mock('@/composables/useTimeline', () => ({
  useTimeline: () => ({
    currentIndex: ref(0),
    isPlaying: ref(false),
    playbackSpeed: ref(1),
    currentTime: ref(0),
    duration: ref(0),
    progress: ref(0),
    pause: vi.fn(),
    setSpeed: vi.fn(),
    seek: vi.fn(),
    play: vi.fn(),
    reset: vi.fn(),
    stepForward: vi.fn(),
    stepBackward: vi.fn(),
  }),
}))

vi.mock('@/utils/dom', () => ({
  copyToClipboard: vi.fn(),
}))

const flushPromises = async () => {
  await Promise.resolve()
  await nextTick()
}

describe('SharePage recovery notice', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    mockGetSharedSession.mockResolvedValue({
      id: 'shared-session-1',
      title: 'Recovered session',
      status: 'completed',
      events: [],
      is_shared: true,
      latest_message: 'Recovered answer <tool_call>{"name":"browser"}</tool_call>',
      latest_message_at: 1710000005,
    })
  })

  it('shows an info toast when replay history is reconstructed from latest saved message', async () => {
    mount(SharePage)

    await flushPromises()

    expect(mockShowInfoToast).toHaveBeenCalledWith(
      'Recovered this completed task from its latest saved message. Earlier step details were unavailable.',
    )
  })

  it('shows the recovery toast only once across initial restore and auto-replay', async () => {
    mount(SharePage)

    await flushPromises()
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(mockShowInfoToast).toHaveBeenCalledTimes(1)
  })
})
