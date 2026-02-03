import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.models.file import FileInfo
from app.domain.models.plan import Plan, Step
from app.domain.models.search import SearchResultItem
from app.domain.models.source_citation import SourceCitation


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class ErrorEvent(BaseEvent):
    """Error event"""

    type: Literal["error"] = "error"
    error: str


class PlanEvent(BaseEvent):
    """Plan related events"""

    type: Literal["plan"] = "plan"
    plan: Plan
    status: PlanStatus
    step: Step | None = None


class BrowserToolContent(BaseModel):
    """Browser tool content"""

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


ToolContent = (
    BrowserToolContent
    | SearchToolContent
    | ShellToolContent
    | FileToolContent
    | McpToolContent
    | BrowserAgentToolContent
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


class StepEvent(BaseEvent):
    """Step related events"""

    type: Literal["step"] = "step"
    step: Step
    status: StepStatus


class MessageEvent(BaseEvent):
    """Message event"""

    type: Literal["message"] = "message"
    role: Literal["user", "assistant"] = "assistant"
    message: str
    attachments: list[FileInfo] | None = None
    skills: list[str] | None = None  # Skill IDs enabled for this message
    deep_research: bool | None = None  # Enable deep research mode (parallel wide_research)


class DoneEvent(BaseEvent):
    """Done event"""

    type: Literal["done"] = "done"


class WaitEvent(BaseEvent):
    """Wait event"""

    type: Literal["wait"] = "wait"


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


class PlanningPhase(str, Enum):
    """Planning phase enum for progressive disclosure"""

    RECEIVED = "received"  # Message received, starting to process
    ANALYZING = "analyzing"  # Analyzing task complexity
    PLANNING = "planning"  # Generating plan with LLM
    FINALIZING = "finalizing"  # Parsing and validating plan


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


class StreamEvent(BaseEvent):
    """Stream event for real-time LLM response streaming"""

    type: Literal["stream"] = "stream"
    content: str  # Streamed content chunk
    is_final: bool = False  # Whether this is the final chunk


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
    """Workspace structure and organization event"""

    type: Literal["workspace"] = "workspace"
    action: str  # "initialized", "organized", "validated", "deliverable_added"
    workspace_type: str | None = None  # "research", "code_project", "data_analysis"
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


class DeepResearchStatus(str, Enum):
    """Deep research status enum"""

    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    STARTED = "started"
    QUERY_STARTED = "query_started"
    QUERY_COMPLETED = "query_completed"
    QUERY_SKIPPED = "query_skipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeepResearchQueryStatus(str, Enum):
    """Individual query status enum"""

    PENDING = "pending"
    SEARCHING = "searching"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class WideResearchStatus(str, Enum):
    """Wide research status enum for parallel multi-source search"""

    PENDING = "pending"
    SEARCHING = "searching"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class DeepResearchQueryData(BaseModel):
    """Individual research query data"""

    id: str
    query: str
    status: DeepResearchQueryStatus = DeepResearchQueryStatus.PENDING
    result: list[SearchResultItem] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DeepResearchEvent(BaseEvent):
    """Deep research progress event for parallel search execution"""

    type: Literal["deep_research"] = "deep_research"
    research_id: str  # Unique research session ID
    status: DeepResearchStatus
    total_queries: int
    completed_queries: int = 0
    queries: list[DeepResearchQueryData] = Field(default_factory=list)
    auto_run: bool = False


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


AgentEvent = (
    ErrorEvent
    | PlanEvent
    | ToolEvent
    | StepEvent
    | MessageEvent
    | DoneEvent
    | TitleEvent
    | WaitEvent
    | KnowledgeEvent
    | DatasourceEvent
    | IdleEvent
    | MCPHealthEvent
    | ModeChangeEvent
    | SuggestionEvent
    | ReportEvent
    | SkillDeliveryEvent
    | SkillActivationEvent
    | StreamEvent
    | VerificationEvent
    | ReflectionEvent
    | PathEvent
    | MultiTaskEvent
    | WorkspaceEvent
    | BudgetEvent
    | ProgressEvent
    | DeepResearchEvent
    | WideResearchEvent
    | ThoughtEvent
    | ConfidenceEvent
)
