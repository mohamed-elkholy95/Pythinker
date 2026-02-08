// Backend API service
import { apiClient, API_CONFIG, ApiResponse, createSSEConnection, SSECallbacks } from './client';
import { AgentSSEEvent } from '../types/event';
import { CreateSessionResponse, GetSessionResponse, ShellViewResponse, FileViewResponse, ListSessionResponse, SignedUrlResponse, ShareSessionResponse, SharedSessionResponse } from '../types/response';
import type { FileInfo } from './file';



/**
 * Agent mode enum - determines which flow to use
 */
export type AgentMode = 'discuss' | 'agent';

export interface CreateSessionOptions {
  require_fresh_sandbox?: boolean;
  sandbox_wait_seconds?: number;
}

/**
 * Create Session
 * @param mode - Agent mode: 'discuss' (simple chat) or 'agent' (full capabilities)
 * @returns Session
 */
export async function createSession(
  mode: AgentMode = 'agent',
  options?: CreateSessionOptions
): Promise<CreateSessionResponse> {
  const response = await apiClient.put<ApiResponse<CreateSessionResponse>>('/sessions', {
    mode,
    ...(options || {}),
  });
  return response.data.data;
}

export async function getSession(sessionId: string): Promise<GetSessionResponse> {
  const response = await apiClient.get<ApiResponse<GetSessionResponse>>(`/sessions/${sessionId}`);
  return response.data.data;
}

export async function getSessions(): Promise<ListSessionResponse> {
  const response = await apiClient.get<ApiResponse<ListSessionResponse>>('/sessions');
  return response.data.data;
}

export async function getSessionsSSE(callbacks?: SSECallbacks<ListSessionResponse>): Promise<() => void> {
  return createSSEConnection<ListSessionResponse>(
    '/sessions',
    {
      method: 'POST'
    },
    callbacks
  );
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiClient.delete<ApiResponse<void>>(`/sessions/${sessionId}`);
}

export async function stopSession(sessionId: string): Promise<void> {
  await apiClient.post<ApiResponse<void>>(`/sessions/${sessionId}/stop`);
}

/**
 * Pause a session for user takeover
 * This pauses agent execution so the user can control the browser via VNC
 * @param sessionId Session ID to pause
 */
export async function pauseSession(sessionId: string): Promise<void> {
  await apiClient.post<ApiResponse<void>>(`/sessions/${sessionId}/pause`);
}

/**
 * Resume session request options
 */
export interface ResumeSessionOptions {
  context?: string;
  persist_login_state?: boolean;
}

/**
 * Resume a paused session after user takeover
 * This resumes agent execution after the user finishes their takeover session
 * @param sessionId Session ID to resume
 * @param options Optional context and persist_login_state settings
 */
export async function resumeSession(sessionId: string, options?: ResumeSessionOptions): Promise<void> {
  await apiClient.post<ApiResponse<void>>(`/sessions/${sessionId}/resume`, options || {});
}

export async function renameSession(sessionId: string, title: string): Promise<void> {
  await apiClient.patch<ApiResponse<void>>(`/sessions/${sessionId}/rename`, { title });
}

/**
 * Create VNC signed URL
 * @param sessionId Session ID to create signed URL for
 * @param expireMinutes URL expiration time in minutes (default: 15)
 * @returns Signed URL response for VNC WebSocket access
 */
export async function createVncSignedUrl(sessionId: string, expireMinutes: number = 15): Promise<SignedUrlResponse> {
  const response = await apiClient.post<ApiResponse<SignedUrlResponse>>(`/sessions/${sessionId}/vnc/signed-url`, {
    expire_minutes: expireMinutes
  });
  return response.data.data;
}

/**
 * Get VNC WebSocket URL with signed URL
 * @param sessionId Session ID
 * @param expireMinutes URL expiration time in minutes (default: 60)
 * @returns Promise resolving to signed VNC WebSocket URL string
 *
 * @example
 * // Signed URL (no Authorization header needed, more secure)
 * const url = await getVNCUrl('session123');
 * const url = await getVNCUrl('session123', 120);
 */
export const getVNCUrl = async (
  sessionId: string,
  expireMinutes: number = 15
): Promise<string> => {
    const signedUrlResponse = await createVncSignedUrl(sessionId, expireMinutes);
    const wsBaseUrl = API_CONFIG.host.replace(/^http/, 'ws');
    return `${wsBaseUrl}${signedUrlResponse.signed_url}`;
}

/**
 * Get VNC screenshot from sandbox
 * @param sessionId Session ID
 * @returns Promise resolving to screenshot blob
 *
 * @example
 * const blob = await getVNCScreenshot('session123');
 * const url = URL.createObjectURL(blob);
 */
export async function getVNCScreenshot(
  sessionId: string,
  quality: number = 75,
  scale: number = 0.5
): Promise<Blob> {
  const response = await apiClient.get(`/sessions/${sessionId}/vnc/screenshot`, {
    responseType: 'blob',
    params: { quality, scale, _t: Date.now() },  // Cache-busting timestamp
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache'
    }
  });
  return response.data;
}

/**
 * Attachment info for chat request
 */
export interface ChatAttachment {
  file_id: string;
  filename: string;
  content_type: string;
  size: number;
  upload_date: string;
}

/**
 * Chat options for additional features
 */
export interface ChatOptions {
  deep_research?: boolean;  // Enable deep research mode (parallel searches with approval)
}

/**
 * Chat with Session (using SSE to receive streaming responses)
 * @param sessionId Session ID
 * @param message User message
 * @param eventId Optional last event ID for resumption
 * @param attachments Optional file attachments
 * @param skills Optional skill IDs to enable for this message
 * @param options Optional chat options (deep_research, etc.)
 * @param callbacks SSE callbacks for events
 * @returns A function to cancel the SSE connection
 */
export const chatWithSession = async (
  sessionId: string,
  message: string = '',
  eventId?: string,
  attachments?: ChatAttachment[],
  skills?: string[],
  options?: ChatOptions,
  callbacks?: SSECallbacks<AgentSSEEvent['data']>
): Promise<() => void> => {
  return createSSEConnection<AgentSSEEvent['data']>(
    `/sessions/${sessionId}/chat`,
    {
      method: 'POST',
      body: {
        message,
        timestamp: Math.floor(Date.now() / 1000),
        event_id: eventId,
        attachments,
        skills,
        deep_research: options?.deep_research
      }
    },
    callbacks
  );
};

/**
 * View Shell session output
 * @param sessionId Session ID
 * @param shellSessionId Shell session ID
 * @returns Shell session output content
 */
export async function viewShellSession(sessionId: string, shellSessionId: string): Promise<ShellViewResponse> {
  const response = await apiClient.post<ApiResponse<ShellViewResponse>>(
    `/sessions/${sessionId}/shell`,
    { session_id: shellSessionId }
  );
  return response.data.data;
}

/**
 * Confirm or reject a tool action
 * @param sessionId Session ID
 * @param actionId Tool action ID
 * @param accept Whether to accept the action
 */
export async function confirmToolAction(sessionId: string, actionId: string, accept: boolean): Promise<void> {
  await apiClient.post<ApiResponse<void>>(
    `/sessions/${sessionId}/actions/${actionId}/confirm`,
    { accept }
  );
}

/**
 * View file content
 * @param sessionId Session ID
 * @param file File path
 * @returns File content
 */
export async function viewFile(sessionId: string, file: string): Promise<FileViewResponse> {
  const response = await apiClient.post<ApiResponse<FileViewResponse>>(
    `/sessions/${sessionId}/file`,
    { file }
  );
  return response.data.data;
}

export async function getSessionFiles(sessionId: string): Promise<FileInfo[]> {
  const response = await apiClient.get<ApiResponse<FileInfo[]>>(`/sessions/${sessionId}/files`);
  return response.data.data;
}

export async function clearUnreadMessageCount(sessionId: string): Promise<void> {
  await apiClient.post<ApiResponse<void>>(`/sessions/${sessionId}/clear_unread_message_count`);
}

/**
 * Share a session to make it publicly accessible
 * @param sessionId Session ID to share
 * @returns Share session response with current sharing status
 * 
 * @example
 * ```typescript
 * // Share a session
 * const result = await shareSession('session123');
 * console.log(result.is_shared); // true
 * ```
 */
export async function shareSession(sessionId: string): Promise<ShareSessionResponse> {
  const response = await apiClient.post<ApiResponse<ShareSessionResponse>>(`/sessions/${sessionId}/share`);
  return response.data.data;
}

/**
 * Unshare a session to make it private again
 * @param sessionId Session ID to unshare
 * @returns Share session response with current sharing status
 * 
 * @example
 * ```typescript
 * // Unshare a session
 * const result = await unshareSession('session123');
 * console.log(result.is_shared); // false
 * ```
 */
export async function unshareSession(sessionId: string): Promise<ShareSessionResponse> {
  const response = await apiClient.delete<ApiResponse<ShareSessionResponse>>(`/sessions/${sessionId}/share`);
  return response.data.data;
}

/**
 * Get a shared session without authentication
 * This endpoint allows public access to sessions that have been marked as shared.
 * No authentication token is required.
 * 
 * @param sessionId Session ID to retrieve
 * @returns Shared session data (accessible publicly)
 * 
 * @example
 * ```typescript
 * // Get a shared session (no auth required)
 * try {
 *   const sharedSession = await getSharedSession('session123');
 *   console.log(sharedSession.title);
 *   console.log(sharedSession.events);
 * } catch (error) {
 *   console.error('Session not found or not shared');
 * }
 * ```
 */
export async function getSharedSession(sessionId: string): Promise<SharedSessionResponse> {
  const response = await apiClient.get<ApiResponse<SharedSessionResponse>>(`/sessions/shared/${sessionId}`);
  return response.data.data;
}

export async function getSharedSessionFiles(sessionId: string): Promise<FileInfo[]> {
  const response = await apiClient.get<ApiResponse<FileInfo[]>>(`/sessions/${sessionId}/share/files`);
  return response.data.data;
}

// ============================================================================
// Workspace API
// ============================================================================

/**
 * Workspace template interface
 */
export interface WorkspaceTemplate {
  name: string;
  description: string;
  folders: Record<string, string>;
  trigger_keywords: string[];
}

/**
 * Workspace template list response
 */
export interface WorkspaceTemplateListResponse {
  templates: WorkspaceTemplate[];
}

/**
 * Session workspace response
 */
export interface SessionWorkspaceResponse {
  session_id: string;
  workspace_structure: Record<string, string> | null;
  workspace_root: string | null;
}

/**
 * Get all available workspace templates
 * @returns List of workspace templates
 *
 * @example
 * ```typescript
 * const templates = await getWorkspaceTemplates();
 * console.log(templates.templates); // Array of templates
 * ```
 */
export async function getWorkspaceTemplates(): Promise<WorkspaceTemplateListResponse> {
  const response = await apiClient.get<ApiResponse<WorkspaceTemplateListResponse>>('/workspace/templates');
  return response.data.data;
}

/**
 * Get a specific workspace template by name
 * @param templateName - Name of the template (e.g., 'research', 'data_analysis')
 * @returns Workspace template details
 *
 * @example
 * ```typescript
 * const template = await getWorkspaceTemplate('research');
 * console.log(template.folders); // { inputs: "...", research: "..." }
 * ```
 */
export async function getWorkspaceTemplate(templateName: string): Promise<WorkspaceTemplate> {
  const response = await apiClient.get<ApiResponse<WorkspaceTemplate>>(`/workspace/templates/${templateName}`);
  return response.data.data;
}

/**
 * Get workspace structure for a session
 * @param sessionId - Session ID
 * @returns Session workspace structure
 *
 * @example
 * ```typescript
 * const workspace = await getSessionWorkspace('session123');
 * if (workspace.workspace_structure) {
 *   console.log('Workspace folders:', workspace.workspace_structure);
 * }
 * ```
 */
export async function getSessionWorkspace(sessionId: string): Promise<SessionWorkspaceResponse> {
  const response = await apiClient.get<ApiResponse<SessionWorkspaceResponse>>(`/workspace/sessions/${sessionId}`);
  return response.data.data;
}

// ============================================================================
// Deep Research API
// ============================================================================

/**
 * Approve a pending deep research session to start execution
 * @param sessionId Session ID
 */
export async function approveDeepResearch(sessionId: string): Promise<void> {
  await apiClient.post<ApiResponse<void>>(`/sessions/${sessionId}/deep-research/approve`);
}

/**
 * Skip a specific query or all pending queries in deep research
 * @param sessionId Session ID
 * @param queryId Optional query ID to skip (if not provided, skips all)
 */
export async function skipDeepResearchQuery(sessionId: string, queryId?: string): Promise<void> {
  await apiClient.post<ApiResponse<void>>(`/sessions/${sessionId}/deep-research/skip`, {
    query_id: queryId
  });
}

/**
 * Deep research status response
 */
export interface DeepResearchStatusResponse {
  research_id: string;
  status: string;
  total_queries: number;
  completed_queries: number;
}

/**
 * Get the current status of deep research for a session
 * @param sessionId Session ID
 */
export async function getDeepResearchStatus(sessionId: string): Promise<DeepResearchStatusResponse> {
  const response = await apiClient.get<ApiResponse<DeepResearchStatusResponse>>(
    `/sessions/${sessionId}/deep-research/status`
  );
  return response.data.data;
}

// ============================================================================
// Browse URL API
// ============================================================================

/**
 * Request for browsing a URL directly
 */
export interface BrowseUrlRequest {
  url: string;
}

/**
 * Browse URL SSE callbacks
 */
export interface BrowseUrlCallbacks {
  onOpen?: () => void;
  onToolEvent?: (event: AgentSSEEvent['data']) => void;
  onMessage?: (message: string) => void;
  onClose?: () => void;
  onError?: (error: Error) => void;
}

/**
 * Navigate browser directly to a URL from search results
 * This triggers the browser in the sandbox to navigate to the specified URL,
 * providing a faster workflow than having the agent search again.
 *
 * Returns an SSE stream with tool events for the navigation.
 *
 * @param sessionId Session ID
 * @param url URL to navigate to
 * @param callbacks Optional callbacks for SSE events
 * @returns A function to cancel the SSE connection
 *
 * @example
 * ```typescript
 * // After user clicks a search result
 * const cancel = await browseUrl('session123', 'https://example.com/article', {
 *   onToolEvent: (event) => console.log('Tool event:', event),
 *   onMessage: (msg) => console.log('Message:', msg),
 * });
 * ```
 */
export async function browseUrl(
  sessionId: string,
  url: string,
  callbacks?: BrowseUrlCallbacks
): Promise<() => void> {
  return createSSEConnection<AgentSSEEvent['data']>(
    `/sessions/${sessionId}/browse`,
    {
      method: 'POST',
      body: { url }
    },
    {
      onOpen: callbacks?.onOpen,
      onMessage: ({ event, data }) => {
        if (event === 'tool' && callbacks?.onToolEvent) {
          callbacks.onToolEvent(data);
        } else if (event === 'message' && callbacks?.onMessage) {
          const messageData = data as { content?: string };
          if (messageData.content) {
            callbacks.onMessage(messageData.content);
          }
        }
      },
      onClose: callbacks?.onClose,
      onError: callbacks?.onError,
    }
  );
}

// ============================================================================
// Sandbox API
// ============================================================================

/**
 * Get a signed WebSocket URL for sandbox access (proxied through backend)
 * @param sessionId Session ID
 * @param target 'screencast' or 'input'
 * @returns Signed WebSocket URL
 */
async function getSandboxSignedUrl(sessionId: string, target: string): Promise<string> {
  const response = await apiClient.post<ApiResponse<SignedUrlResponse>>(
    `/sessions/${sessionId}/sandbox/signed-url?target=${target}`,
    { expire_minutes: 15 }
  );
  const wsBaseUrl = API_CONFIG.host.replace(/^http/, 'ws');
  return `${wsBaseUrl}${response.data.data.signed_url}`;
}

/**
 * Get screencast WebSocket URL via signed URL (proxied through backend)
 * @param sessionId Session ID
 * @param quality JPEG quality (1-100)
 * @param maxFps Max frames per second (1-30)
 * @returns Signed WebSocket URL for screencast stream
 */
export async function getScreencastUrl(
  sessionId: string,
  quality: number = 70,
  maxFps: number = 15,
): Promise<string> {
  const baseUrl = await getSandboxSignedUrl(sessionId, 'screencast');
  const separator = baseUrl.includes('?') ? '&' : '?';
  return `${baseUrl}${separator}quality=${quality}&max_fps=${maxFps}`;
}

/**
 * Get input stream WebSocket URL via signed URL (proxied through backend)
 * Used for interactive takeover - forwards mouse/keyboard events to sandbox
 * @param sessionId Session ID
 * @returns Signed WebSocket URL for input stream
 */
export async function getInputStreamUrl(sessionId: string): Promise<string> {
  return getSandboxSignedUrl(sessionId, 'input');
}

/**
 * Submit a rating for a report
 * @param sessionId Session ID
 * @param reportId Report ID
 * @param rating Rating from 1 to 5
 * @param feedback Optional feedback text
 */
export async function submitRating(
  sessionId: string,
  reportId: string,
  rating: number,
  feedback?: string
): Promise<void> {
  await apiClient.post('/ratings', {
    session_id: sessionId,
    report_id: reportId,
    rating,
    feedback,
  });
}
