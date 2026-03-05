import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

import { SessionStatus } from '@/types/response'

const { routeMock, pushMock } = vi.hoisted(() => ({
  routeMock: {
    params: { sessionId: 'current-session' },
    matched: [] as Array<{ meta?: Record<string, unknown> }>,
  },
  pushMock: vi.fn(),
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

import SessionItem from '../SessionItem.vue'

const baseSession = {
  session_id: 'session-1',
  title: 'Telegram research',
  latest_message: 'latest message',
  latest_message_at: 1710000000,
  status: SessionStatus.COMPLETED,
  unread_message_count: 0,
  is_shared: false,
  source: 'telegram',
}

describe('SessionItem', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.params = { sessionId: 'other-session' }
    routeMock.matched = []
  })

  it('renders Telegram source badge for Telegram sessions', () => {
    const wrapper = mount(SessionItem, {
      props: { session: baseSession },
      global: {
        stubs: {
          TaskIcon: true,
        },
      },
    })

    expect(wrapper.find('[data-testid="session-source-telegram"]').exists()).toBe(true)
  })

  it('routes Telegram sessions to agents session route inside Agents workspace', async () => {
    routeMock.matched = [{ meta: { workspace: 'agents' } }]

    const wrapper = mount(SessionItem, {
      props: { session: baseSession },
      global: {
        stubs: {
          TaskIcon: true,
        },
      },
    })

    await wrapper.find('[role="button"]').trigger('click')

    expect(pushMock).toHaveBeenCalledWith({
      name: 'agents-session',
      params: { sessionId: 'session-1' },
    })
  })

  it('routes non-Telegram sessions to regular chat route', async () => {
    routeMock.matched = [{ meta: { workspace: 'agents' } }]

    const wrapper = mount(SessionItem, {
      props: {
        session: {
          ...baseSession,
          session_id: 'session-2',
          source: 'web',
        },
      },
      global: {
        stubs: {
          TaskIcon: true,
        },
      },
    })

    await wrapper.find('[role="button"]').trigger('click')

    expect(pushMock).toHaveBeenCalledWith('/chat/session-2')
  })
})

