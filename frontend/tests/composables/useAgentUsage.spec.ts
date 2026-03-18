import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'

import type { AgentUsageRange } from '@/api/usage'

const apiMocks = vi.hoisted(() => ({
  getUsageSummary: vi.fn(),
  getDailyUsage: vi.fn(),
  getAgentUsageSummary: vi.fn(),
  getAgentUsageRuns: vi.fn(),
  getAgentUsageTimeseries: vi.fn(),
  getAgentUsageBreakdown: vi.fn(),
}))

vi.mock('@/api/usage', async () => {
  const actual = await vi.importActual<typeof import('@/api/usage')>('@/api/usage')
  return {
    ...actual,
    getUsageSummary: apiMocks.getUsageSummary,
    getDailyUsage: apiMocks.getDailyUsage,
    getAgentUsageSummary: apiMocks.getAgentUsageSummary,
    getAgentUsageRuns: apiMocks.getAgentUsageRuns,
    getAgentUsageTimeseries: apiMocks.getAgentUsageTimeseries,
    getAgentUsageBreakdown: apiMocks.getAgentUsageBreakdown,
  }
})

import { useAgentUsage } from '@/composables/useAgentUsage'

function mountHarness() {
  let composable: ReturnType<typeof useAgentUsage> | null = null

  const Harness = defineComponent({
    setup() {
      composable = useAgentUsage()
      return () => h('div')
    },
  })

  const wrapper = mount(Harness)
  return {
    wrapper,
    composable: composable!,
  }
}

describe('useAgentUsage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getUsageSummary.mockResolvedValue({
      today: { tokens: 10, cost: 0.01, llm_calls: 1, tool_calls: 0 },
      month: { tokens: 10, cost: 0.01, llm_calls: 1, tool_calls: 0, sessions: 1, active_days: 1 },
    })
    apiMocks.getDailyUsage.mockResolvedValue({ days: [], total_days: 0 })
    apiMocks.getAgentUsageSummary.mockResolvedValue({
      run_count: 0,
      completed_run_count: 0,
      failed_run_count: 0,
      success_rate: 0,
      avg_run_duration_ms: 0,
      total_cost: 0,
      total_input_tokens: 0,
      total_cached_input_tokens: 0,
      total_output_tokens: 0,
      total_reasoning_tokens: 0,
      total_tool_calls: 0,
      total_mcp_calls: 0,
      cache_savings_estimate: 0,
    })
    apiMocks.getAgentUsageRuns.mockResolvedValue({ runs: [], total_runs: 0 })
    apiMocks.getAgentUsageTimeseries.mockResolvedValue({ points: [], total_points: 0 })
    apiMocks.getAgentUsageBreakdown.mockResolvedValue({ rows: [], total_rows: 0 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts idle before the first request begins', () => {
    const { composable, wrapper } = mountHarness()

    expect(composable.loadingOverview.value).toBe(false)
    expect(composable.loadingBreakdown.value).toBe(false)

    wrapper.unmount()
  })

  it('captures overview failures and clears the loading state', async () => {
    const { composable, wrapper } = mountHarness()
    const failure = new Error('summary failed')
    apiMocks.getAgentUsageSummary.mockRejectedValueOnce(failure)

    await composable.loadOverview('30d')

    expect(composable.loadingOverview.value).toBe(false)
    expect(composable.overviewError.value).toBe(failure)
    expect(composable.agentSummary.value).toBeNull()

    wrapper.unmount()
  })

  it('does not update state after unmount aborts an in-flight overview request', async () => {
    let capturedSignal: AbortSignal | undefined
    apiMocks.getUsageSummary.mockImplementationOnce(
      ({ signal }: { signal?: AbortSignal } = {}) =>
        new Promise((resolve, reject) => {
          capturedSignal = signal
          signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
          setTimeout(() => resolve({
            today: { tokens: 99, cost: 0.5, llm_calls: 2, tool_calls: 1 },
            month: { tokens: 99, cost: 0.5, llm_calls: 2, tool_calls: 1, sessions: 1, active_days: 1 },
          }), 50)
        })
    )

    const { composable, wrapper } = mountHarness()
    const promise = composable.loadOverview('30d' satisfies AgentUsageRange)

    wrapper.unmount()
    await promise

    expect(capturedSignal?.aborted).toBe(true)
    expect(composable.legacySummary.value).toBeNull()
    expect(composable.loadingOverview.value).toBe(false)
  })
})
