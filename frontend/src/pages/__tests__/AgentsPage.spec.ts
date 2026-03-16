import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const {
  getLinkedChannelsMock,
  generateLinkCodeMock,
  getSessionsMock,
  pushMock,
} = vi.hoisted(() => ({
  getLinkedChannelsMock: vi.fn(),
  generateLinkCodeMock: vi.fn(),
  getSessionsMock: vi.fn(),
  pushMock: vi.fn(),
}))

vi.mock('@/api/channelLinks', () => ({
  getLinkedChannels: getLinkedChannelsMock,
  generateLinkCode: generateLinkCodeMock,
}))

vi.mock('@/api/agent', () => ({
  getSessions: getSessionsMock,
}))

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return {
    ...actual,
    useRouter: () => ({
      push: pushMock,
    }),
  }
})

import AgentsPage from '../AgentsPage.vue'

const mountAgentsPage = () =>
  mount(AgentsPage, {
    global: {
      directives: {
        'auto-follow-scroll': {},
      },
    },
  })

describe('AgentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Telegram onboarding with the Link Account CTA when user is not linked', async () => {
    getLinkedChannelsMock.mockResolvedValue([])
    getSessionsMock.mockResolvedValue({ sessions: [] })

    const wrapper = mountAgentsPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Deploy your agent for web apps')
    expect(wrapper.text()).toContain('Link Account')
    expect(wrapper.text()).toContain('Works in your messenger')
  })

  it('shows linked workspace and only Telegram sessions when Telegram is linked', async () => {
    getLinkedChannelsMock.mockResolvedValue([
      {
        channel: 'telegram',
        sender_id: '5829880422|john',
        linked_at: '2026-03-03T12:00:00Z',
      },
    ])
    getSessionsMock.mockResolvedValue({
      sessions: [
        {
          session_id: 'session-1',
          title: 'Find me a Python course',
          status: 'completed',
          unread_message_count: 0,
          latest_message: 'Here are three options',
          latest_message_at: 1710000000,
          is_shared: false,
          source: 'telegram',
        },
        {
          session_id: 'session-2',
          title: 'Web session only',
          status: 'completed',
          unread_message_count: 0,
          latest_message: 'Ignore this',
          latest_message_at: 1710000100,
          is_shared: false,
          source: 'web',
        },
      ],
    })

    const wrapper = mountAgentsPage()
    await flushPromises()

    expect(pushMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Telegram connected')
    expect(wrapper.text()).toContain('Refresh chats')
    expect(wrapper.text()).toContain('Find me a Python course')
    expect(wrapper.text()).not.toContain('Web session only')
  })

  it('supports searching and status filtering for Telegram sessions', async () => {
    getLinkedChannelsMock.mockResolvedValue([
      {
        channel: 'telegram',
        sender_id: '5829880422|john',
        linked_at: '2026-03-03T12:00:00Z',
      },
    ])
    getSessionsMock.mockResolvedValue({
      sessions: [
        {
          session_id: 'session-1',
          title: 'Python onboarding',
          status: 'running',
          unread_message_count: 0,
          latest_message: 'Plan generated',
          latest_message_at: 1710000100,
          is_shared: false,
          source: 'telegram',
        },
        {
          session_id: 'session-2',
          title: 'Marketing brief',
          status: 'completed',
          unread_message_count: 0,
          latest_message: 'Done',
          latest_message_at: 1710000000,
          is_shared: false,
          source: 'telegram',
        },
      ],
    })

    const wrapper = mountAgentsPage()
    await flushPromises()

    const searchInput = wrapper.find('input[type="search"]')
    const statusSelect = wrapper.find('select')

    expect(searchInput.exists()).toBe(true)
    expect(statusSelect.exists()).toBe(true)

    await searchInput.setValue('Python')
    await flushPromises()

    expect(wrapper.text()).toContain('Python onboarding')
    expect(wrapper.text()).not.toContain('Marketing brief')

    await searchInput.setValue('')
    await statusSelect.setValue('completed')
    await flushPromises()

    expect(wrapper.text()).toContain('Marketing brief')
    expect(wrapper.text()).not.toContain('Python onboarding')
  })
})
