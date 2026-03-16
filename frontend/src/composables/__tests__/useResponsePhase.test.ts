import { describe, it, expect, vi } from 'vitest'

describe('useResponsePhase', () => {
  it('should start in idle phase', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase } = useResponsePhase()
    expect(phase.value).toBe('idle')
  })

  it('should transition from idle to connecting', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo } = useResponsePhase()
    transitionTo('connecting')
    expect(phase.value).toBe('connecting')
  })

  it('should transition from connecting to streaming', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo } = useResponsePhase()
    transitionTo('connecting')
    transitionTo('streaming')
    expect(phase.value).toBe('streaming')
  })

  it('should auto-settle from completing after timeout', async () => {
    vi.useFakeTimers()
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo } = useResponsePhase()

    transitionTo('connecting')
    transitionTo('streaming')
    transitionTo('completing')

    expect(phase.value).toBe('completing')

    // After 300ms, should auto-settle
    vi.advanceTimersByTime(350)
    expect(phase.value).toBe('settled')

    vi.useRealTimers()
  })

  it('should expose isLoading computed', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { isLoading, transitionTo } = useResponsePhase()

    expect(isLoading.value).toBe(false)
    transitionTo('connecting')
    expect(isLoading.value).toBe(true)
    transitionTo('streaming')
    expect(isLoading.value).toBe(true)
  })

  it('should expose isThinking computed', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { isThinking, transitionTo } = useResponsePhase()

    expect(isThinking.value).toBe(false)
    transitionTo('connecting')
    expect(isThinking.value).toBe(true)
    transitionTo('streaming')
    expect(isThinking.value).toBe(false)
  })

  it('should reset to idle', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo, reset } = useResponsePhase()

    transitionTo('connecting')
    transitionTo('streaming')
    reset()
    expect(phase.value).toBe('idle')
  })

  it('should transition to timed_out', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, isTimedOut, transitionTo } = useResponsePhase()

    transitionTo('streaming')
    transitionTo('timed_out')
    expect(phase.value).toBe('timed_out')
    expect(isTimedOut.value).toBe(true)
  })

  it('should transition to stopped', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, isStopped, transitionTo } = useResponsePhase()

    transitionTo('streaming')
    transitionTo('stopped')
    expect(phase.value).toBe('stopped')
    expect(isStopped.value).toBe(true)
  })

  it('should transition to error', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, isError, transitionTo } = useResponsePhase()

    transitionTo('streaming')
    transitionTo('error')
    expect(phase.value).toBe('error')
    expect(isError.value).toBe(true)
  })

  it('should not be loading when timed_out', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { isLoading, transitionTo } = useResponsePhase()

    transitionTo('streaming')
    expect(isLoading.value).toBe(true)
    transitionTo('timed_out')
    expect(isLoading.value).toBe(false)
  })

  it('should not be loading when stopped', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { isLoading, transitionTo } = useResponsePhase()

    transitionTo('streaming')
    expect(isLoading.value).toBe(true)
    transitionTo('stopped')
    expect(isLoading.value).toBe(false)
  })

  it('should not be loading when error', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { isLoading, transitionTo } = useResponsePhase()

    transitionTo('streaming')
    expect(isLoading.value).toBe(true)
    transitionTo('error')
    expect(isLoading.value).toBe(false)
  })
})
