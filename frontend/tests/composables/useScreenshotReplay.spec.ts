import { ref } from 'vue'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()

vi.mock('../../src/api/client', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}))

describe('useScreenshotReplay', () => {
  beforeEach(() => {
    mockGet.mockReset()
    vi.resetModules()
  })

  it('loads completed-session replay from the first frame when requested', async () => {
    mockGet.mockResolvedValue({
      data: {
        data: {
          screenshots: [
            {
              id: 'shot-1',
              session_id: 'session-1',
              sequence_number: 0,
              timestamp: 100,
              trigger: 'session_start',
              size_bytes: 10,
              has_thumbnail: false,
            },
            {
              id: 'shot-2',
              session_id: 'session-1',
              sequence_number: 1,
              timestamp: 200,
              trigger: 'periodic',
              size_bytes: 20,
              has_thumbnail: false,
            },
          ],
          total: 2,
        },
      },
    })

    const { useScreenshotReplay } = await import('../../src/composables/useScreenshotReplay')
    const replay = useScreenshotReplay(ref('session-1'))

    await replay.loadScreenshots({ startAt: 'first' })

    expect(replay.currentIndex.value).toBe(0)
  })

  it('defaults to the last frame when no explicit replay start is provided', async () => {
    mockGet.mockResolvedValue({
      data: {
        data: {
          screenshots: [
            {
              id: 'shot-1',
              session_id: 'session-1',
              sequence_number: 0,
              timestamp: 100,
              trigger: 'session_start',
              size_bytes: 10,
              has_thumbnail: false,
            },
            {
              id: 'shot-2',
              session_id: 'session-1',
              sequence_number: 1,
              timestamp: 200,
              trigger: 'periodic',
              size_bytes: 20,
              has_thumbnail: false,
            },
          ],
          total: 2,
        },
      },
    })

    const { useScreenshotReplay } = await import('../../src/composables/useScreenshotReplay')
    const replay = useScreenshotReplay(ref('session-1'))

    await replay.loadScreenshots()

    expect(replay.currentIndex.value).toBe(1)
  })

  it('clears the replay cursor when a refreshed session has no screenshots', async () => {
    mockGet
      .mockResolvedValueOnce({
        data: {
          data: {
            screenshots: [
              {
                id: 'shot-1',
                session_id: 'session-1',
                sequence_number: 0,
                timestamp: 100,
                trigger: 'session_start',
                size_bytes: 10,
                has_thumbnail: false,
              },
              {
                id: 'shot-2',
                session_id: 'session-1',
                sequence_number: 1,
                timestamp: 200,
                trigger: 'periodic',
                size_bytes: 20,
                has_thumbnail: false,
              },
            ],
            total: 2,
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          data: {
            screenshots: [],
            total: 0,
          },
        },
      })

    const { useScreenshotReplay } = await import('../../src/composables/useScreenshotReplay')
    const replay = useScreenshotReplay(ref('session-1'))

    await replay.loadScreenshots()
    expect(replay.currentIndex.value).toBe(1)

    await replay.loadScreenshots({ startAt: 'preserve' })

    expect(replay.screenshots.value).toEqual([])
    expect(replay.currentIndex.value).toBe(-1)
  })

  it('ignores stale screenshot list responses when multiple loads overlap', async () => {
    let resolveFirst: ((value: unknown) => void) | undefined
    let resolveSecond: ((value: unknown) => void) | undefined

    mockGet
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveFirst = resolve
      }))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveSecond = resolve
      }))

    const { useScreenshotReplay } = await import('../../src/composables/useScreenshotReplay')
    const replay = useScreenshotReplay(ref('session-1'))

    const firstLoad = replay.loadScreenshots({ startAt: 'first' })
    const secondLoad = replay.loadScreenshots()

    resolveSecond?.({
      data: {
        data: {
          screenshots: [
            {
              id: 'shot-new-1',
              session_id: 'session-1',
              sequence_number: 0,
              timestamp: 100,
              trigger: 'session_start',
              size_bytes: 10,
              has_thumbnail: false,
            },
            {
              id: 'shot-new-2',
              session_id: 'session-1',
              sequence_number: 1,
              timestamp: 200,
              trigger: 'periodic',
              size_bytes: 20,
              has_thumbnail: false,
            },
            {
              id: 'shot-new-3',
              session_id: 'session-1',
              sequence_number: 2,
              timestamp: 300,
              trigger: 'periodic',
              size_bytes: 30,
              has_thumbnail: false,
            },
          ],
          total: 3,
        },
      },
    })

    resolveFirst?.({
      data: {
        data: {
          screenshots: [
            {
              id: 'shot-old-1',
              session_id: 'session-1',
              sequence_number: 0,
              timestamp: 50,
              trigger: 'session_start',
              size_bytes: 10,
              has_thumbnail: false,
            },
          ],
          total: 1,
        },
      },
    })

    await Promise.all([firstLoad, secondLoad])

    expect(replay.screenshots.value.map((s) => s.id)).toEqual([
      'shot-new-1',
      'shot-new-2',
      'shot-new-3',
    ])
    expect(replay.currentIndex.value).toBe(2)
  })

  it('uses shared screenshot endpoints when requested', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/sessions/shared/session-1/screenshots') {
        return Promise.resolve({
          data: {
            data: {
              screenshots: [
                {
                  id: 'shot-1',
                  session_id: 'session-1',
                  sequence_number: 0,
                  timestamp: 100,
                  trigger: 'session_start',
                  size_bytes: 10,
                  has_thumbnail: false,
                },
              ],
              total: 1,
            },
          },
        })
      }

      if (url === '/sessions/shared/session-1/screenshots/shot-1') {
        return Promise.resolve({
          data: new Blob(['frame']),
        })
      }

      throw new Error(`Unexpected URL: ${url}`)
    })

    const { useScreenshotReplay } = await import('../../src/composables/useScreenshotReplay')
    const replay = useScreenshotReplay(ref('session-1'), { isShared: true })

    await replay.loadScreenshots({ startAt: 'first' })

    expect(mockGet).toHaveBeenCalledWith('/sessions/shared/session-1/screenshots')
  })
})
