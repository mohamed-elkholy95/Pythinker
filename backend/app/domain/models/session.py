from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import List, Optional, Dict
from enum import Enum
import uuid
from app.domain.models.event import PlanEvent, AgentEvent
from app.domain.models.plan import Plan
from app.domain.models.file import FileInfo
from app.domain.models.multi_task import MultiTaskChallenge


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
    AGENT = "agent"      # Full PlanAct capabilities


class Session(BaseModel):
    """Session model"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str  # User ID that owns this session
    sandbox_id: Optional[str] = Field(default=None)  # Identifier for the sandbox environment
    agent_id: str
    task_id: Optional[str] = None
    title: Optional[str] = None
    unread_message_count: int = 0
    latest_message: Optional[str] = None
    latest_message_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    events: List[AgentEvent] = []
    files: List[FileInfo] = []
    status: SessionStatus = SessionStatus.PENDING
    is_shared: bool = False  # Whether this session is shared publicly
    mode: AgentMode = AgentMode.AGENT  # Agent mode: agent (full PlanAct) or discuss (simple Q&A)
    pending_action: Optional[dict] = None
    pending_action_status: Optional[str] = None
    # Workspace metadata (sanitized)
    project_name: Optional[str] = None
    project_path: Optional[str] = None
    template_id: Optional[str] = None
    template_used: Optional[str] = None
    workspace_capabilities: Optional[List[str]] = None
    dev_command: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    port: Optional[int] = None
    env_var_keys: Optional[List[str]] = None
    secret_keys: Optional[List[str]] = None
    git_remote: Optional[dict] = None

    # Multi-task challenge tracking (Phase 1)
    multi_task_challenge: Optional[MultiTaskChallenge] = None
    workspace_structure: Optional[Dict[str, str]] = None  # folder -> purpose

    # Budget tracking (leverages existing usage system)
    budget_limit: Optional[float] = None  # USD limit
    budget_warning_threshold: float = 0.8  # Warn at 80%
    budget_paused: bool = False  # Session paused due to budget

    # Execution metadata
    iteration_limit_override: Optional[int] = None  # Override default iterations
    complexity_score: Optional[float] = None  # Assessed task complexity (0.0-1.0)

    # Browser takeover settings
    persist_login_state: Optional[bool] = None  # Whether to persist browser login state across tasks

    def get_last_plan(self) -> Optional[Plan]:
        """Get the last plan from the events"""
        for event in reversed(self.events):
            if isinstance(event, PlanEvent):
                return event.plan
        return None
