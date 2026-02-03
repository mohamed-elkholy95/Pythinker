import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.domain.models.event import AgentEvent, PlanEvent
from app.domain.models.file import FileInfo
from app.domain.models.multi_task import MultiTaskChallenge
from app.domain.models.plan import Plan


class SessionStatus(str, Enum):
    """Session status enum"""

    PENDING = "pending"
    INITIALIZING = "initializing"  # Sandbox being prepared (Phase 2: Eager init)
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentMode(str, Enum):
    """Agent mode enum - determines which flow to use"""

    DISCUSS = "discuss"  # Simple Q&A with search, no planning
    AGENT = "agent"  # Full PlanAct capabilities


class Session(BaseModel):
    """Session model"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str  # User ID that owns this session
    sandbox_id: str | None = Field(default=None)  # Identifier for the sandbox environment
    agent_id: str
    task_id: str | None = None
    title: str | None = None
    unread_message_count: int = 0
    latest_message: str | None = None
    latest_message_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    events: list[AgentEvent] = []
    files: list[FileInfo] = []
    status: SessionStatus = SessionStatus.PENDING
    is_shared: bool = False  # Whether this session is shared publicly
    mode: AgentMode = AgentMode.AGENT  # Agent mode: agent (full PlanAct) or discuss (simple Q&A)
    pending_action: dict | None = None
    pending_action_status: str | None = None
    # Workspace metadata (sanitized)
    project_name: str | None = None
    project_path: str | None = None
    template_id: str | None = None
    template_used: str | None = None
    workspace_capabilities: list[str] | None = None
    dev_command: str | None = None
    build_command: str | None = None
    test_command: str | None = None
    port: int | None = None
    env_var_keys: list[str] | None = None
    secret_keys: list[str] | None = None
    git_remote: dict | None = None

    # Multi-task challenge tracking (Phase 1)
    multi_task_challenge: MultiTaskChallenge | None = None
    workspace_structure: dict[str, str] | None = None  # folder -> purpose

    # Budget tracking (leverages existing usage system)
    budget_limit: float | None = None  # USD limit
    budget_warning_threshold: float = 0.8  # Warn at 80%
    budget_paused: bool = False  # Session paused due to budget

    # Execution metadata
    iteration_limit_override: int | None = None  # Override default iterations
    complexity_score: float | None = None  # Assessed task complexity (0.0-1.0)

    # Browser takeover settings
    persist_login_state: bool | None = None  # Whether to persist browser login state across tasks

    # OpenReplay session tracking
    openreplay_session_id: str | None = None  # OpenReplay session ID for replay
    openreplay_session_url: str | None = None  # Direct URL to OpenReplay session

    def get_last_plan(self) -> Plan | None:
        """Get the last plan from the events"""
        for event in reversed(self.events):
            if isinstance(event, PlanEvent):
                return event.plan
        return None
