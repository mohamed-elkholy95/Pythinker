from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Literal, Optional, Union, List
from datetime import datetime
import uuid
from enum import Enum
from app.domain.models.plan import Plan, Step
from app.domain.models.file import FileInfo
from app.domain.models.search import SearchResultItem


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
    step: Optional[Step] = None

class BrowserToolContent(BaseModel):
    """Browser tool content"""
    screenshot: Optional[str] = None
    content: Optional[str] = None  # Page content (text or HTML)

class SearchToolContent(BaseModel):
    """Search tool content"""
    results: List[SearchResultItem]

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
    screenshot: Optional[str] = None

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
    tool_content: Optional[ToolContent] = None
    function_name: str
    function_args: Dict[str, Any]
    status: ToolStatus
    function_result: Optional[Any] = None

    # Action/observation metadata (OpenHands-style)
    action_type: Optional[str] = None
    observation_type: Optional[str] = None
    command: Optional[str] = None
    cwd: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    file_path: Optional[str] = None
    diff: Optional[str] = None
    runtime_status: Optional[str] = None

    # Security/confirmation metadata
    security_risk: Optional[str] = None
    security_reason: Optional[str] = None
    security_suggestions: Optional[List[str]] = None
    confirmation_state: Optional[str] = None

    # Timeline tracking fields
    sequence_number: Optional[int] = None  # Position in session timeline
    started_at: Optional[datetime] = None  # When tool execution started
    completed_at: Optional[datetime] = None  # When tool execution completed
    duration_ms: Optional[float] = None  # Execution duration in milliseconds (stored as float for precision)

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
    attachments: Optional[List[FileInfo]] = None

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
    reason: Optional[str] = None


class MCPHealthEvent(BaseEvent):
    """MCP server health status event"""
    type: Literal["mcp_health"] = "mcp_health"
    server_name: str
    healthy: bool
    error: Optional[str] = None
    tools_available: int = 0


class ModeChangeEvent(BaseEvent):
    """Mode change event when switching between discuss and agent modes"""
    type: Literal["mode_change"] = "mode_change"
    mode: str  # "discuss" or "agent"
    reason: Optional[str] = None  # Reason for mode switch


class SuggestionEvent(BaseEvent):
    """Suggestion event for end-of-response suggestions"""
    type: Literal["suggestion"] = "suggestion"
    suggestions: List[str]  # List of 2-3 contextual suggestions


class ReportEvent(BaseEvent):
    """Report event for displaying task completion reports in Notion-like markdown view"""
    type: Literal["report"] = "report"
    id: str  # Unique ID for the report (named 'id' for frontend compatibility)
    title: str  # Report title
    content: str  # Markdown content of the report
    attachments: Optional[List[FileInfo]] = None  # Associated files


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
    verdict: Optional[str] = None  # "pass", "revise", "fail"
    confidence: Optional[float] = None
    summary: Optional[str] = None
    revision_feedback: Optional[str] = None  # Feedback for replanning


class ReflectionStatus(str, Enum):
    """Reflection status enum"""
    TRIGGERED = "triggered"
    COMPLETED = "completed"


class ReflectionEvent(BaseEvent):
    """Reflection event during execution"""
    type: Literal["reflection"] = "reflection"
    status: ReflectionStatus
    decision: Optional[str] = None  # "continue", "adjust", "replan", "escalate", "abort"
    confidence: Optional[float] = None
    summary: Optional[str] = None
    trigger_reason: Optional[str] = None  # Why reflection was triggered


class PathEvent(BaseEvent):
    """Path event for Tree-of-Thoughts multi-path exploration"""
    type: Literal["path"] = "path"
    path_id: str
    action: str  # "created", "exploring", "completed", "abandoned", "selected"
    score: Optional[float] = None
    description: Optional[str] = None


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
]
