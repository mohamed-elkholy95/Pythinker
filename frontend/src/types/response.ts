import { AgentSSEEvent } from "./event";

export enum SessionStatus {
    PENDING = "pending",
    INITIALIZING = "initializing",  // Phase 2: Sandbox being prepared
    RUNNING = "running",
    WAITING = "waiting",
    COMPLETED = "completed",
    FAILED = "failed",
    CANCELLED = "cancelled"
}

export enum AgentMode {
    DISCUSS = "discuss",
    AGENT = "agent"
}

export enum ResearchMode {
    FAST_SEARCH = "fast_search",
    DEEP_RESEARCH = "deep_research"
}

export type StreamingMode = 'cdp_only'
export type SessionSource = 'web' | 'telegram' | string

export interface SandboxInfo {
    sandbox_id: string;
    streaming_mode: StreamingMode;
    status: string;
}

export interface CreateSessionResponse {
    session_id: string;
    mode: AgentMode;
    research_mode: ResearchMode;
    sandbox: SandboxInfo | null;
    status: SessionStatus;
}

export interface GetSessionResponse {
    session_id: string;
    title: string | null;
    status: SessionStatus;
    source: SessionSource;
    research_mode: ResearchMode;
    streaming_mode: StreamingMode | null;
    events: AgentSSEEvent[];
    is_shared: boolean;
}

export interface ListSessionItem {
    session_id: string;
    title: string | null;
    latest_message: string | null;
    latest_message_at: number | null;
    status: SessionStatus;
    unread_message_count: number;
    is_shared: boolean;
    source: SessionSource;
}

export interface ListSessionResponse {
    sessions: ListSessionItem[];
}

export interface ConsoleRecord {
    ps1: string;
    command: string;
    output: string;
  }
  
  export interface ShellViewResponse {
    output: string;
    session_id: string;
    console: ConsoleRecord[];
  }

export interface FileViewResponse {
    content: string;
    file: string;
}

export interface SignedUrlResponse {
    signed_url: string;
    expires_in: number;
}

export interface ShareSessionResponse {
    session_id: string;
    is_shared: boolean;
}

export interface SharedSessionResponse {
    session_id: string;
    title: string | null;
    status: SessionStatus;
    events: AgentSSEEvent[];
    is_shared: boolean;
}
  
