import { apiClient } from './client'

// --- Types ---

export interface McpServerStatus {
  name: string
  healthy: boolean
  degraded: boolean
  transport: string | null
  tools_count: number
  avg_response_time_ms: number
  success_rate: number
  last_error: string | null
  last_check: string | null
  consecutive_failures: number
}

export interface McpStatusResponse {
  overall_status: string
  total_servers: number
  healthy_count: number
  unhealthy_count: number
  degraded_count: number
  total_tools: number
  servers: McpServerStatus[]
}

export interface McpToolInfo {
  name: string
  description: string | null
  server_name: string
  parameters: Record<string, unknown> | null
}

export interface McpToolListResponse {
  server_name: string | null
  tools: McpToolInfo[]
  total: number
}

export interface McpTestConnectionRequest {
  name: string
  transport: string
  command?: string | null
  args?: string[] | null
  url?: string | null
  env?: Record<string, string> | null
  headers?: Record<string, string> | null
}

export interface McpTestConnectionResponse {
  success: boolean
  latency_ms: number
  tools_count: number
  error: string | null
}

// --- SSE Event Data ---

export interface McpHealthEventData {
  event_id: string | null
  timestamp: number
  server_name: string
  healthy: boolean
  degraded: boolean
  error: string | null
  tools_available: number
  avg_response_time_ms: number
  success_rate: number
  last_check: string | null
}

// --- API Functions ---

export async function getMcpStatus(): Promise<McpStatusResponse> {
  const response = await apiClient.get<{ data: McpStatusResponse }>('/mcp/status')
  return response.data.data
}

export async function getMcpServers(): Promise<McpServerStatus[]> {
  const response = await apiClient.get<{ data: McpServerStatus[] }>('/mcp/servers')
  return response.data.data
}

export async function getMcpServerTools(
  serverName: string,
): Promise<McpToolListResponse> {
  const response = await apiClient.get<{ data: McpToolListResponse }>(
    `/mcp/servers/${encodeURIComponent(serverName)}/tools`,
  )
  return response.data.data
}

export async function testMcpConnection(
  config: McpTestConnectionRequest,
): Promise<McpTestConnectionResponse> {
  const response = await apiClient.post<{ data: McpTestConnectionResponse }>(
    '/mcp/test-connection',
    config,
  )
  return response.data.data
}
