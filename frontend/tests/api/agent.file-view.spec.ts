import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockPost = vi.fn()

vi.mock('@/api/client', () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  API_CONFIG: { host: 'http://localhost:8000' },
  createEventSourceConnection: vi.fn(),
  createSSEConnection: vi.fn(),
}))

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
}

const makeDeferred = <T>(): Deferred<T> => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('agent viewFile dedupe', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('coalesces concurrent requests for the same session/file', async () => {
    const deferred = makeDeferred<{ data: { data: { content: string; file: string } } }>()
    mockPost.mockReturnValue(deferred.promise)

    const { viewFile } = await import('../../src/api/agent')

    const p1 = viewFile('session-1', '/workspace/demo.md')
    const p2 = viewFile('session-1', '/workspace/demo.md')

    expect(mockPost).toHaveBeenCalledTimes(1)

    deferred.resolve({
      data: { data: { content: 'hello', file: '/workspace/demo.md' } },
    })

    await expect(p1).resolves.toEqual({ content: 'hello', file: '/workspace/demo.md' })
    await expect(p2).resolves.toEqual({ content: 'hello', file: '/workspace/demo.md' })
  })

  it('serves a short-lived cached response for immediate repeats', async () => {
    mockPost.mockResolvedValue({
      data: { data: { content: 'cached', file: '/workspace/demo.md' } },
    })

    const { viewFile } = await import('../../src/api/agent')

    const first = await viewFile('session-2', '/workspace/demo.md')
    const second = await viewFile('session-2', '/workspace/demo.md')

    expect(first).toEqual({ content: 'cached', file: '/workspace/demo.md' })
    expect(second).toEqual({ content: 'cached', file: '/workspace/demo.md' })
    expect(mockPost).toHaveBeenCalledTimes(1)
  })
})
