import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator, Field

from app.domain.models.file import FileInfo
from app.domain.models.plan import Plan, Step
from app.domain.models.search import SearchResultItem
from app.domain.models.source_citation import SourceCitation
from app.domain.models.tool_call import ToolCallStatus


class ThoughtStatus(str, Enum):
    """Thought event status enum"""

    THINKING = "thinking"
    THOUGHT = "thought"
    CHAIN_COMPLETE = "chain_complete"


class PlanStatus(str, Enum):
    """Plan status enum"""

    CREATED = "created"
    UPDATED = "updated"
    COMPLETED = "completed"


class StepStatus(str, Enum):
    """Step status enum"""

    STARTED = "started"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class ToolStatus(str, Enum):
    """Tool status enum"""

    CALLING = "calling"
    CALLED = "called"


class BaseEvent(BaseModel):
    """Base class for agent events"""

    type: Literal[""] = ""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorEvent(BaseEvent):
    """Error event with structured error information.

    Provides enough context for the frontend to:
    - Display appropriate error messages to the user
    - Determine if the error is recoverable (show retry button)
    - Show specific guidance via retry_hint
    """

    type: Literal["error"] = "error"
    error: str
    error_type: str | None = None  # e.g. "token_limit", "timeout", "tool_execution", "llm_api"
    recoverable: bool = True  # Whether the user can retry/continue
    retry_hint: str | None = None  # User-facing guidance, e.g. "Try a simpler request"
    error_code: str | None = None  # Stable machine-readable code for client retry policy.
    error_category: str | None = None  # transport | timeout | validation | auth | upstream | domain
    severity: str = "error"  # info | warning | error | critical
    retry_after_ms: int | None = None  # Suggested retry delay in milliseconds.
    can_resume: bool = False  # Whether reconnect with event_id resume is expected to work.
    checkpoint_event_id: str | None = None  # Safe resume checkpoint when a gap/corruption is detected.
    details: dict[str, Any] | None = None  # Optional structured diagnostics payload.


class PlanEvent(BaseEvent):
    """Plan related events"""

    type: Literal["plan"] = "plan"
    plan: Plan
    status: PlanStatus
    step: Step | None = None
    phases: list[dict[str, Any]] | None = None  # Phase summaries for frontend


class BrowserToolContent(BaseModel):
    """Browser tool content"""

    screenshot: str | None = None  # Base64 encoded screenshot
    content: str | None = None  # Page content (text or HTML)


class SearchToolContent(BaseModel):
    """Search tool content"""

    results: list[SearchResultItem]


class ShellToolContent(BaseModel):
    """Shell tool content"""

    console: Any


class FileToolContent(BaseModel):
    """File tool content"""

    content: str


class McpToolContent(BaseModel):
    """MCP tool content"""

    result: Any


class BrowserAgentToolContent(BaseModel):
    """Browser agent tool content"""

    result: Any
    steps_taken: int = 0


class GitToolContent(BaseModel):
    """Git tool content for git operations"""

    operation: str  # clone, status, diff, log, branches
    output: str | None = None
    repo_path: str | None = None
    branch: str | None = None
    commits: list[dict[str, Any]] | None = None
    diff_content: str | None = None


class CodeExecutorToolContent(BaseModel):
    """Code executor tool content"""

    language: str  # python, javascript, bash, sql
    code: str | None = None
    output: str | None = None
    error: str | None = None
    exit_code: int | None = None
    execution_time_ms: int | None = None
    artifacts: list[dict[str, Any]] | None = None


class PlaywrightToolContent(BaseModel):
    """Playwright browser automation content"""

    browser_type: str | None = None  # chromium, firefox, webkit
    url: str | None = None
    screenshot: str | None = None  # Base64 encoded
    content: str | None = None


class TestRunnerToolContent(BaseModel):
    """Test runner tool content"""

    framework: str | None = None  # pytest, jest, etc.
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    output: str | None = None
    duration_ms: int | None = None


class SkillToolContent(BaseModel):
    """Skill tool content for skill operations"""

    skill_id: str | None = None
    skill_name: str | None = None
    operation: str  # invoke, create, list
    result: Any | None = None
    status: str | None = None


class ExportToolContent(BaseModel):
    """Export tool content"""

    format: str | None = None  # pdf, csv, json, etc.
    filename: str | None = None
    size_bytes: int | None = None
    path: str | None = None


class SlidesToToolContent(BaseModel):
    """Slides tool content"""

    title: str | None = None
    slide_count: int = 0
    format: str | None = None  # pptx, pdf, html
    path: str | None = None


class WorkspaceToolContent(BaseModel):
    """Workspace tool content"""

    action: str  # create, organize, list
    workspace_type: str | None = None
    files_count: int = 0
    structure: dict[str, Any] | None = None


class ScheduleToolContent(BaseModel):
    """Schedule tool content"""

    action: str  # create, list, cancel
    schedule_id: str | None = None
    schedule_time: str | None = None
    status: str | None = None


class DeepScanToolContent(BaseModel):
    """Deep scan analyzer tool content"""

    scan_type: str | None = None
    findings_count: int = 0
    summary: str | None = None
    details: list[dict[str, Any]] | None = None


class AgentModeToolContent(BaseModel):
    """Agent mode tool content"""

    mode: str  # discuss, agent, etc.
    previous_mode: str | None = None
    reason: str | None = None


class CodeDevToolContent(BaseModel):
    """Code dev tool content"""

    operation: str  # analyze, refactor, etc.
    file_path: str | None = None
    result: str | None = None
    suggestions: list[str] | None = None


class CanvasToolContent(BaseModel):
    """Canvas tool content for canvas operations"""

    operation: str  # create_project, add_element, modify_element, etc.
    project_id: str | None = None
    project_name: str | None = None
    element_count: int = 0
    image_urls: list[str] | None = None


class PlanToolContent(BaseModel):
    """Plan tool content"""

    operation: str  # create, update, get
    plan_id: str | None = None
    steps_count: int = 0


class RepoMapToolContent(BaseModel):
    """Repo map tool content"""

    repo_path: str | None = None
    files_count: int = 0
    structure: dict[str, Any] | None = None


class ChartToolContent(BaseModel):
    """Chart tool content for Plotly chart creation"""

    chart_type: str  # bar, line, scatter, pie, area, grouped_bar, stacked_bar, box
    title: str
    html_file_id: str | None = None  # MinIO file ID for interactive HTML
    png_file_id: str | None = None  # MinIO file ID for static PNG
    plotly_json_file_id: str | None = None  # MinIO file ID for Plotly JSON contract
    html_filename: str | None = None
    png_filename: str | None = None
    plotly_json_filename: str | None = None
    html_size: int | None = None  # HTML file size in bytes (for frontend display)
    plotly_json_size: int | None = None
    render_contract_version: str | None = None
    data_points: int = 0
    series_count: int = 0
    execution_time_ms: int | None = None
    error: str | None = None  # Sync/render error message for frontend display


class KnowledgeBaseToolContent(BaseModel):
    """Knowledge base tool content for query and list operations"""

    operation: str  # "query", "list"
    knowledge_base_id: str | None = None
    query: str | None = None
    results_count: int = 0
    query_time_ms: float = 0.0


ToolContent = (
    BrowserToolContent
    | SearchToolContent
    | ShellToolContent
    | FileToolContent
    | McpToolContent
    | BrowserAgentToolContent
    | GitToolContent
    | CodeExecutorToolContent
    | PlaywrightToolContent
    | TestRunnerToolContent
    | SkillToolContent
    | ExportToolContent
    | SlidesToToolContent
    | WorkspaceToolContent
    | ScheduleToolContent
    | DeepScanToolContent
    | AgentModeToolContent
    | CodeDevToolContent
    | CanvasToolContent
    | PlanToolContent
    | RepoMapToolContent
    | ChartToolContent
    | KnowledgeBaseToolContent
)


class ToolEvent(BaseEvent):
    """Tool related events"""

    type: Literal["tool"] = "tool"
    tool_call_id: str
    tool_name: str
    tool_content: ToolContent | None = None
    function_name: str
    function_args: dict[str, Any]
    status: ToolStatus
    function_result: Any | None = None

    # Action/observation metadata (OpenHands-style)
    action_type: str | None = None
    observation_type: str | None = None
    command: str | None = None
    cwd: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    file_path: str | None = None
    diff: str | None = None
    runtime_status: str | None = None

    # Security/confirmation metadata
    security_risk: str | None = None
    security_reason: str | None = None
    security_suggestions: list[str] | None = None
    confirmation_state: str | None = None

    # Standardized envelope status (more granular than ToolStatus)
    call_status: ToolCallStatus | None = None

    # Timeline tracking fields
    sequence_number: int | None = None  # Position in session timeline
    started_at: datetime | None = None  # When tool execution started
    completed_at: datetime | None = None  # When tool execution completed
    duration_ms: float | None = None  # Execution duration in milliseconds (stored as float for precision)

    # Enhanced command display (Phase 3)
    display_command: str | None = None  # "Searching 'machine learning'"
    command_category: str | None = None  # "search", "browse", "file", "shell", "code"
    command_summary: str | None = None  # Short summary for UI badges


class ToolProgressEvent(BaseEvent):
    """Progress event for long-running tool operations.

    Provides real-time progress updates during tool execution,
    enabling better UX for operations like browser navigation,
    file processing, or shell commands.
    """

    type: Literal["tool_progress"] = "tool_progress"
    tool_call_id: str  # Links to parent ToolEvent
    tool_name: str
    function_name: str

    # Progress tracking
    progress_percent: int  # 0-100
    current_step: str  # Human-readable current action
    steps_completed: int = 0
    steps_total: int | None = None  # None if unknown

    # Timing
    elapsed_ms: float = 0
    estimated_remaining_ms: float | None = None

    # Checkpoint info for resume capability
    checkpoint_id: str | None = None  # ID for resuming from this point
    checkpoint_data: dict[str, Any] | None = None  # Serialized checkpoint state


class TitleEvent(BaseEvent):
    """Title event"""

    type: Literal["title"] = "title"
    title: str


class PhaseStatus(str, Enum):
    """Phase lifecycle status enum"""

    STARTED = "started"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PhaseEvent(BaseEvent):
    """Phase lifecycle event for structured agent flow."""

    type: Literal["phase"] = "phase"
    phase_id: str
    phase_type: str  # PhaseType value
    label: str
    status: PhaseStatus
    order: int = 0
    icon: str = ""
    color: str = ""
    total_phases: int = 0
    skip_reason: str | None = None


class StepEvent(BaseEvent):
    """Step related events"""

    type: Literal["step"] = "step"
    step: Step
    status: StepStatus
    phase_id: str | None = None  # Parent phase ID
    step_type: str | None = None  # StepType value


class MessageEvent(BaseEvent):
    """Message event"""

    type: Literal["message"] = "message"
    role: Literal["user", "assistant"] = "assistant"
    message: str
    attachments: list[FileInfo] | None = None
    skills: list[str] | None = None  # Skill IDs enabled for this message
    thinking_mode: str | None = None  # Model tier override: 'auto', 'fast', 'deep_think'
    # Follow-up context from suggestion clicks
    follow_up_selected_suggestion: str | None = None  # The suggestion text that was clicked
    follow_up_anchor_event_id: str | None = None  # Event ID to anchor context to
    follow_up_source: str | None = None  # Source of follow-up (e.g., "suggestion_click")


class DoneEvent(BaseEvent):
    """Done event"""

    type: Literal["done"] = "done"


class WaitEvent(BaseEvent):
    """Wait event"""

    type: Literal["wait"] = "wait"
    wait_reason: str | None = None  # user_input|captcha|login|2fa|payment|verification|other
    suggest_user_takeover: str | None = None  # none|browser


class KnowledgeEvent(BaseEvent):
    """Knowledge event from the knowledge module"""

    type: Literal["knowledge"] = "knowledge"
    scope: str
    content: str


class DatasourceEvent(BaseEvent):
    """Datasource event from the datasource module"""

    type: Literal["datasource"] = "datasource"
    api_name: str
    documentation: str


class IdleEvent(BaseEvent):
    """Idle event when agent enters standby state"""

    type: Literal["idle"] = "idle"
    reason: str | None = None


class MCPHealthEvent(BaseEvent):
    """MCP server health status event"""

    type: Literal["mcp_health"] = "mcp_health"
    server_name: str
    healthy: bool
    error: str | None = None
    tools_available: int = 0


class ModeChangeEvent(BaseEvent):
    """Mode change event when switching between discuss and agent modes"""

    type: Literal["mode_change"] = "mode_change"
    mode: str  # "discuss" or "agent"
    reason: str | None = None  # Reason for mode switch


class SuggestionEvent(BaseEvent):
    """Suggestion event for end-of-response suggestions"""

    type: Literal["suggestion"] = "suggestion"
    suggestions: list[str]  # List of 2-3 contextual suggestions
    source: str | None = None  # Source of suggestions: "completion", "discuss"
    anchor_event_id: str | None = None  # Event ID to anchor context to (report/message)
    anchor_excerpt: str | None = None  # Brief excerpt from anchored content


class PlanningPhase(str, Enum):
    """Planning phase enum for progressive disclosure"""

    RECEIVED = "received"  # Message received, starting to process
    ANALYZING = "analyzing"  # Analyzing task complexity
    PLANNING = "planning"  # Generating plan with LLM
    FINALIZING = "finalizing"  # Parsing and validating plan
    HEARTBEAT = "heartbeat"  # Keep-alive during long agent operations (no UI change)
    WAITING = "waiting"  # Long-running execution wait beacon (non-transport heartbeat)


class ProgressEvent(BaseEvent):
    """Progress event for instant feedback during planning/execution.

    Provides immediate visual feedback to users while LLM is working.
    Enables progressive disclosure UX pattern.
    """

    type: Literal["progress"] = "progress"
    phase: PlanningPhase
    message: str  # User-friendly status message
    estimated_steps: int | None = None  # Estimated number of steps (if known)
    progress_percent: int | None = None  # 0-100 progress indicator
    estimated_duration_seconds: int | None = None  # Rough time estimate for the task
    complexity_category: str | None = None  # "simple", "medium", or "complex"
    wait_elapsed_seconds: int | None = None  # Elapsed wait time for long-running execution
    wait_stage: str | None = None  # execution_wait | verification_wait | tool_wait


class ComprehensionEvent(BaseEvent):
    """Event emitted when agent comprehends a long/complex message.

    Used to show the user that the agent has understood their requirements
    before creating tasks.
    """

    type: Literal["comprehension"] = "comprehension"
    original_length: int  # Length of original message
    summary: str  # Agent's summarized understanding
    key_requirements: list[str] | None = None  # Extracted key requirements
    complexity_score: float | None = None  # 0-1 complexity assessment


class TaskRecreationEvent(BaseEvent):
    """Event emitted when tasks are recreated based on new understanding.

    Allows the agent to reset and recreate tasks after comprehending
    a long message or receiving clarifying information.
    """

    type: Literal["task_recreation"] = "task_recreation"
    reason: str  # Why tasks were recreated
    previous_step_count: int  # Number of steps before recreation
    new_step_count: int  # Number of steps after recreation
    preserved_findings: int  # Number of findings preserved from previous work


class ReportEvent(BaseEvent):
    """Report event for displaying task completion reports in Notion-like markdown view"""

    type: Literal["report"] = "report"
    id: str  # Unique ID for the report (named 'id' for frontend compatibility)
    title: str  # Report title
    content: str  # Markdown content of the report
    attachments: list[FileInfo] | None = None  # Associated files
    sources: list[SourceCitation] | None = None  # Bibliography/references


class SkillPackageFileData(BaseModel):
    """File data within a skill delivery event"""

    path: str  # Relative path: "SKILL.md", "scripts/seo_analyzer.py"
    content: str  # File content
    size: int  # Size in bytes


class SkillDeliveryEvent(BaseEvent):
    """Skill delivery event for displaying skill packages in chat.

    Emitted when a skill package is created and ready for user download/install.
    The frontend displays a skill card with file tree and preview capabilities.
    """

    type: Literal["skill_delivery"] = "skill_delivery"
    package_id: str  # Unique package ID
    name: str  # Skill name
    description: str  # Skill description
    version: str = "1.0.0"
    icon: str = "puzzle"  # Lucide icon name
    category: str = "custom"
    author: str | None = None
    file_tree: dict[str, Any] = Field(default_factory=dict)  # Hierarchical structure for UI
    files: list[SkillPackageFileData] = Field(default_factory=list)  # All files in package
    file_id: str | None = None  # GridFS file ID for download
    skill_id: str | None = None  # DB skill ID if also saved to database


class SkillActivationEvent(BaseEvent):
    """Skill activation event emitted when skills are loaded for a message.

    Helps with debugging skill activation issues by showing which skills
    are active and what tools are available.
    """

    type: Literal["skill_activation"] = "skill_activation"
    skill_ids: list[str] = Field(default_factory=list)  # Active skill IDs
    skill_names: list[str] = Field(default_factory=list)  # Human-readable names
    tool_restrictions: list[str] | None = None  # Restricted tool list (if any)
    prompt_chars: int = 0  # Size of injected skill context
    activation_sources: dict[str, list[str]] = Field(default_factory=dict)  # skill_id -> activation sources
    command_skill_id: str | None = None  # Skill activated via slash command, when present
    auto_trigger_enabled: bool = False  # Whether auto-trigger policy was enabled for this message


class StreamEvent(BaseEvent):
    """Stream event for real-time LLM response streaming"""

    type: Literal["stream"] = "stream"
    content: str  # Streamed content chunk
    is_final: bool = False  # Whether this is the final chunk
    phase: str = "thinking"  # "thinking" for planning, "summarizing" for report generation


class ToolStreamEvent(BaseEvent):
    """Streams partial tool content during LLM generation.

    Emitted while the LLM is still generating tool call arguments,
    allowing the frontend to show progressive content (e.g., file
    content appearing character-by-character in the editor view).

    The normal ToolEvent(status=CALLING) is still emitted once the
    full tool call is ready — this event provides early previews.
    """

    type: Literal["tool_stream"] = "tool_stream"
    tool_call_id: str
    tool_name: str
    function_name: str
    partial_content: str  # Accumulated content extracted so far
    content_type: str = "text"  # "text" | "code" | "json"
    is_final: bool = False  # True when the full content is available


class VerificationStatus(str, Enum):
    """Verification status enum"""

    STARTED = "started"
    PASSED = "passed"
    REVISION_NEEDED = "revision_needed"
    FAILED = "failed"


class VerificationEvent(BaseEvent):
    """Verification event when verifying a plan before execution"""

    type: Literal["verification"] = "verification"
    status: VerificationStatus
    verdict: str | None = None  # "pass", "revise", "fail"
    confidence: float | None = None
    summary: str | None = None
    revision_feedback: str | None = None  # Feedback for replanning


class ReflectionStatus(str, Enum):
    """Reflection status enum"""

    TRIGGERED = "triggered"
    COMPLETED = "completed"


class ReflectionEvent(BaseEvent):
    """Reflection event during execution"""

    type: Literal["reflection"] = "reflection"
    status: ReflectionStatus
    decision: str | None = None  # "continue", "adjust", "replan", "escalate", "abort"
    confidence: float | None = None
    summary: str | None = None
    trigger_reason: str | None = None  # Why reflection was triggered


class PathEvent(BaseEvent):
    """Path event for Tree-of-Thoughts multi-path exploration"""

    type: Literal["path"] = "path"
    path_id: str
    action: str  # "created", "exploring", "completed", "abandoned", "selected"
    score: float | None = None
    description: str | None = None


class MultiTaskEvent(BaseEvent):
    """Multi-task challenge progress event"""

    type: Literal["multi_task"] = "multi_task"
    challenge_id: str
    action: str  # "started", "task_switching", "task_completed", "challenge_completed"
    current_task_index: int
    total_tasks: int
    current_task: str | None = None  # Task description
    progress_percentage: float = 0.0
    elapsed_time_seconds: float | None = None


class WorkspaceEvent(BaseEvent):
    """Workspace structure and organization event.

    Emitted during Deep Research to notify the frontend of workspace lifecycle:
    - "initialized": workspace directories created in sandbox
    - "deliverables_ready": all deliverable files cataloged at session end
    """

    type: Literal["workspace"] = "workspace"
    action: str  # "initialized", "deliverables_ready"
    workspace_type: str | None = None  # "research", "code_project", "data_analysis"
    workspace_path: str | None = None  # absolute path in sandbox
    structure: dict[str, str] | None = None  # folder_name -> purpose
    files_organized: int = 0
    deliverables_count: int = 0
    manifest_path: str | None = None


class BudgetEvent(BaseEvent):
    """Budget threshold and exhaustion events"""

    type: Literal["budget"] = "budget"
    action: str  # "warning", "exhausted", "resumed"
    budget_limit: float  # USD
    consumed: float  # USD
    remaining: float  # USD
    percentage_used: float
    warning_threshold: float = 0.8
    session_paused: bool = False


class PhaseTransitionEvent(BaseEvent):
    """Phased research progress transition event."""

    type: Literal["phase_transition"] = "phase_transition"
    phase: str
    label: str | None = None
    research_id: str | None = None
    source: str | None = None  # wide_research | session


class CheckpointSavedEvent(BaseEvent):
    """Event emitted when a phased research checkpoint is persisted."""

    type: Literal["checkpoint_saved"] = "checkpoint_saved"
    phase: str
    research_id: str | None = None
    notes_preview: str | None = None
    source_count: int | None = None


class WideResearchStatus(str, Enum):
    """Wide research status enum for parallel multi-source search"""

    PENDING = "pending"
    SEARCHING = "searching"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class WideResearchEvent(BaseEvent):
    """Wide research progress event for parallel multi-source search.

    Emitted during wide_research execution to provide frontend progress updates.
    """

    type: Literal["wide_research"] = "wide_research"
    research_id: str
    topic: str
    status: WideResearchStatus
    total_queries: int
    completed_queries: int = 0
    sources_found: int = 0
    search_types: list[str] = Field(default_factory=list)
    current_query: str | None = None
    errors: list[str] = Field(default_factory=list)


class LegacyDeepResearchEvent(BaseEvent):
    """Legacy event type for backward compatibility with old sessions.

    DeepResearchEvent was removed but MongoDB may still contain these events.
    This stub allows SessionDocument deserialization to succeed without crashing.
    """

    type: Literal["deep_research"] = "deep_research"
    research_id: str = ""
    status: str = ""
    total_queries: int = 0
    completed_queries: int = 0
    queries: list[dict[str, Any]] = Field(default_factory=list)
    auto_run: bool = False


class ThoughtEvent(BaseEvent):
    """Thought event for Chain-of-Thought reasoning.

    Exposes the agent's reasoning process for transparency and debugging.
    """

    type: Literal["thought"] = "thought"
    status: ThoughtStatus
    thought_type: str | None = None  # observation, analysis, hypothesis, etc.
    content: str | None = None  # The thought content
    confidence: float | None = None  # 0.0 to 1.0
    step_name: str | None = None  # Name of the reasoning step
    chain_id: str | None = None  # ID of the thought chain
    is_final: bool = False  # Whether this completes the chain


class ConfidenceEvent(BaseEvent):
    """Confidence calibration event for decision transparency.

    Reports calibrated confidence levels for decisions and actions.
    """

    type: Literal["confidence"] = "confidence"
    decision: str  # The decision or action
    confidence: float  # Calibrated confidence 0.0-1.0
    level: str  # high, medium, low
    action_recommendation: str  # proceed, verify, ask_user
    supporting_factors: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)


class FlowSelectionEvent(BaseEvent):
    """Emitted when a flow engine is selected for a session.

    Enables observability of which flow is used, with what model,
    and why it was selected.
    """

    type: Literal["flow_selection"] = "flow_selection"
    flow_mode: str  # FlowMode value: plan_act, coordinator
    model: str | None = None  # LLM model identifier
    session_id: str | None = None
    reason: str | None = None


class CanvasUpdateEvent(BaseEvent):
    """Canvas update event emitted when agent modifies a canvas project."""

    type: Literal["canvas_update"] = "canvas_update"
    project_id: str
    operation: str  # create_project, add_element, modify_element, etc.
    element_count: int = 0
    project_name: str | None = None


class FlowTransitionEvent(BaseEvent):
    """Emitted when the workflow transitions between states.

    Enables full observability of flow lifecycle and state changes.
    """

    type: Literal["flow_transition"] = "flow_transition"
    from_state: str  # Previous AgentStatus value
    to_state: str  # New AgentStatus value
    reason: str | None = None  # Why the transition happened
    step_id: str | None = None  # Current step ID if applicable
    elapsed_ms: float | None = None  # Time spent in previous state


class ResearchModeEvent(BaseEvent):
    """Emitted at the start of a session flow to indicate the active research mode.

    Allows the frontend to adapt its layout (e.g., auto-open browser panel
    for deep_research, hide it for fast_search).
    """

    type: Literal["research_mode"] = "research_mode"
    research_mode: str  # "fast_search" or "deep_research"


# Discriminated union on 'type' field for efficient Pydantic v2 validation
# Using Union[] syntax required for Annotated discriminator pattern
AgentEvent = Annotated[
    Union[  # noqa: UP007
        ErrorEvent,
        PlanEvent,
        ToolEvent,
        ToolStreamEvent,
        ToolProgressEvent,
        StepEvent,
        MessageEvent,
        DoneEvent,
        TitleEvent,
        WaitEvent,
        KnowledgeEvent,
        DatasourceEvent,
        IdleEvent,
        MCPHealthEvent,
        ModeChangeEvent,
        SuggestionEvent,
        ReportEvent,
        SkillDeliveryEvent,
        SkillActivationEvent,
        StreamEvent,
        VerificationEvent,
        ReflectionEvent,
        PathEvent,
        MultiTaskEvent,
        WorkspaceEvent,
        BudgetEvent,
        ProgressEvent,
        ComprehensionEvent,
        TaskRecreationEvent,
        PhaseTransitionEvent,
        CheckpointSavedEvent,
        WideResearchEvent,
        LegacyDeepResearchEvent,
        ThoughtEvent,
        ConfidenceEvent,
        CanvasUpdateEvent,
        FlowSelectionEvent,
        FlowTransitionEvent,
        ResearchModeEvent,
        PhaseEvent,
    ],
    Discriminator("type"),
]
