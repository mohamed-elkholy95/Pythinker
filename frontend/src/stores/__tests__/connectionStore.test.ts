import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  SSE_HEARTBEAT_LIVENESS_MS,
  SSE_STALE_TIMEOUT_MS,
} from '@/core/session/workflowTimingContract'
import { useConnectionStore } from '@/stores/connectionStore'

describe('connectionStore timing defaults', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-28T12:00:00.000Z'))
    setActivePinia(createPinia())
  })

  it('uses the shared heartbeat liveness threshold', () => {
    const connectionStore = useConnectionStore()

    connectionStore.lastHeartbeatTime = Date.now() - SSE_HEARTBEAT_LIVENESS_MS + 1
    expect(connectionStore.isReceivingHeartbeats).toBe(true)

    connectionStore.lastHeartbeatTime = Date.now() - SSE_HEARTBEAT_LIVENESS_MS
    expect(connectionStore.isReceivingHeartbeats).toBe(false)
  })

  it('uses the shared stale timeout threshold', () => {
    const connectionStore = useConnectionStore()

    connectionStore.transitionTo('streaming')
    connectionStore.lastRealEventTime = Date.now() - SSE_STALE_TIMEOUT_MS - 1
    connectionStore.lastHeartbeatTime = Date.now() - SSE_STALE_TIMEOUT_MS - 1

    connectionStore.checkStaleConnection()
    expect(connectionStore.isStale).toBe(true)

    connectionStore.lastHeartbeatTime = Date.now() - SSE_HEARTBEAT_LIVENESS_MS + 1
    connectionStore.checkStaleConnection()
    expect(connectionStore.isStale).toBe(false)
  })
})
