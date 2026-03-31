import { describe, expect, it, vi } from 'vitest'

import type { AgentSSEEvent } from '@/types/event'
import { SessionStatus } from '@/types/response'

import { resolveSessionHistory } from '../sessionHistory'

describe('sessionHistory', () => {
  it('returns stored history unchanged when events exist', () => {
    const events: AgentSSEEvent[] = [
      {
        event: 'message',
        data: {
          event_id: 'event-1',
          timestamp: 1710000000,
          content: 'Stored history',
          role: 'assistant',
          attachments: [],
        },
      },
    ]

    const resolution = resolveSessionHistory({
      status: SessionStatus.COMPLETED,
      events,
      latest_message: 'Latest message',
      latest_message_at: 1710000005,
    })

    expect(resolution.recoveredFromLatestMessage).toBe(false)
    expect(resolution.events).toBe(events)
  })

  it('builds a synthetic assistant message for terminal sessions missing history', () => {
    const resolution = resolveSessionHistory({
      status: SessionStatus.COMPLETED,
      events: [],
      latest_message: 'Recovered answer <tool_call>{"name":"shell"}</tool_call>',
      latest_message_at: 1710000005,
    })

    expect(resolution.recoveredFromLatestMessage).toBe(true)
    expect(resolution.events).toHaveLength(1)
    expect(resolution.events[0]).toEqual({
      event: 'message',
      data: {
        event_id: 'synthetic-latest-message-1710000005',
        timestamp: 1710000005,
        content: 'Recovered answer',
        role: 'assistant',
        attachments: [],
      },
    })
  })

  it('does not synthesize history for active sessions', () => {
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(1710000005000)

    const resolution = resolveSessionHistory({
      status: SessionStatus.RUNNING,
      events: [],
      latest_message: 'Still streaming',
      latest_message_at: null,
    })

    expect(resolution.recoveredFromLatestMessage).toBe(false)
    expect(resolution.events).toEqual([])

    nowSpy.mockRestore()
  })
})
