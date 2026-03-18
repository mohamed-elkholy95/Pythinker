import { apiClient } from './client'

export interface UserSettings {
  llm_provider: string
  model_name: string
  api_base: string
  temperature: number
  max_tokens: number
  search_provider: string
  browser_agent_max_steps: number
  browser_agent_timeout: number
  browser_agent_use_vision: boolean
  response_verbosity_preference: 'adaptive' | 'concise' | 'detailed'
  clarification_policy: 'auto' | 'always' | 'never'
  quality_floor_enforced: boolean
  skill_auto_trigger_enabled: boolean
}

export interface LLMProviderInfo {
  id: string
  name: string
  models: string[]
  requires_api_key: boolean
  api_base?: string
  setup_note?: string
}

export interface SearchProviderInfo {
  id: string
  name: string
  requires_api_key: boolean
}

export interface ProvidersInfo {
  llm_providers: LLMProviderInfo[]
  search_providers: SearchProviderInfo[]
}

export interface UpdateSettingsRequest {
  llm_provider?: string
  model_name?: string
  api_base?: string
  temperature?: number
  max_tokens?: number
  search_provider?: string
  browser_agent_max_steps?: number
  browser_agent_timeout?: number
  browser_agent_use_vision?: boolean
  response_verbosity_preference?: 'adaptive' | 'concise' | 'detailed'
  clarification_policy?: 'auto' | 'always' | 'never'
  quality_floor_enforced?: boolean
  skill_auto_trigger_enabled?: boolean
}

/**
 * Get current user's settings
 */
export async function getSettings(): Promise<UserSettings> {
  const response = await apiClient.get<{ data: UserSettings }>('/settings')
  return response.data.data
}

/**
 * Update user's settings
 */
export async function updateSettings(settings: UpdateSettingsRequest): Promise<UserSettings> {
  const response = await apiClient.put<{ data: UserSettings }>('/settings', settings)
  return response.data.data
}

/**
 * Get available providers
 */
export async function getProviders(): Promise<ProvidersInfo> {
  const response = await apiClient.get<{ data: ProvidersInfo }>('/settings/providers')
  return response.data.data
}

/**
 * Actual running server-side LLM configuration (from env vars / LLM singleton).
 * This is what the backend is ACTUALLY using, not user preferences.
 */
export interface ServerConfig {
  model_name: string
  api_base: string
  temperature: number
  max_tokens: number
  llm_provider: string
  search_provider: string
  search_provider_chain: string[]
  configured_search_keys: string[]
}

/**
 * Get the actual running LLM configuration from the backend server.
 */
export async function getServerConfig(): Promise<ServerConfig> {
  const response = await apiClient.get<{ data: ServerConfig }>('/settings/server-config')
  return response.data.data
}
