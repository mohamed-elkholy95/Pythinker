import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockFetchEventSource = vi.fn()

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: (...args: unknown[]) => mockFetchEventSource(...args),
}))

vi.mock('../../src/main', () => ({
  router: {
    currentRoute: {
      value: {
        path: '/chat',
      },
    },
  },
}))

vi.mock('../../src/api/auth', () => ({
  clearStoredTokens: vi.fn(),
  getStoredToken: vi.fn(() => 'test-token'),
  getStoredRefreshToken: vi.fn(() => 'test-refresh-token'),
  storeToken: vi.fn(),
}))

const okResponse = (): Response =>
  ({
    status: 200,
    ok: true,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'text/event-stream' }),
  } as Response)

describe('createSSEConnection close behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('reports transient close as retrying', async () => {
    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onmessage = handlers.onmessage as (event: { event: string; data: string }) => void
      const onclose = handlers.onclose as () => void
      void onopen(okResponse())
      onmessage({
        event: 'progress',
        data: JSON.stringify({ event_id: 'evt_progress', phase: 'planning' }),
      })
      onclose()
      return Promise.resolve()
    })

    const { createSSEConnection } = await import('../../src/api/client')
    const onClose = vi.fn()
    const onRetry = vi.fn()

    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello' },
      },
      {
        onClose,
        onRetry,
      }
    )

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onClose.mock.calls[0]?.[0]).toMatchObject({
      willRetry: true,
      reason: 'retrying',
      retryAttempt: 1,
    })
    expect(onRetry).toHaveBeenCalledWith(1, 7)

    cancel()
  })

  it('schedules a single retry on transport error without double enqueue', async () => {
    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onerror = handlers.onerror as (error: unknown) => void
      void onopen(okResponse())

      try {
        onerror(new Error('network interrupted'))
      } catch (error) {
        return Promise.reject(error)
      }
      return Promise.resolve()
    })

    const { createSSEConnection } = await import('../../src/api/client')
    const onRetry = vi.fn()
    const onError = vi.fn()

    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello' },
      },
      {
        onRetry,
        onError,
      }
    )

    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(onRetry).toHaveBeenCalledWith(1, 7)
    expect(onError).not.toHaveBeenCalled()

    cancel()
  })

  it('reports done-then-close as completed without retry', async () => {
    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onmessage = handlers.onmessage as (event: { event: string; data: string }) => void
      const onclose = handlers.onclose as () => void
      void onopen(okResponse())
      onmessage({
        event: 'done',
        data: JSON.stringify({ event_id: 'evt_done' }),
      })
      onclose()
      return Promise.resolve()
    })

    const { createSSEConnection } = await import('../../src/api/client')
    const onClose = vi.fn()
    const onRetry = vi.fn()

    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello' },
      },
      {
        onClose,
        onRetry,
      }
    )

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onClose.mock.calls[0]?.[0]).toMatchObject({
      willRetry: false,
      reason: 'completed',
      streamCompleted: true,
    })
    expect(onRetry).not.toHaveBeenCalled()

    cancel()
  })

  it('does not retry when stream closes without events after message send', async () => {
    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onclose = handlers.onclose as () => void
      void onopen(okResponse())
      onclose()
      return Promise.resolve()
    })

    const { createSSEConnection } = await import('../../src/api/client')
    const onClose = vi.fn()
    const onRetry = vi.fn()

    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello' },
      },
      {
        onClose,
        onRetry,
      }
    )

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onClose.mock.calls[0]?.[0]).toMatchObject({
      willRetry: false,
      reason: 'no_events_after_message',
      messageSent: true,
      receivedAnyEvents: false,
    })
    expect(onRetry).not.toHaveBeenCalled()

    cancel()
  })

  it('applies server-provided retry policy headers', async () => {
    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onmessage = handlers.onmessage as (event: { event: string; data: string }) => void
      const onclose = handlers.onclose as () => void
      void onopen({
        ...okResponse(),
        headers: new Headers({
          'content-type': 'text/event-stream',
          'X-Pythinker-SSE-Retry-Max-Attempts': '2',
          'X-Pythinker-SSE-Retry-Base-Delay-Ms': '300',
          'X-Pythinker-SSE-Retry-Max-Delay-Ms': '900',
          'X-Pythinker-SSE-Retry-Jitter-Ratio': '0.1',
        }),
      } as Response)
      onmessage({
        event: 'progress',
        data: JSON.stringify({ event_id: 'evt_progress_retry_header', phase: 'planning' }),
      })
      onclose()
      return Promise.resolve()
    })

    const { createSSEConnection } = await import('../../src/api/client')
    const onClose = vi.fn()
    const onRetry = vi.fn()

    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello' },
      },
      {
        onClose,
        onRetry,
      }
    )

    expect(onRetry).toHaveBeenCalledWith(1, 2)
    expect(onClose.mock.calls[0]?.[0]).toMatchObject({
      maxRetries: 2,
      willRetry: true,
      reason: 'retrying',
    })

    cancel()
  })

  it('keeps stream retryable for recoverable error events', async () => {
    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onmessage = handlers.onmessage as (event: { event: string; data: string }) => void
      const onclose = handlers.onclose as () => void
      void onopen(okResponse())
      onmessage({
        event: 'error',
        data: JSON.stringify({
          event_id: 'evt-err-1',
          error: 'Stream timed out',
          error_type: 'timeout',
          recoverable: true,
          retry_after_ms: 1200,
        }),
      })
      onclose()
      return Promise.resolve()
    })

    const { createSSEConnection } = await import('../../src/api/client')
    const onClose = vi.fn()
    const onRetry = vi.fn()

    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello' },
      },
      {
        onClose,
        onRetry,
      }
    )

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onClose.mock.calls[0]?.[0]).toMatchObject({
      willRetry: true,
      reason: 'retrying',
      streamCompleted: false,
      retryDelayMs: 1200,
    })
    expect(onRetry).toHaveBeenCalledWith(1, 7)

    cancel()
  })
})
