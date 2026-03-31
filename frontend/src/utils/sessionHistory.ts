import type { AgentSSEEvent } from '@/types/event'
import { SessionStatus } from '@/types/response'

import { stripLeakedToolCallMarkup } from './messageSanitizer'

export interface SessionHistorySource {
  status: SessionStatus
  events: AgentSSEEvent[]
  latest_message?: string | null
  latest_message_at?: number | null
}

export interface SessionHistoryResolution {
  events: AgentSSEEvent[]
  recoveredFromLatestMessage: boolean
}

const TERMINAL_STATUSES = new Set<SessionStatus>([
  SessionStatus.COMPLETED,
  SessionStatus.FAILED,
  SessionStatus.CANCELLED,
])

export function resolveSessionHistory(session: SessionHistorySource): SessionHistoryResolution {
  if (session.events.length > 0) {
    return { events: session.events, recoveredFromLatestMessage: false }
  }

  const latestMessage = stripLeakedToolCallMarkup(session.latest_message)
  if (!TERMINAL_STATUSES.has(session.status) || !latestMessage) {
    return { events: session.events, recoveredFromLatestMessage: false }
  }

  const timestamp = session.latest_message_at ?? Math.floor(Date.now() / 1000)
  return {
    recoveredFromLatestMessage: true,
    events: [
      {
        event: 'message',
        data: {
          event_id: `synthetic-latest-message-${timestamp}`,
          timestamp,
          content: latestMessage,
          role: 'assistant',
          attachments: [],
        },
      },
    ],
  }
}
