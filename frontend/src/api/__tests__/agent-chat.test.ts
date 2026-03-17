import { afterEach, describe, expect, it, vi } from 'vitest'

const { createSSEConnectionMock } = vi.hoisted(() => ({
  createSSEConnectionMock: vi.fn((..._args: unknown[]) => Promise.resolve(() => {})),
}))

vi.mock('../client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  API_CONFIG: {
    host: 'http://localhost:8000',
  },
  createSSEConnection: createSSEConnectionMock,
  createEventSourceConnection: vi.fn(async () => () => {}),
}))

import { chatWithSession } from '../agent'

describe('chatWithSession event_id behavior', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('omits event_id for fresh user messages', async () => {
    await chatWithSession('session-1', 'how are you?', 'evt-123')

    expect(createSSEConnectionMock).toHaveBeenCalledTimes(1)
    const callArgs = createSSEConnectionMock.mock.calls[0] as unknown[]
    const options = (callArgs[1] ?? {}) as { body?: Record<string, unknown> }
    const body = options.body as Record<string, unknown>

    expect(body.message).toBe('how are you?')
    expect(body.event_id).toBeUndefined()
  })

  it('includes event_id for resume-only calls', async () => {
    await chatWithSession('session-1', '', 'evt-456')

    expect(createSSEConnectionMock).toHaveBeenCalledTimes(1)
    const callArgs = createSSEConnectionMock.mock.calls[0] as unknown[]
    const options = (callArgs[1] ?? {}) as { body?: Record<string, unknown> }
    const body = options.body as Record<string, unknown>

    expect(body.message).toBe('')
    expect(body.event_id).toBe('evt-456')
  })
})
