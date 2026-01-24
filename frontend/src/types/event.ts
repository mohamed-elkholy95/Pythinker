import type { FileInfo } from '../api/file';

export type AgentSSEEvent = {
  event: 'tool' | 'step' | 'message' | 'error' | 'done' | 'title' | 'wait' | 'plan' | 'attachments' | 'mode_change' | 'suggestion' | 'report' | 'stream';
  data: ToolEventData | StepEventData | MessageEventData | ErrorEventData | DoneEventData | TitleEventData | WaitEventData | PlanEventData | ModeChangeEventData | SuggestionEventData | ReportEventData | StreamEventData;
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