import { AgentSSEEvent } from "./event";

export enum SessionStatus {
    PENDING = "pending",
    INITIALIZING = "initializing",  // Phase 2: Sandbox being prepared
    RUNNING = "running",
    WAITING = "waiting",
    COMPLETED = "completed",
    FAILED = "failed"
}

export enum AgentMode {
    DISCUSS = "discuss",
    AGENT = "agent"
}

// Phase 4: Sandbox info for optimistic VNC connection
export interface SandboxInfo {
    sandbox_id: string;
    vnc_url: string | null;
    status: string;
}

export interface CreateSessionResponse {
    session_id: string;
    mode: AgentMode;
    sandbox: SandboxInfo | null;  // Phase 4: Early sandbox info for optimistic VNC
    status: SessionStatus;
}

export interface GetSessionResponse {
    session_id: string;
    title: string | null;
    status: SessionStatus;
    events: AgentSSEEvent[];
    is_shared: boolean;
    openreplay_session_id?: string | null;
    openreplay_session_url?: string | null;
}

export interface ListSessionItem {
    session_id: string;
    title: string | null;
    latest_message: string | null;
    latest_message_at: number | null;
    status: SessionStatus;
    unread_message_count: number;
    is_shared: boolean;
    openreplay_session_id?: string | null;
    openreplay_session_url?: string | null;
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
    openreplay_session_id?: string | null;
    openreplay_session_url?: string | null;
}
  
