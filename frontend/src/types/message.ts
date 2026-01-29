import type { FileInfo } from '../api/file';

export type MessageType = "user" | "assistant" | "tool" | "step" | "attachments" | "report";

// Source citation for report bibliography
export interface SourceCitation {
  url: string;
  title: string;
  snippet?: string;
  access_time: string;
  source_type: 'search' | 'browser' | 'file';
}

export interface Message {
  type: MessageType;
  content: BaseContent;
}

export interface BaseContent {
  timestamp: number;
}

export interface MessageContent extends BaseContent {
  content: string;
}

export interface ToolContent extends BaseContent {
  tool_call_id: string;
  name: string;
  function: string;
  args: any;
  content?: any;
  status: "calling" | "called";
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

export interface StepContent extends BaseContent {
  id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  tools: ToolContent[];
}

export interface AttachmentsContent extends BaseContent {
  role: "user" | "assistant";
  attachments: FileInfo[];
}

export interface ReportSection {
  title: string;
  preview: string;
  level?: number;
}

export interface ReportContent extends BaseContent {
  id: string;
  title: string;
  content: string;
  lastModified: number;
  fileCount?: number;
  sections?: ReportSection[];
  attachments?: FileInfo[];
  sources?: SourceCitation[];
}
