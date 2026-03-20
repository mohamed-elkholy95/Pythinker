import type { FileInfo } from '../api/file';
import type { SourceCitation, SkillPackageFile, SkillPackageFileTree } from './message';
import type { ToolContentPayload } from './toolContent';

/**
 * Follow-up context from suggestion clicks
 */
export interface FollowUp {
  selected_suggestion: string;  // The suggestion text that was clicked
  anchor_event_id: string;      // Event ID to anchor context to
  source: string;               // Source of follow-up (e.g., "suggestion_click")
}

/** All SSE event type strings recognised by the frontend. */
export type EventType = AgentSSEEvent['event']

export type AgentSSEEvent = {
  event:
    | 'tool'
    | 'tool_stream'
    | 'tool_progress'
    | 'step'
    | 'message'
    | 'error'
    | 'done'
    | 'title'
    | 'wait'
    | 'plan'
    | 'attachments'
    | 'mode_change'
    | 'suggestion'
    | 'report'
    | 'stream'
    | 'progress'
    | 'wide_research'
    | 'deep_research'
    | 'phase_transition'
    | 'checkpoint_saved'
    | 'skill_delivery'
    | 'skill_activation'
    | 'thought'
    | 'canvas_update'
    | 'workspace'
    | 'research_mode'
    | 'flow_selection'
    | 'flow_transition'
    | 'verification'
    | 'reflection'
    | 'partial_result'
    | 'phase'
    | 'eval_metrics'
    | 'mcp_health';
  data:
    | ToolEventData
    | ToolStreamEventData
    | ToolProgressEventData
    | StepEventData
    | MessageEventData
    | ErrorEventData
    | DoneEventData
    | TitleEventData
    | WaitEventData
    | PlanEventData
    | ModeChangeEventData
    | SuggestionEventData
    | ReportEventData
    | StreamEventData
    | ProgressEventData
    | WideResearchEventData
    | DeepResearchEventData
    | PhaseTransitionEventData
    | CheckpointSavedEventData
    | SkillDeliveryEventData
    | SkillActivationEventData
    | ThoughtEventData
    | CanvasUpdateEventData
    | WorkspaceEventData
    | AgentPhaseEventData
    | ResearchModeEventData
    | FlowSelectionEventData
    | FlowTransitionEventData
    | VerificationEventData
    | ReflectionEventData
    | PartialResultEventData
    | EvalMetricsEventData;
}

export interface BaseEventData {
  event_id: string;
  timestamp: number;
}

export interface ToolStreamEventData extends BaseEventData {
  tool_call_id: string;
  tool_name: string;
  function_name: string;

  // Streaming content
  partial_content: string;           // Incremental chunk
  accumulated_content?: string;      // Full content so far (for late joiners)
  content_type: string;

  // Metadata
  is_final: boolean;
  chunk_index?: number;              // Sequential chunk number
  total_bytes?: number;              // Accumulated byte count
  language?: string;                 // For code: 'python', 'javascript', etc.

  // Progress tracking
  progress_percent?: number;         // 0-100 for known-length operations
  elapsed_ms?: number;               // Execution time so far
}

export interface ToolProgressEventData extends BaseEventData {
  tool_call_id: string;
  tool_name: string;
  function_name: string;
  progress_percent: number;         // 0-100
  current_step: string;
  steps_completed: number;
  steps_total?: number;
  elapsed_ms: number;
  estimated_remaining_ms?: number;
  checkpoint_data?: Record<string, unknown> | null;
}

export interface ToolEventData extends BaseEventData {
  tool_call_id: string;
  name: string;
  status: "calling" | "running" | "called";
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
  // Terminal session name (optional, from backend agent)
  session_name?: string;
}

export interface StepEventData extends BaseEventData {
  status: "pending" | "started" | "running" | "completed" | "failed" | "blocked" | "skipped"
  id: string
  description: string
  phase_id?: string | null  // Parent phase ID; when set, step is in plan-act flow (hide fast-search UI)
  step_type?: string | null
}

export interface MessageEventData extends BaseEventData {
  content: string;
  role: "user" | "assistant";
  attachments: FileInfo[];
  // Follow-up context from suggestion clicks
  follow_up_selected_suggestion?: string;
  follow_up_anchor_event_id?: string;
  follow_up_source?: string;
}

export interface ErrorEventData extends BaseEventData {
  error: string;
  error_type?: string;     // "timeout" | "token_limit" | "tool_execution" | "llm_api"
  recoverable?: boolean;   // Whether retry makes sense
  retry_hint?: string;     // User-facing recovery guidance
  error_code?: string;     // Stable machine-readable code
  error_category?: string; // transport | timeout | validation | auth | upstream | domain
  severity?: 'info' | 'warning' | 'error' | 'critical' | string;
  retry_after_ms?: number;
  can_resume?: boolean;
  checkpoint_event_id?: string;
  details?: Record<string, unknown>;
}

export interface DoneEventData extends BaseEventData {
}

export interface WaitEventData extends BaseEventData {
  wait_reason?: 'user_input' | 'captcha' | 'login' | '2fa' | 'payment' | 'verification' | 'other' | string;
  suggest_user_takeover?: 'none' | 'browser' | string;
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
  source?: string;                // Source of suggestions: "completion", "discuss"
  anchor_event_id?: string;       // Event ID to anchor context to (report/message)
  anchor_excerpt?: string;        // Brief excerpt from anchored content
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
  phase?: string;
  phase_metadata?: Record<string, unknown>;
}

export type PlanningPhase = 'received' | 'analyzing' | 'planning' | 'verifying' | 'executing_setup' | 'finalizing' | 'waiting';

export interface ProgressEventData extends BaseEventData {
  phase: PlanningPhase;
  message: string;
  estimated_steps?: number;
  progress_percent?: number;
  estimated_duration_seconds?: number;
  complexity_category?: 'simple' | 'medium' | 'complex';
  wait_elapsed_seconds?: number;
  wait_stage?: 'execution_wait' | 'verification_wait' | 'tool_wait' | string;
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

export type DeepResearchStatus = 'started' | 'running' | 'waiting' | 'completed' | 'failed' | string;

export interface DeepResearchEventData extends BaseEventData {
  research_id: string;
  status: DeepResearchStatus;
  total_queries?: number;
  completed_queries?: number;
  queries?: string[];
  auto_run?: boolean;
}

export type ResearchWorkflowPhase =
  | 'planning'
  | 'phase_1'
  | 'phase_2'
  | 'phase_3'
  | 'executing'
  | 'summarizing'
  | 'compilation'
  | 'completed'
  | string;

export interface PhaseTransitionEventData extends BaseEventData {
  phase: ResearchWorkflowPhase;
  label?: string;
  research_id?: string;
  source?: 'wide_research' | 'deep_research' | 'session';
}

export interface CheckpointSavedEventData extends BaseEventData {
  phase: ResearchWorkflowPhase;
  research_id?: string;
  notes_preview?: string;
  source_count?: number;
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

export interface CanvasUpdateEventData extends BaseEventData {
  project_id: string;
  session_id?: string;
  operation: string;
  element_count: number;
  project_name?: string;
  version: number;
  changed_element_ids?: string[];
  source?: 'agent' | 'manual' | 'system';
}

export interface WorkspaceEventData extends BaseEventData {
  action: 'initialized' | 'deliverables_ready';
  workspace_type?: string;
  workspace_path?: string;
  structure?: Record<string, string>;
  files_organized?: number;
  deliverables_count?: number;
}

export interface AgentPhaseEventData extends BaseEventData {
  phase_id: string;
  phase_type: string;
  label: string;
  status: 'started' | 'completed' | 'skipped';
  order?: number;
  icon?: string;
  color?: string;
  total_phases?: number;
  skip_reason?: string;
}

export interface ResearchModeEventData extends BaseEventData {
  research_mode: string;
}

// ── Observability events (flow lifecycle, verification) ──────────────

export interface FlowSelectionEventData extends BaseEventData {
  flow_mode: string;
  model?: string;
  session_id?: string;
  reason?: string;
}

export interface FlowTransitionEventData extends BaseEventData {
  from_state: string;
  to_state: string;
  reason?: string;
  step_id?: string;
  elapsed_ms?: number;
}

export type VerificationVerdict = 'pass' | 'revise' | 'fail';

export interface VerificationEventData extends BaseEventData {
  status: string;
  verdict?: VerificationVerdict;
  confidence?: number;
  summary?: string;
  revision_feedback?: string;
}

// ── Reflection events (meta-cognitive reflection during execution) ────

export type ReflectionDecision = 'continue' | 'adjust' | 'replan' | 'escalate' | 'abort';

export interface ReflectionEventData extends BaseEventData {
  status: 'triggered' | 'completed';
  decision?: ReflectionDecision;
  confidence?: number;
  summary?: string;
  trigger_reason?: string;
}

// ── Partial result events (provisional findings during execution) ─────

export interface PartialResultEventData extends BaseEventData {
  type: 'partial_result';
  step_index: number;
  step_title: string;
  headline: string;
  sources_count: number;
}

// ── Evaluation metrics events (observability) ─────────────────────────

export interface EvalMetricsEventData extends BaseEventData {
  metrics: Record<string, unknown>;
  hallucination_score: number;
  passed: boolean;
}
