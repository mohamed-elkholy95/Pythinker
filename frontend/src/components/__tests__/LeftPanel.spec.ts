import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

const {
  routeMock,
  pushMock,
  getSessionsMock,
  getSessionsSSEMock,
  getServerConfigMock,
  stopSessionMock,
  sessionFeedData,
  refreshFeedMock,
  onStatusChangeMock,
} = vi.hoisted(() => ({
  routeMock: {
    path: '/chat',
    params: {},
    matched: [] as Array<{ meta?: Record<string, unknown> }>,
  },
  pushMock: vi.fn(),
  getSessionsMock: vi.fn(),
  getSessionsSSEMock: vi.fn(),
  getServerConfigMock: vi.fn(),
  stopSessionMock: vi.fn(),
  sessionFeedData: {
    value: [] as Array<Record<string, unknown>>,
  },
  refreshFeedMock: vi.fn(),
  onStatusChangeMock: vi.fn(),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return {
    ...actual,
    useRoute: () => routeMock,
    useRouter: () => ({
      push: pushMock,
    }),
  }
})

vi.mock('../../composables/useLeftPanel', () => ({
  useLeftPanel: () => ({
    isLeftPanelShow: { value: true },
    toggleLeftPanel: vi.fn(),
    hideLeftPanel: vi.fn(),
  }),
}))

vi.mock('../api/agent', () => ({
  stopSession: stopSessionMock,
  getSessions: getSessionsMock,
  getSessionsSSE: getSessionsSSEMock,
}))

vi.mock('@/api/settings', () => ({
  getServerConfig: getServerConfigMock,
}))

vi.mock('@/composables/useSettingsDialog', () => ({
  useSettingsDialog: () => ({
    openSettingsDialog: vi.fn(),
  }),
}))

vi.mock('@/composables/useAuth', () => ({
  useAuth: () => ({
    currentUser: { value: { fullname: 'Mohamed Elkholy', email: 'mohamed@example.com' } },
  }),
}))

vi.mock('@/composables/useSessionStatus', () => ({
  useSessionStatus: () => ({
    onStatusChange: onStatusChangeMock,
  }),
}))

vi.mock('@/composables/useSessionListFeed', async () => {
  const vue = await vi.importActual<typeof import('vue')>('vue')
  return {
    useSessionListFeed: () => ({
      sessions: vue.ref(sessionFeedData.value),
      refresh: refreshFeedMock,
    }),
  }
})

vi.mock('@/composables/useProjectList', async () => {
  const vue = await vi.importActual<typeof import('vue')>('vue')
  return {
    useProjectList: () => ({
      projects: vue.ref([]),
      addProject: vi.fn(),
    }),
  }
})

import LeftPanel from '../LeftPanel.vue'

const SessionItemStub = defineComponent({
  name: 'SessionItem',
  props: ['session'],
  template: '<div class="session-row">{{ session.title }}</div>',
})

const mountLeftPanel = () =>
  mount(LeftPanel, {
    global: {
      stubs: {
        SessionItem: SessionItemStub,
        PythinkerLogoTextIcon: true,
        UserMenu: true,
        Popover: { template: '<div><slot /></div>' },
        PopoverTrigger: { template: '<div><slot /></div>' },
        PopoverContent: { template: '<div><slot /></div>' },
      },
    },
  })

describe('LeftPanel channel source filtering', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.path = '/chat'
    routeMock.params = {}
    routeMock.matched = []
    sessionFeedData.value = [
      {
        session_id: 'telegram-1',
        title: 'Telegram report',
        latest_message: 'Done',
        latest_message_at: 1710000000,
        status: 'completed',
        unread_message_count: 0,
        is_shared: false,
        source: 'telegram',
      },
      {
        session_id: 'web-1',
        title: 'Web task',
        latest_message: 'In progress',
        latest_message_at: 1710000100,
        status: 'running',
        unread_message_count: 0,
        is_shared: false,
        source: 'web',
      },
    ]
    onStatusChangeMock.mockReturnValue(() => {})
    getSessionsMock.mockResolvedValue({
      sessions: [],
    })
    getSessionsSSEMock.mockResolvedValue(() => {})
    getServerConfigMock.mockResolvedValue({
      model_name: 'gpt-5',
      model_display_name: '',
      api_base: 'https://api.openai.com/v1',
      temperature: 0.2,
      max_tokens: 4096,
      llm_provider: 'openai',
      search_provider: 'bing',
      search_provider_chain: ['bing'],
      configured_search_keys: ['bing'],
    })
  })

  it('supports All / Telegram / Web filter controls in main workspace', async () => {
    const wrapper = mountLeftPanel()
    await flushPromises()

    const homeLink = wrapper.find('[data-testid="workspace-sidebar-brand-link"]')
    expect(homeLink.exists()).toBe(true)
    await homeLink.trigger('click')
    expect(pushMock).toHaveBeenCalledWith('/')
    expect(wrapper.find('[data-testid="session-source-filter-trigger"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Telegram report')
    expect(wrapper.text()).toContain('Web task')

    await wrapper.find('[data-testid="session-source-filter-telegram"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Telegram report')
    expect(wrapper.text()).not.toContain('Web task')

    await wrapper.find('[data-testid="session-source-filter-web"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Web task')
    expect(wrapper.text()).not.toContain('Telegram report')
  })

  it('forces Telegram-only list and hides source filters in Agents workspace', async () => {
    routeMock.path = '/chat/agents'
    routeMock.matched = [{ meta: { workspace: 'agents' } }]

    const wrapper = mountLeftPanel()
    await flushPromises()

    expect(wrapper.find('[data-testid="session-source-filter-trigger"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Telegram report')
    expect(wrapper.text()).not.toContain('Web task')
  })
})
