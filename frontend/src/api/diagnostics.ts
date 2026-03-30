import { apiClient } from '@/api/client';
import type { ApiResponse } from '@/api/client';

export interface ContainerLogsPreview {
  enabled: boolean;
  backend: string[];
  sandbox: string[];
  message?: string | null;
}

export async function fetchContainerLogsPreview(): Promise<ContainerLogsPreview> {
  const { data } = await apiClient.get<ApiResponse<ContainerLogsPreview>>('/diagnostics/container-logs');
  return data.data;
}
