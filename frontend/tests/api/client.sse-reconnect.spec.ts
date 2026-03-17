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

describe('createSSEConnection reconnect behavior', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    const { getSseCircuitBreaker } = await import('../../src/composables/useCircuitBreaker')
    getSseCircuitBreaker().reset()
  })

  afterEach(async () => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    const { getSseCircuitBreaker } = await import('../../src/composables/useCircuitBreaker')
    getSseCircuitBreaker().reset()
  })

  it('emits gap callback and resumes from checkpoint event id on next retry', async () => {
    let callCount = 0
    let secondHeaders: Record<string, string> | undefined

    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      callCount += 1
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onmessage = handlers.onmessage as (event: { event: string; data: string }) => void
      const onclose = handlers.onclose as () => void

      if (callCount === 1) {
        void onopen(okResponse())
        onmessage({
          event: 'error',
          data: JSON.stringify({
            event_id: 'evt-gap-1',
            error_code: 'stream_gap_detected',
            recoverable: true,
            retry_after_ms: 100,
            checkpoint_event_id: 'evt-checkpoint-42',
            details: {
              requested_event_id: 'evt-old-10',
              first_available_event_id: 'evt-new-11',
            },
          }),
        })
        onclose()
        return Promise.resolve()
      }

      secondHeaders = handlers.headers as Record<string, string>
      void onopen(okResponse())
      onmessage({
        event: 'done',
        data: JSON.stringify({ event_id: 'evt-done-2' }),
      })
      onclose()
      return Promise.resolve()
    })

    const { createSSEConnection } = await import('../../src/api/client')
    const onGapDetected = vi.fn()

    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello world' },
      },
      {
        onGapDetected,
      }
    )

    await vi.advanceTimersByTimeAsync(250)

    expect(onGapDetected).toHaveBeenCalledWith({
      requestedEventId: 'evt-old-10',
      firstAvailableEventId: 'evt-new-11',
      checkpointEventId: 'evt-checkpoint-42',
    })
    expect(secondHeaders?.['Last-Event-ID']).toBe('evt-checkpoint-42')

    cancel()
  })

  it('defers retry while circuit is open and reconnects after reset window', async () => {
    const { createSSEConnection } = await import('../../src/api/client')
    const { getSseCircuitBreaker } = await import('../../src/composables/useCircuitBreaker')
    const circuit = getSseCircuitBreaker()
    circuit.forceOpen()

    mockFetchEventSource.mockImplementation((_url: string, handlers: Record<string, unknown>) => {
      const onopen = handlers.onopen as (response: Response) => Promise<void>
      const onmessage = handlers.onmessage as (event: { event: string; data: string }) => void
      const onclose = handlers.onclose as () => void
      void onopen(okResponse())
      onmessage({
        event: 'done',
        data: JSON.stringify({ event_id: 'evt-done-3' }),
      })
      onclose()
      return Promise.resolve()
    })

    const onError = vi.fn()
    const cancel = await createSSEConnection(
      '/sessions/test/chat',
      {
        method: 'POST',
        body: { message: 'hello' },
      },
      {
        onError,
      }
    )

    expect(mockFetchEventSource).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(31000)
    expect(mockFetchEventSource).toHaveBeenCalledTimes(1)

    cancel()
  })
})
