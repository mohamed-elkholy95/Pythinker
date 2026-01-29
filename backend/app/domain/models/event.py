import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from app.domain.models.file import FileInfo
from app.domain.models.plan import Plan, Step
from app.domain.models.search import SearchResultItem
from app.domain.models.source_citation import SourceCitation


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

ToolContent = Union[
    BrowserToolContent,
    SearchToolContent,
    ShellToolContent,
    FileToolContent,
    McpToolContent,
    BrowserAgentToolContent
]

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
    RECEIVED = "received"        # Message received, starting to process
    ANALYZING = "analyzing"      # Analyzing task complexity
    PLANNING = "planning"        # Generating plan with LLM
    FINALIZING = "finalizing"    # Parsing and validating plan


class ProgressEvent(BaseEvent):
    """Progress event for instant feedback during planning/execution.

    Provides immediate visual feedback to users while LLM is working.
    Enables progressive disclosure UX pattern.
    """
    type: Literal["progress"] = "progress"
    phase: PlanningPhase
    message: str                           # User-friendly status message
    estimated_steps: int | None = None  # Estimated number of steps (if known)
    progress_percent: int | None = None # 0-100 progress indicator


class ReportEvent(BaseEvent):
    """Report event for displaying task completion reports in Notion-like markdown view"""
    type: Literal["report"] = "report"
    id: str  # Unique ID for the report (named 'id' for frontend compatibility)
    title: str  # Report title
    content: str  # Markdown content of the report
    attachments: list[FileInfo] | None = None  # Associated files
    sources: list[SourceCitation] | None = None  # Bibliography/references


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


AgentEvent = Union[
    ErrorEvent,
    PlanEvent,
    ToolEvent,
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
    StreamEvent,
    VerificationEvent,
    ReflectionEvent,
    PathEvent,
    MultiTaskEvent,
    WorkspaceEvent,
    BudgetEvent,
    ProgressEvent,
    DeepResearchEvent,
]
