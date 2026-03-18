import { computed, onUnmounted, ref } from 'vue'

import {
  getAgentUsageBreakdown,
  getAgentUsageRuns,
  getAgentUsageSummary,
  getAgentUsageTimeseries,
  getDailyUsage,
  getUsageSummary,
  type AgentUsageBreakdownGroup,
  type AgentUsageBreakdownRow,
  type AgentUsageRange,
  type AgentUsageRun,
  type AgentUsageSummary,
  type AgentUsageTimeseriesPoint,
  type DailyUsage,
  type UsageSummary,
} from '@/api/usage'

const RANGE_TO_DAYS: Record<AgentUsageRange, number> = {
  '7d': 7,
  '30d': 30,
  '90d': 90,
}

export function useAgentUsage() {
  const loadingOverview = ref(false)
  const loadingBreakdown = ref(false)
  const overviewError = ref<Error | null>(null)
  const breakdownError = ref<Error | null>(null)

  const legacySummary = ref<UsageSummary | null>(null)
  const legacyDailyUsage = ref<DailyUsage[]>([])
  const agentSummary = ref<AgentUsageSummary | null>(null)
  const agentRuns = ref<AgentUsageRun[]>([])
  const agentBreakdown = ref<AgentUsageBreakdownRow[]>([])
  const agentTimeseries = ref<AgentUsageTimeseriesPoint[]>([])
  let disposed = false
  let overviewController: AbortController | null = null
  let breakdownController: AbortController | null = null

  const hasAgentData = computed(() => (agentSummary.value?.run_count ?? 0) > 0)

  async function loadOverview(range: AgentUsageRange) {
    overviewController?.abort()
    overviewController = typeof AbortController !== 'undefined' ? new AbortController() : null
    loadingOverview.value = true
    overviewError.value = null
    const days = RANGE_TO_DAYS[range]
    const requestSignal = overviewController?.signal

    const [legacySummaryResult, legacyDailyResult, agentSummaryResult, agentRunsResult, agentTimeseriesResult] =
      await Promise.allSettled([
        getUsageSummary({ signal: requestSignal }),
        getDailyUsage(days, { signal: requestSignal }),
        getAgentUsageSummary(range, { signal: requestSignal }),
        getAgentUsageRuns(range, 7, { signal: requestSignal }),
        getAgentUsageTimeseries(range, 'day', { signal: requestSignal }),
      ])

    if (disposed || requestSignal?.aborted) {
      return
    }

    const rejectedResult = [
      legacySummaryResult,
      legacyDailyResult,
      agentSummaryResult,
      agentRunsResult,
      agentTimeseriesResult,
    ].find(
      (result): result is PromiseRejectedResult => result.status === 'rejected' && !isAbortError(result.reason)
    )

    overviewError.value = rejectedResult ? toError(rejectedResult.reason) : null
    legacySummary.value = legacySummaryResult.status === 'fulfilled' ? legacySummaryResult.value : null
    legacyDailyUsage.value =
      legacyDailyResult.status === 'fulfilled' ? legacyDailyResult.value.days : []
    agentSummary.value = agentSummaryResult.status === 'fulfilled' ? agentSummaryResult.value : null
    agentRuns.value = agentRunsResult.status === 'fulfilled' ? agentRunsResult.value.runs : []
    agentTimeseries.value = agentTimeseriesResult.status === 'fulfilled' ? agentTimeseriesResult.value.points : []
    loadingOverview.value = false
  }

  async function loadBreakdown(range: AgentUsageRange, groupBy: AgentUsageBreakdownGroup) {
    breakdownController?.abort()
    breakdownController = typeof AbortController !== 'undefined' ? new AbortController() : null
    loadingBreakdown.value = true
    breakdownError.value = null
    try {
      const result = await getAgentUsageBreakdown(range, groupBy, { signal: breakdownController?.signal })
      if (disposed || breakdownController?.signal.aborted) {
        return
      }
      agentBreakdown.value = result.rows
    } catch (error) {
      if (isAbortError(error)) {
        return
      }
      agentBreakdown.value = []
      breakdownError.value = toError(error)
    } finally {
      if (!disposed) {
        loadingBreakdown.value = false
      }
    }
  }

  onUnmounted(() => {
    disposed = true
    overviewController?.abort()
    breakdownController?.abort()
    loadingOverview.value = false
    loadingBreakdown.value = false
  })

  function isAbortError(error: unknown): boolean {
    return (
      error instanceof DOMException && error.name === 'AbortError'
    ) || (
      typeof error === 'object' &&
      error !== null &&
      'code' in error &&
      error.code === 'ERR_CANCELED'
    )
  }

  function toError(error: unknown): Error {
    return error instanceof Error ? error : new Error(String(error))
  }

  return {
    agentBreakdown,
    agentRuns,
    agentSummary,
    agentTimeseries,
    breakdownError,
    hasAgentData,
    legacyDailyUsage,
    legacySummary,
    loadBreakdown,
    loadOverview,
    loadingBreakdown,
    loadingOverview,
    overviewError,
  }
}
