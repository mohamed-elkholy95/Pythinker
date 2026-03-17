import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { isEventSourceResumeEnabled } from '../sseTransport'

const STORAGE_KEY = 'pythinker:sse-eventsource-resume'

const createStorageMock = (): Storage => {
  const store = new Map<string, string>()
  return {
    get length() {
      return store.size
    },
    clear: () => {
      store.clear()
    },
    key: (index: number) => {
      return Array.from(store.keys())[index] ?? null
    },
    getItem: (key: string) => {
      return store.get(key) ?? null
    },
    setItem: (key: string, value: string) => {
      store.set(key, value)
    },
    removeItem: (key: string) => {
      store.delete(key)
    },
  }
}

describe('isEventSourceResumeEnabled', () => {
  let storage: Storage

  beforeEach(() => {
    storage = createStorageMock()
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: storage,
    })
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: storage,
    })
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    storage.removeItem(STORAGE_KEY)
  })

  it('defaults to enabled when env flag is unset', () => {
    vi.unstubAllEnvs()
    expect(isEventSourceResumeEnabled()).toBe(true)
  })

  it('respects env disable flag', () => {
    vi.stubEnv('VITE_ENABLE_EVENTSOURCE_RESUME', 'false')
    expect(isEventSourceResumeEnabled()).toBe(false)
  })

  it('allows localStorage override to enable', () => {
    vi.stubEnv('VITE_ENABLE_EVENTSOURCE_RESUME', 'false')
    storage.setItem(STORAGE_KEY, 'true')
    expect(isEventSourceResumeEnabled()).toBe(true)
  })

  it('allows localStorage override to disable', () => {
    vi.stubEnv('VITE_ENABLE_EVENTSOURCE_RESUME', 'true')
    storage.setItem(STORAGE_KEY, 'false')
    expect(isEventSourceResumeEnabled()).toBe(false)
  })
})
