import { computed, ref } from 'vue'
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const hasAgentDataFlag = ref(false)

const state = {
  agentBreakdown: ref([]),
  agentRuns: ref([]),
  agentSummary: ref(null),
  agentTimeseries: ref([]),
  hasAgentData: computed(() => hasAgentDataFlag.value),
  legacyDailyUsage: ref([]),
  legacySummary: ref(null),
  loadBreakdown: vi.fn(async () => {}),
  loadOverview: vi.fn(async () => {}),
  loadingBreakdown: ref(false),
  loadingOverview: ref(false),
}

vi.mock('@/composables/useAgentUsage', () => ({
  useAgentUsage: () => state,
}))

vi.mock('@/components/settings/UsageChart.vue', () => ({
  default: {
    name: 'UsageChart',
    props: ['data', 'metric', 'legendLabel'],
    template: '<div class="usage-chart-stub">{{ metric }} {{ legendLabel }}</div>',
  },
}))

import UsageSettings from '@/components/settings/UsageSettings.vue'

describe('UsageSettings', () => {
  beforeEach(() => {
    state.agentBreakdown.value = []
    state.agentRuns.value = []
    state.agentSummary.value = null
    state.agentTimeseries.value = []
    state.legacyDailyUsage.value = []
    state.legacySummary.value = null
    hasAgentDataFlag.value = false
    state.loadingBreakdown.value = false
    state.loadingOverview.value = false
    state.loadBreakdown.mockClear()
    state.loadOverview.mockClear()
  })

  it('renders agent usage views when run-level data exists', async () => {
    state.agentSummary.value = {
      run_count: 4,
      completed_run_count: 3,
      failed_run_count: 1,
      success_rate: 0.75,
      avg_run_duration_ms: 4200,
      total_cost: 1.25,
      total_input_tokens: 1400,
      total_cached_input_tokens: 200,
      total_output_tokens: 600,
      total_reasoning_tokens: 120,
      total_tool_calls: 8,
      total_mcp_calls: 3,
      cache_savings_estimate: 0.04,
    }
    state.agentRuns.value = [
      {
        run_id: 'run-1',
        session_id: 'session-1',
        started_at: '2026-03-17T12:00:00Z',
        completed_at: '2026-03-17T12:00:04Z',
        status: 'completed',
        duration_ms: 4000,
        total_cost: 0.32,
        total_tokens: 420,
        tool_call_count: 2,
        mcp_call_count: 1,
        primary_model: 'gpt-4o-mini',
        primary_provider: 'openai',
      },
    ]
    state.agentBreakdown.value = [
      {
        key: 'gpt-4o-mini',
        run_count: 4,
        input_tokens: 1400,
        cached_input_tokens: 200,
        output_tokens: 600,
        reasoning_tokens: 120,
        cost: 1.25,
        avg_duration_ms: 4200,
        error_rate: 0.25,
      },
    ]
    state.agentTimeseries.value = [
      {
        date: '2026-03-17T00:00:00Z',
        run_count: 4,
        success_count: 3,
        failed_count: 1,
        cost: 1.25,
        input_tokens: 1400,
        cached_input_tokens: 200,
        output_tokens: 600,
        reasoning_tokens: 120,
        tool_calls: 8,
        mcp_calls: 3,
      },
    ]
    hasAgentDataFlag.value = true

    const wrapper = mount(UsageSettings)

    expect(wrapper.text()).toContain('Agent Runs')
    expect(wrapper.text()).toContain('Recent Runs')
    expect(wrapper.text()).toContain('gpt-4o-mini')
    expect(wrapper.text()).toContain('Breakdown')
    expect(wrapper.text()).toContain('Efficiency')
  })

  it('shows legacy fallback when run-level data is unavailable', async () => {
    state.legacySummary.value = {
      today: {
        tokens: 1200,
        cost: 0.18,
        llm_calls: 6,
        tool_calls: 2,
      },
      month: {
        tokens: 32000,
        cost: 4.6,
        llm_calls: 120,
        tool_calls: 35,
        sessions: 14,
        active_days: 9,
      },
    }
    state.legacyDailyUsage.value = [
      {
        date: '2026-03-17',
        total_prompt_tokens: 800,
        total_completion_tokens: 400,
        total_cached_tokens: 100,
        total_cost: 0.18,
        llm_call_count: 6,
        tool_call_count: 2,
        tokens_by_model: {},
        cost_by_model: {},
      },
    ]
    hasAgentDataFlag.value = false

    const wrapper = mount(UsageSettings)

    expect(wrapper.text()).toContain('Run-level telemetry is not available')
    expect(wrapper.text()).toContain('Recent Activity')
    expect(wrapper.text()).toContain('$4.60')
  })
})
