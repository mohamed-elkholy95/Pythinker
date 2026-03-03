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

  it('renders the Telegram onboarding design when user is not linked', async () => {
    getLinkedChannelsMock.mockResolvedValue([])
    getSessionsMock.mockResolvedValue({ sessions: [] })

    const wrapper = mountAgentsPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Deploy your agent for web apps')
    expect(wrapper.text()).toContain('Get started on Telegram')
    expect(wrapper.text()).toContain('Works in your messenger')
  })

  it('navigates to normal chat view when Telegram is linked', async () => {
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
        },
      ],
    })

    mountAgentsPage()
    await flushPromises()

    expect(pushMock).toHaveBeenCalledWith('/chat/session-1')
  })
})
