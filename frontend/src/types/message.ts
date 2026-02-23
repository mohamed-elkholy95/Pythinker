import type { FileInfo } from '../api/file';
import type { ToolContentPayload } from './toolContent';

export type MessageType = "user" | "assistant" | "tool" | "step" | "attachments" | "report" | "skill_delivery" | "thought" | "phase";

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
  event_id?: string;  // Event ID from SSE events (for follow-up context anchoring)
}

export interface MessageContent extends BaseContent {
  content: string;
  /** When true, user upgraded this message via "Use Agent Mode" CTA; show compact badge */
  agentModeUpgrade?: boolean;
}

export interface ToolContent extends BaseContent {
  tool_call_id: string;
  name: string;
  function: string;
  args: Record<string, unknown>;
  content?: ToolContentPayload;
  status: "calling" | "called";
  // Display metadata (Pythinker-style human-readable descriptions)
  display_command?: string;      // Full human-readable description: "Search for OpenRouter free tier LLM models"
  command_category?: string;     // Category: "search", "browse", "file", "shell", etc.
  command_summary?: string;      // Short summary for badges
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
  // Streaming preview content (from tool_stream events)
  streaming_content?: string;
  streaming_content_type?: string;
}

export interface StepContent extends BaseContent {
  id: string;
  description: string;
  status: 'pending' | 'started' | 'running' | 'completed' | 'failed' | 'blocked' | 'skipped';
  tools: ToolContent[];
  phase_id?: string | null;  // When set, step is in plan-act flow (hide fast-search inline UI)
  step_type?: string | null;
  items?: StepItem[];  // Interleaved tools + thoughts for Pythinker-style rendering
  sub_stage_history?: string[];  // Previous descriptions for progressive finalization steps
}

export interface PhaseContent extends BaseContent {
  phase_id: string;
  phase_type: string;
  label: string;
  status: 'started' | 'completed' | 'skipped';
  order?: number;
  icon?: string;
  color?: string;
  total_phases?: number;
  skip_reason?: string;
  steps: StepContent[];
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

export interface ResearchCheckpointSummary {
  phase: string;
  notes_preview?: string;
  source_count?: number;
  timestamp: number;
}

export interface ResearchReflectionSummary {
  learned: string;
  next_step?: string;
  timestamp: number;
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
  phase?: string;
  phase_label?: string;
}

export interface WideResearchMiniState {
  research_id: string;
  status: WideResearchStatus;
  total_queries: number;
  completed_queries: number;
  sources_found: number;
  search_types: string[];
}
