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
    CANCELLED = "cancelled"


class TakeoverState(str, Enum):
    """Takeover lifecycle state for browser takeover control.

    Transitions:
        idle -> takeover_requested -> takeover_active -> resuming -> idle
    Failure: takeover_requested -> idle (pause failed)
    Failure: resuming stays takeover_active (resume failed, user can retry)
    """

    IDLE = "idle"
    TAKEOVER_REQUESTED = "takeover_requested"
    TAKEOVER_ACTIVE = "takeover_active"
    RESUMING = "resuming"


class AgentMode(str, Enum):
    """Agent mode enum - determines which flow to use"""

    DISCUSS = "discuss"  # Simple Q&A with search, no planning
    AGENT = "agent"  # Full PlanAct capabilities


class ResearchMode(str, Enum):
    """Research strategy for the session.

    Controls how information gathering works within an agent session.
    FAST_SEARCH: API-based search only, no planning, quick synthesis (~seconds).
    DEEP_RESEARCH: Browser-first, multi-step planning, CDP prominent (default).
    """

    FAST_SEARCH = "fast_search"
    DEEP_RESEARCH = "deep_research"
    DEAL_FINDING = "deal_finding"


class SandboxLifecycleMode(str, Enum):
    """Sandbox container lifecycle mode."""

    STATIC = "static"
    EPHEMERAL = "ephemeral"


class Session(BaseModel):
    """Session model"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str  # User ID that owns this session
    source: str = "web"  # Channel origin: "web" | "telegram" | "discord" | "cron" | "api"
    sandbox_id: str | None = Field(default=None)  # Identifier for the sandbox environment
    sandbox_owned: bool = False  # True when session owns lifecycle of sandbox container
    sandbox_lifecycle_mode: SandboxLifecycleMode | None = None
    sandbox_created_at: datetime | None = None
    agent_id: str
    task_id: str | None = None
    title: str | None = None
    unread_message_count: int = 0
    latest_message: str | None = None
    latest_message_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    events: list[AgentEvent] = Field(default_factory=list)
    files: list[FileInfo] = Field(default_factory=list)
    status: SessionStatus = SessionStatus.PENDING
    is_shared: bool = False  # Whether this session is shared publicly
    mode: AgentMode = AgentMode.AGENT  # Agent mode: agent (full PlanAct) or discuss (simple Q&A)
    research_mode: ResearchMode = ResearchMode.DEEP_RESEARCH  # Research strategy: fast_search or deep_research
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
    port: int | None = Field(default=None, ge=1, le=65535)
    env_var_keys: list[str] | None = None
    secret_keys: list[str] | None = None
    git_remote: dict | None = None

    # Multi-task challenge tracking (Phase 1)
    multi_task_challenge: MultiTaskChallenge | None = None
    workspace_structure: dict[str, str] | None = None  # folder -> purpose

    # Budget tracking (leverages existing usage system)
    budget_limit: float | None = None  # USD limit
    budget_warning_threshold: float = Field(default=0.8, ge=0.0, le=1.0)  # Warn at 80%
    budget_paused: bool = False  # Session paused due to budget

    # Execution metadata
    iteration_limit_override: int | None = None  # Override default iterations
    complexity_score: float | None = Field(default=None, ge=0.0, le=1.0)  # Assessed task complexity

    # Browser takeover settings
    persist_login_state: bool | None = None  # Whether to persist browser login state across tasks
    takeover_state: TakeoverState = TakeoverState.IDLE  # Takeover lifecycle state
    takeover_reason: str | None = None  # Reason for current takeover (manual|captcha|login|2fa|payment|verification)

    # Telegram option commands (channel-level state, not runtime behavior)
    reasoning_visibility: str | None = None  # off | on | stream — controls Telegram reasoning lane
    thinking_level: str | None = None  # off | low | medium | high — controls LLM thinking effort
    verbose_mode: str | None = None  # off | on — controls verbose output
    elevated_mode: str | None = None  # off | on — controls elevated execution mode

    def get_last_plan(self) -> Plan | None:
        """Get the last plan from the events"""
        for event in reversed(self.events):
            if isinstance(event, PlanEvent):
                return event.plan
        return None
