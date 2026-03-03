// Channel linking API service
import { apiClient } from './client';
import type { ApiResponse } from './client';

/**
 * Response from generating a link code
 */
export interface GenerateLinkCodeResponse {
  code: string;
  channel: string;
  expires_in_seconds: number;
  instructions: string;
}

/**
 * A single linked channel entry
 */
export interface LinkedChannel {
  channel: string;
  sender_id: string;
  linked_at: string | null;
}

/**
 * Response from listing linked channels
 */
export interface LinkedChannelsListResponse {
  channels: LinkedChannel[];
}

/**
 * Generate a one-time link code for a channel
 * @param channel Channel to generate code for (default: telegram)
 * @returns Link code with expiry and instructions
 */
export async function generateLinkCode(
  channel: string = 'telegram',
): Promise<GenerateLinkCodeResponse> {
  const response = await apiClient.post<ApiResponse<GenerateLinkCodeResponse>>(
    '/channel-links/generate',
    { channel },
  );
  return response.data.data;
}

/**
 * Get all linked channels for the current user
 * @returns Array of linked channels
 */
export async function getLinkedChannels(): Promise<LinkedChannel[]> {
  const response = await apiClient.get<ApiResponse<LinkedChannelsListResponse>>(
    '/channel-links',
  );
  return response.data.data?.channels ?? [];
}

/**
 * Unlink a channel from the current user's account
 * @param channel Channel to unlink
 */
export async function unlinkChannel(channel: string): Promise<void> {
  await apiClient.delete(`/channel-links/${channel}`);
}
