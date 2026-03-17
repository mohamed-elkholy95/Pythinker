import { apiClient } from './client'

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

/**
 * Get usage summary for today and this month
 */
export async function getUsageSummary(): Promise<UsageSummary> {
  const response = await apiClient.get<{ data: UsageSummary }>('/usage/summary')
  return response.data.data
}

/**
 * Get daily usage breakdown
 */
export async function getDailyUsage(days: number = 30): Promise<DailyUsageList> {
  const response = await apiClient.get<{ data: DailyUsageList }>(`/usage/daily?days=${days}`)
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
