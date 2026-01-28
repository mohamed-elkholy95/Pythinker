from typing import Dict, Optional, List, Type, TypeVar, Generic, get_args, Self, Any
from datetime import datetime, timezone, UTC, date
from beanie import Document
from pydantic import BaseModel
from app.domain.models.agent import Agent
from app.domain.models.memory import Memory
from app.domain.models.event import AgentEvent
from app.domain.models.session import Session, SessionStatus, AgentMode
from app.domain.models.file import FileInfo
from app.domain.models.user import User, UserRole
from app.domain.models.usage import UsageRecord, DailyUsageAggregate, UsageType
from app.domain.models.multi_task import MultiTaskChallenge
from pymongo import IndexModel, ASCENDING, DESCENDING

T = TypeVar('T', bound=BaseModel)

class BaseDocument(Document, Generic[T]):
    def __init_subclass__(cls, id_field="id", domain_model_class: Type[T] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._ID_FIELD = id_field
        cls._DOMAIN_MODEL_CLASS = domain_model_class
    
    def update_from_domain(self, domain_obj: T) -> None:
        """Update the document from domain model"""
        data = domain_obj.model_dump(exclude={'id', 'created_at'})
        data[self._ID_FIELD] = domain_obj.id
        if hasattr(self, 'updated_at'):
            data['updated_at'] = datetime.now(UTC)
        
        for field, value in data.items():
            setattr(self, field, value)
    
    def to_domain(self) -> T:
        """Convert MongoDB document to domain model"""
        # Convert to dict and map agent_id to id field
        data = self.model_dump(exclude={'id'})
        data['id'] = data.pop(self._ID_FIELD)
        return self._DOMAIN_MODEL_CLASS.model_validate(data)
    
    @classmethod
    def from_domain(cls, domain_obj: T) -> Self:
        """Create a new MongoDB agent from domain"""
        # Convert to dict and map id to agent_id field
        data = domain_obj.model_dump()
        data[cls._ID_FIELD] = data.pop('id')
        return cls.model_validate(data)

class UserDocument(BaseDocument[User], id_field="user_id", domain_model_class=User):
    """MongoDB document for User"""
    user_id: str
    fullname: str
    email: str  # Now required field for login
    password_hash: Optional[str] = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
    last_login_at: Optional[datetime] = None

    class Settings:
        name = "users"
        indexes = [
            "user_id",
            "fullname",  # Keep fullname index but not unique
            IndexModel([("email", ASCENDING)], unique=True),  # Email as unique index
        ]

class AgentDocument(BaseDocument[Agent], id_field="agent_id", domain_model_class=Agent):
    """MongoDB document for Agent"""
    agent_id: str
    model_name: str
    temperature: float
    max_tokens: int
    memories: Dict[str, Memory] = {}
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)

    class Settings:
        name = "agents"
        indexes = [
            "agent_id",
            IndexModel([("created_at", DESCENDING)]),  # Agents by creation time
        ]


class SessionDocument(BaseDocument[Session], id_field="session_id", domain_model_class=Session):
    """MongoDB model for Session"""
    session_id: str
    user_id: str  # User ID that owns this session
    sandbox_id: Optional[str] = None
    agent_id: str
    task_id: Optional[str] = None
    title: Optional[str] = None
    unread_message_count: int = 0
    latest_message: Optional[str] = None
    latest_message_at: Optional[datetime] = None
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
    events: List[AgentEvent]
    status: SessionStatus
    files: List[FileInfo] = []
    is_shared: Optional[bool] = False
    mode: AgentMode = AgentMode.DISCUSS  # Agent mode: discuss or agent
    pending_action: Optional[Dict[str, Any]] = None
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
    git_remote: Optional[Dict[str, Any]] = None

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

    # Timeline tracking
    event_count: int = 0  # Total number of events for efficient queries

    class Settings:
        name = "sessions"
        indexes = [
            "session_id",
            "user_id",  # Index for user_id queries
            "status",  # Index for status filtering
            "is_shared",  # Index for finding shared sessions
            # Compound indexes for common query patterns
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),  # User's sessions by status
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),  # User's sessions chronologically
            IndexModel([("user_id", ASCENDING), ("updated_at", DESCENDING)]),  # User's sessions by recent activity
            IndexModel([("is_shared", ASCENDING), ("created_at", DESCENDING)]),  # Shared sessions chronologically
        ]


class SnapshotDocument(Document):
    """MongoDB document for StateSnapshot"""
    snapshot_id: str
    session_id: str
    action_id: Optional[str] = None
    sequence_number: int

    # Timing
    created_at: datetime = datetime.now(timezone.utc)

    # Snapshot type
    snapshot_type: str  # SnapshotType enum value

    # Resource identification
    resource_path: Optional[str] = None

    # Snapshot data stored as JSON
    snapshot_data: Dict = {}

    # Compression info
    is_compressed: bool = False
    compressed_size_bytes: Optional[int] = None

    class Settings:
        name = "snapshots"
        indexes = [
            "snapshot_id",
            "session_id",
            IndexModel([("session_id", ASCENDING), ("sequence_number", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("created_at", ASCENDING)]),
            "action_id",
        ]


class UsageDocument(BaseDocument[UsageRecord], id_field="usage_id", domain_model_class=UsageRecord):
    """MongoDB document for individual LLM usage records."""
    usage_id: str
    user_id: str
    session_id: str

    # Model info
    model: str
    provider: str  # "openai", "anthropic", "ollama"

    # Token counts
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0

    # Cost (in USD)
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0

    # Metadata
    usage_type: str = UsageType.LLM_CALL.value
    created_at: datetime = datetime.now(timezone.utc)

    class Settings:
        name = "usage"
        indexes = [
            "usage_id",
            "user_id",
            "session_id",
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("session_id", ASCENDING), ("created_at", ASCENDING)]),
        ]


class DailyUsageDocument(BaseDocument[DailyUsageAggregate], id_field="usage_id", domain_model_class=DailyUsageAggregate):
    """MongoDB document for daily usage aggregates."""
    usage_id: str  # Format: {user_id}_{date}
    user_id: str
    date: date

    # Token totals
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_tokens: int = 0

    # Cost totals
    total_prompt_cost: float = 0.0
    total_completion_cost: float = 0.0
    total_cost: float = 0.0

    # Activity counts
    llm_call_count: int = 0
    tool_call_count: int = 0
    session_count: int = 0

    # Model breakdown
    tokens_by_model: Dict[str, int] = {}
    cost_by_model: Dict[str, float] = {}

    # Sessions active this day
    active_sessions: List[str] = []

    # Timestamps
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)

    class Settings:
        name = "daily_usage"
        indexes = [
            "usage_id",
            "user_id",
            IndexModel([("user_id", ASCENDING), ("date", DESCENDING)]),
        ]
