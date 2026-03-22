import { apiClient } from './client';

// --- Types ---

export interface CredentialField {
  key: string;
  label: string;
  description: string;
  placeholder: string;
  required: boolean;
  secret: boolean;
}

export interface McpTemplate {
  credential_fields: readonly CredentialField[];
}

export interface CatalogConnector {
  id: string;
  name: string;
  description: string;
  connector_type: string;
  icon: string;
  brand_color: string;
  category: string;
  is_official: boolean;
  availability: 'available' | 'coming_soon' | 'built_in';
  mcp_template: McpTemplate | null;
}

export interface CustomApiConfigResponse {
  base_url: string;
  auth_type: string;
  api_key: string | null;
  headers: Record<string, string>;
  description: string | null;
}

export interface CustomMcpConfigResponse {
  transport: string;
  command: string | null;
  args: readonly string[];
  url: string | null;
  headers: Record<string, string>;
  env: Record<string, string>;
  description: string | null;
}

export interface UserConnector {
  id: string;
  connector_id: string | null;
  connector_type: string;
  name: string;
  description: string;
  icon: string;
  status: string;
  enabled: boolean;
  last_connected_at: string | null;
  error_message: string | null;
  api_config: CustomApiConfigResponse | null;
  mcp_config: CustomMcpConfigResponse | null;
}

export interface ConnectorListResponse {
  connectors: CatalogConnector[];
  total: number;
}

export interface UserConnectorListResponse {
  connectors: UserConnector[];
  total: number;
  connected_count: number;
}

export interface CreateCustomApiRequest {
  name: string;
  description?: string;
  base_url: string;
  auth_type?: string;
  api_key?: string;
  headers?: Record<string, string>;
}

export interface CreateCustomMcpRequest {
  name: string;
  description?: string;
  transport: string;
  command?: string;
  args?: string[];
  url?: string;
  headers?: Record<string, string>;
  env?: Record<string, string>;
}

export interface UpdateUserConnectorRequest {
  name?: string;
  description?: string;
  enabled?: boolean;
  api_config?: Record<string, unknown>;
  mcp_config?: Record<string, unknown>;
}

export interface TestConnectionResponse {
  ok: boolean;
  message: string;
  latency_ms: number | null;
}

// --- API functions ---

export async function getCatalogConnectors(
  type?: string,
  search?: string,
): Promise<CatalogConnector[]> {
  const params: Record<string, string> = {};
  if (type) params.type = type;
  if (search) params.search = search;
  const response = await apiClient.get<{ data: ConnectorListResponse }>(
    '/connectors/catalog',
    { params },
  );
  return response.data.data.connectors;
}

export async function getUserConnectors(): Promise<UserConnectorListResponse> {
  const response = await apiClient.get<{ data: UserConnectorListResponse }>(
    '/connectors/user',
  );
  return response.data.data;
}

export async function connectApp(
  connectorId: string,
  credentials?: Record<string, string>,
): Promise<UserConnector> {
  const response = await apiClient.post<{ data: UserConnector }>(
    `/connectors/user/connect/${connectorId}`,
    credentials ? { credentials } : undefined,
  );
  return response.data.data;
}

export async function createCustomApi(
  data: CreateCustomApiRequest,
): Promise<UserConnector> {
  const response = await apiClient.post<{ data: UserConnector }>(
    '/connectors/user/custom-api',
    data,
  );
  return response.data.data;
}

export async function createCustomMcp(
  data: CreateCustomMcpRequest,
): Promise<UserConnector> {
  const response = await apiClient.post<{ data: UserConnector }>(
    '/connectors/user/custom-mcp',
    data,
  );
  return response.data.data;
}

export async function updateUserConnector(
  id: string,
  data: UpdateUserConnectorRequest,
): Promise<UserConnector> {
  const response = await apiClient.put<{ data: UserConnector }>(
    `/connectors/user/${id}`,
    data,
  );
  return response.data.data;
}

export async function deleteUserConnector(id: string): Promise<void> {
  await apiClient.delete(`/connectors/user/${id}`);
}

export async function testConnection(id: string): Promise<TestConnectionResponse> {
  const response = await apiClient.post<{ data: TestConnectionResponse }>(
    `/connectors/user/${id}/test`,
  );
  return response.data.data;
}
