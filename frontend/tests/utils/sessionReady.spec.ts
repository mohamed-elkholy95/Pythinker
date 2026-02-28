import { describe, it, expect, vi, afterEach } from 'vitest'
import { SessionStatus } from '@/types/response'
import { waitForSessionReady } from '@/utils/sessionReady'

describe('waitForSessionReady', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('returns immediately when session is ready', async () => {
    const getSessionFn = vi.fn().mockResolvedValue({ status: SessionStatus.PENDING })

    const result = await waitForSessionReady('session-1', getSessionFn, { pollIntervalMs: 10, maxWaitMs: 1000 })

    expect(result.status).toBe(SessionStatus.PENDING)
    expect(result.timedOut).toBe(false)
    expect(getSessionFn).toHaveBeenCalledTimes(1)
  })

  it('polls until session is no longer initializing', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)

    const getSessionFn = vi
      .fn()
      .mockResolvedValueOnce({ status: SessionStatus.INITIALIZING })
      .mockResolvedValueOnce({ status: SessionStatus.INITIALIZING })
      .mockResolvedValueOnce({ status: SessionStatus.PENDING })

    const promise = waitForSessionReady('session-1', getSessionFn, {
      pollIntervalMs: 50,
      maxWaitMs: 1000,
      initialDelayMs: 0,
    })

    await vi.advanceTimersByTimeAsync(100)
    const result = await promise

    expect(result.status).toBe(SessionStatus.PENDING)
    expect(result.timedOut).toBe(false)
    expect(getSessionFn).toHaveBeenCalledTimes(3)
  })

  it('returns timedOut when still initializing after max wait', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)

    const getSessionFn = vi
      .fn()
      .mockResolvedValue({ status: SessionStatus.INITIALIZING })

    const promise = waitForSessionReady('session-1', getSessionFn, {
      pollIntervalMs: 50,
      maxWaitMs: 120,
      initialDelayMs: 0,
    })

    await vi.advanceTimersByTimeAsync(200)
    const result = await promise

    expect(result.status).toBe(SessionStatus.INITIALIZING)
    expect(result.timedOut).toBe(true)
    expect(getSessionFn).toHaveBeenCalledTimes(3)
  })
})
