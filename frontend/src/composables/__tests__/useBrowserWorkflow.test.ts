import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { createSSEConnectionMock, cancelMock } = vi.hoisted(() => ({
  createSSEConnectionMock: vi.fn(),
  cancelMock: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  createSSEConnection: createSSEConnectionMock,
}))

import { useConnectionStore } from '@/stores/connectionStore'
import { useBrowserWorkflow } from '../useBrowserWorkflow'

describe('useBrowserWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    createSSEConnectionMock.mockResolvedValue(cancelMock)
  })

  it('connects to the browser workflow stream and records progress events', async () => {
    const workflow = useBrowserWorkflow()
    const connectionStore = useConnectionStore()

    const result = await workflow.fetchStream('https://example.com/article', 'stealth')

    expect(createSSEConnectionMock).toHaveBeenCalledTimes(1)
    expect(result).toBeUndefined()
    const [endpoint, options, callbacks] = createSSEConnectionMock.mock.calls[0] as [
      string,
      { method?: string },
      {
        onOpen?: () => void
        onMessage?: (event: { event: string; data: Record<string, unknown> }) => void
      },
    ]

    expect(endpoint).toBe(
      '/browser-workflow/fetch/stream?url=https%3A%2F%2Fexample.com%2Farticle&mode=stealth',
    )
    expect(options).toEqual({ method: 'GET' })

    callbacks.onOpen?.()
    callbacks.onMessage?.({
      event: 'progress',
      data: {
        event_id: '100-0',
        phase: 'fetching',
        url: 'https://example.com/article',
        mode: 'stealth',
      },
    })
    callbacks.onMessage?.({
      event: 'progress',
      data: {
        event_id: '101-0',
        phase: 'completed',
        url: 'https://example.com/article',
        mode: 'stealth',
        tier_used: 'cache',
        from_cache: true,
      },
    })

    expect(workflow.events.value).toHaveLength(2)
    expect(workflow.lastProgress.value?.phase).toBe('completed')
    expect(workflow.lastError.value).toBe(null)
    expect(workflow.isStreaming.value).toBe(false)
    expect(connectionStore.phase).toBe('settled')
    expect(connectionStore.lastEventId).toBe('101-0')
  })

  it('captures transport errors and allows manual stop and clear', async () => {
    const workflow = useBrowserWorkflow()
    const connectionStore = useConnectionStore()

    await workflow.fetchStream('https://example.com', 'http')

    const callbacks = createSSEConnectionMock.mock.calls[0]?.[2] as {
      onError?: (error: Error) => void
    }
    callbacks.onError?.(new Error('network down'))

    expect(workflow.lastError.value).toBe('network down')
    expect(workflow.hasError.value).toBe(true)
    expect(connectionStore.phase).toBe('error')

    workflow.clearEvents()
    expect(workflow.events.value).toEqual([])
    expect(workflow.lastError.value).toBe(null)

    workflow.stopStreaming()
    expect(cancelMock).toHaveBeenCalledTimes(1)
    expect(connectionStore.phase).toBe('stopped')
  })
})
