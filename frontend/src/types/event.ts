import type { FileInfo } from '../api/file';
import type { SourceCitation, DeepResearchQuery, DeepResearchStatus, SkillPackageFile, SkillPackageFileTree } from './message';
import type { ToolContentPayload } from './toolContent';

export type AgentSSEEvent = {
  event: 'tool' | 'step' | 'message' | 'error' | 'done' | 'title' | 'wait' | 'plan' | 'attachments' | 'mode_change' | 'suggestion' | 'report' | 'stream' | 'progress' | 'deep_research' | 'wide_research' | 'skill_delivery' | 'skill_activation' | 'thought';
  data: ToolEventData | StepEventData | MessageEventData | ErrorEventData | DoneEventData | TitleEventData | WaitEventData | PlanEventData | ModeChangeEventData | SuggestionEventData | ReportEventData | StreamEventData | ProgressEventData | DeepResearchEventData | WideResearchEventData | SkillDeliveryEventData | SkillActivationEventData | ThoughtEventData;
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
  args: Record<string, unknown>;
  content?: ToolContentPayload;
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
  sources?: SourceCitation[];
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

export interface DeepResearchEventData extends BaseEventData {
  research_id: string;
  status: DeepResearchStatus;
  total_queries: number;
  completed_queries: number;
  queries: DeepResearchQuery[];
  auto_run: boolean;
}

// Wide Research types (parallel multi-source search)
export type WideResearchStatus = 'pending' | 'searching' | 'aggregating' | 'completed' | 'failed';

export interface WideResearchEventData extends BaseEventData {
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

export interface SkillDeliveryEventData extends BaseEventData {
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

export interface SkillActivationEventData extends BaseEventData {
  skill_ids: string[];
  skill_names: string[];
  tool_restrictions?: string[];
  prompt_chars: number;
}

export interface ThoughtEventData extends BaseEventData {
  status: 'thinking' | 'thought' | 'chain_complete';
  thought_type?: 'observation' | 'analysis' | 'hypothesis' | 'conclusion';
  content?: string;
  confidence?: number;
  step_name?: string;
  chain_id?: string;
  is_final?: boolean;
}
