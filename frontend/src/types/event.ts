import type { FileInfo } from '../api/file';

export type AgentSSEEvent = {
  event: 'tool' | 'step' | 'message' | 'error' | 'done' | 'title' | 'wait' | 'plan' | 'attachments' | 'mode_change' | 'suggestion' | 'report' | 'stream' | 'progress';
  data: ToolEventData | StepEventData | MessageEventData | ErrorEventData | DoneEventData | TitleEventData | WaitEventData | PlanEventData | ModeChangeEventData | SuggestionEventData | ReportEventData | StreamEventData | ProgressEventData;
}

export interface BaseEventData {
  event_id: string;
  timestamp: number;
}

export interface ToolEventData extends BaseEventData {
  tool_call_id: string;
  name: string;
  status: "calling" | "called";
  function: string;
  args: {[key: string]: any};
  content?: any;
  // Action/observation metadata
  action_type?: string;
  observation_type?: string;
  command?: string;
  cwd?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number;
  file_path?: string;
  diff?: string;
  runtime_status?: string;
  // Security/confirmation metadata
  security_risk?: string;
  security_reason?: string;
  security_suggestions?: string[];
  confirmation_state?: string;
}

export interface StepEventData extends BaseEventData {
  status: "pending" | "running" | "completed" | "failed"
  id: string
  description: string
}

export interface MessageEventData extends BaseEventData {
  content: string;
  role: "user" | "assistant";
  attachments: FileInfo[];
}

export interface ErrorEventData extends BaseEventData {
  error: string;
}

export interface DoneEventData extends BaseEventData {
}

export interface WaitEventData extends BaseEventData {
}

export interface TitleEventData extends BaseEventData {
  title: string;
}

export interface PlanEventData extends BaseEventData {
  steps: StepEventData[];
}

export interface ModeChangeEventData extends BaseEventData {
  mode: 'discuss' | 'agent';
  reason?: string;
}

export interface SuggestionEventData extends BaseEventData {
  suggestions: string[];
}

export interface ReportEventData extends BaseEventData {
  id: string;
  title: string;
  content: string;
  attachments?: FileInfo[];
}

export interface StreamEventData extends BaseEventData {
  content: string;
  is_final: boolean;
}

export type PlanningPhase = 'received' | 'analyzing' | 'planning' | 'finalizing';

export interface ProgressEventData extends BaseEventData {
  phase: PlanningPhase;
  message: string;
  estimated_steps?: number;
  progress_percent?: number;
}
