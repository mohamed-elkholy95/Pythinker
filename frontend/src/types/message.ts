import type { FileInfo } from '../api/file';

export type MessageType = "user" | "assistant" | "tool" | "step" | "attachments" | "report" | "deep_research" | "skill_delivery" | "thought";

// Step item types for interleaved tools and thoughts
export type StepItemType = 'tool' | 'thought';

export interface StepItem {
  type: StepItemType;
  timestamp: number;
  content: ToolContent | ThoughtContent;
}

export interface ThoughtContent {
  id: string;
  text: string;
  thought_type?: 'observation' | 'analysis' | 'hypothesis' | 'conclusion';
  confidence?: number;
  timestamp?: number;
}

// Source citation for report bibliography
export interface SourceCitation {
  url: string;
  title: string;
  snippet?: string;
  access_time: string;
  source_type: 'search' | 'browser' | 'file';
}

export interface Message {
  id: string;  // Unique ID for efficient Vue rendering (prevents re-renders on array changes)
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
  items?: StepItem[];  // Interleaved tools + thoughts for Manus-style rendering
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

// Deep Research types
export type DeepResearchStatus = 'pending' | 'awaiting_approval' | 'started' | 'completed' | 'cancelled';
export type DeepResearchQueryStatus = 'pending' | 'searching' | 'completed' | 'skipped' | 'failed';

export interface SearchResultItem {
  title: string;
  link: string;
  snippet: string;
}

export interface DeepResearchQuery {
  id: string;
  query: string;
  status: DeepResearchQueryStatus;
  result?: SearchResultItem[];
  started_at?: number;
  completed_at?: number;
}

export interface DeepResearchContent extends BaseContent {
  research_id: string;
  status: DeepResearchStatus;
  queries: DeepResearchQuery[];
  completed_count: number;
  total_count: number;
  auto_run: boolean;
}

// Skill Package types for skill delivery
export interface SkillPackageFile {
  path: string;
  content: string;
  size: number;
}

export interface SkillPackageFileTree {
  [key: string]: SkillPackageFileTree | {
    type: 'file';
    path: string;
    size: number;
  };
}

export interface SkillDeliveryContent extends BaseContent {
  package_id: string;
  name: string;
  description: string;
  version: string;
  icon: string;
  category: string;
  author?: string;
  file_tree: SkillPackageFileTree;
  files: SkillPackageFile[];
  file_id?: string;
  skill_id?: string;
}

// Wide Research types (parallel multi-source search)
export type WideResearchStatus = 'pending' | 'searching' | 'aggregating' | 'completed' | 'failed';

export interface WideResearchState {
  research_id: string;
  topic: string;
  status: WideResearchStatus;
  total_queries: number;
  completed_queries: number;
  sources_found: number;
  search_types: string[];
  current_query?: string;
  aggregation_strategy?: string;
  errors?: string[];
}

export interface WideResearchMiniState {
  research_id: string;
  status: WideResearchStatus;
  total_queries: number;
  completed_queries: number;
  sources_found: number;
  search_types: string[];
}
