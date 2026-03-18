import { apiClient } from './client'

interface RequestOptions {
  signal?: AbortSignal
}

// Today's usage summary
export interface TodayUsage {
  tokens: number
  cost: number
  llm_calls: number
  tool_calls: number
}

// This month's usage summary
export interface MonthUsage {
  tokens: number
  cost: number
  llm_calls: number
  tool_calls: number
  sessions: number
  active_days: number
}

// Combined usage summary
export interface UsageSummary {
  today: TodayUsage
  month: MonthUsage
}

// Daily usage record
export interface DailyUsage {
  date: string
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cached_tokens: number
  total_cost: number
  llm_call_count: number
  tool_call_count: number
  tokens_by_model: Record<string, number>
  cost_by_model: Record<string, number>
}

// Daily usage list response
export interface DailyUsageList {
  days: DailyUsage[]
  total_days: number
}

// Monthly usage detail
export interface MonthlyUsageDetail {
  year: number
  month: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cached_tokens: number
  total_cost: number
  total_llm_calls: number
  total_tool_calls: number
  total_sessions: number
  active_days: number
  cost_by_model: Record<string, number>
}

// Monthly usage list response
export interface MonthlyUsageList {
  months: MonthlyUsageDetail[]
  total_months: number
}

// Session usage
export interface SessionUsage {
  session_id: string
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cached_tokens: number
  total_cost: number
  llm_call_count: number
  tool_call_count: number
  tokens_by_model: Record<string, number>
  cost_by_model: Record<string, number>
  first_activity: string | null
  last_activity: string | null
}

// Model pricing info
export interface ModelPricing {
  model: string
  prompt_price: number
  completion_price: number
  cached_price: number | null
}

// Pricing list response
export interface PricingList {
  models: ModelPricing[]
}

export type AgentUsageRange = '7d' | '30d' | '90d'
export type AgentUsageBreakdownGroup = 'model' | 'provider' | 'tool' | 'mcp_server'

export interface AgentUsageSummary {
  run_count: number
  completed_run_count: number
  failed_run_count: number
  success_rate: number
  avg_run_duration_ms: number
  total_cost: number
  total_input_tokens: number
  total_cached_input_tokens: number
  total_output_tokens: number
  total_reasoning_tokens: number
  total_tool_calls: number
  total_mcp_calls: number
  cache_savings_estimate: number
}

export interface AgentUsageRun {
  run_id: string
  session_id: string
  started_at: string
  completed_at: string | null
  status: string
  duration_ms: number | null
  total_cost: number
  total_tokens: number
  tool_call_count: number
  mcp_call_count: number
  primary_model: string | null
  primary_provider: string | null
}

export interface AgentUsageRunList {
  runs: AgentUsageRun[]
  total_runs: number
}

export interface AgentUsageBreakdownRow {
  key: string
  run_count: number
  input_tokens: number
  cached_input_tokens: number
  output_tokens: number
  reasoning_tokens: number
  cost: number
  avg_duration_ms: number
  error_rate: number
}

export interface AgentUsageBreakdownList {
  rows: AgentUsageBreakdownRow[]
  total_rows: number
}

export interface AgentUsageTimeseriesPoint {
  date: string
  run_count: number
  success_count: number
  failed_count: number
  cost: number
  input_tokens: number
  cached_input_tokens: number
  output_tokens: number
  reasoning_tokens: number
  tool_calls: number
  mcp_calls: number
}

export interface AgentUsageTimeseries {
  points: AgentUsageTimeseriesPoint[]
  total_points: number
}

/**
 * Get usage summary for today and this month
 */
export async function getUsageSummary(options: RequestOptions = {}): Promise<UsageSummary> {
  const response = await apiClient.get<{ data: UsageSummary }>('/usage/summary', options)
  return response.data.data
}

/**
 * Get daily usage breakdown
 */
export async function getDailyUsage(days: number = 30, options: RequestOptions = {}): Promise<DailyUsageList> {
  const response = await apiClient.get<{ data: DailyUsageList }>(`/usage/daily?days=${days}`, options)
  return response.data.data
}

/**
 * Get monthly usage summaries
 */
export async function getMonthlyUsage(months: number = 12): Promise<MonthlyUsageList> {
  const response = await apiClient.get<{ data: MonthlyUsageList }>(`/usage/monthly?months=${months}`)
  return response.data.data
}

/**
 * Get usage for a specific session
 */
export async function getSessionUsage(sessionId: string): Promise<SessionUsage> {
  const response = await apiClient.get<{ data: SessionUsage }>(`/usage/session/${sessionId}`)
  return response.data.data
}

/**
 * Get model pricing information
 */
export async function getModelPricing(): Promise<PricingList> {
  const response = await apiClient.get<{ data: PricingList }>('/usage/pricing')
  return response.data.data
}

/**
 * Get run-aware usage summary for the selected time range
 */
export async function getAgentUsageSummary(
  range: AgentUsageRange = '30d',
  options: RequestOptions = {}
): Promise<AgentUsageSummary> {
  const response = await apiClient.get<{ data: AgentUsageSummary }>(
    `/usage/agent/summary?range=${range}`,
    options
  )
  return response.data.data
}

/**
 * Get recent agent runs
 */
export async function getAgentUsageRuns(
  range: AgentUsageRange = '30d',
  limit: number = 20,
  options: RequestOptions = {}
): Promise<AgentUsageRunList> {
  const response = await apiClient.get<{ data: AgentUsageRunList }>(
    `/usage/agent/runs?range=${range}&limit=${limit}`,
    options
  )
  return response.data.data
}

/**
 * Get grouped agent usage breakdown
 */
export async function getAgentUsageBreakdown(
  range: AgentUsageRange = '30d',
  groupBy: AgentUsageBreakdownGroup = 'model',
  options: RequestOptions = {}
): Promise<AgentUsageBreakdownList> {
  const response = await apiClient.get<{ data: AgentUsageBreakdownList }>(
    `/usage/agent/breakdown?range=${range}&group_by=${groupBy}`,
    options
  )
  return response.data.data
}

/**
 * Get run-aware daily usage trends
 */
export async function getAgentUsageTimeseries(
  range: AgentUsageRange = '30d',
  bucket: 'hour' | 'day' | 'week' = 'day',
  options: RequestOptions = {}
): Promise<AgentUsageTimeseries> {
  const response = await apiClient.get<{ data: AgentUsageTimeseries }>(
    `/usage/agent/timeseries?range=${range}&bucket=${bucket}`,
    options
  )
  return response.data.data
}
