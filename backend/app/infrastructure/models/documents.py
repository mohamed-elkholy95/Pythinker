import logging
from datetime import UTC, date, datetime
from typing import Any, ClassVar, Generic, Self, TypeVar

from beanie import Document
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.domain.models.agent import Agent
from app.domain.models.agent_usage import AgentRun, AgentStep
from app.domain.models.claim_provenance import ClaimProvenance, ClaimType, ClaimVerificationStatus
from app.domain.models.event import AgentEvent
from app.domain.models.file import FileInfo
from app.domain.models.memory import Memory
from app.domain.models.multi_task import MultiTaskChallenge
from app.domain.models.pricing_snapshot import PricingSnapshot
from app.domain.models.screenshot import SessionScreenshot
from app.domain.models.session import (
    AgentMode,
    PendingAction,
    PendingActionStatus,
    ReasoningVisibility,
    ResearchMode,
    Session,
    SessionStatus,
    TakeoverState,
    ThinkingLevel,
)
from app.domain.models.skill import Skill, SkillCategory, SkillInvocationType, SkillSource
from app.domain.models.usage import DailyUsageAggregate, UsageRecord, UsageType
from app.domain.models.user import User, UserRole
from app.domain.models.visited_source import ContentAccessMethod, VisitedSource

T = TypeVar("T", bound=BaseModel)


class BaseDocument(Document, Generic[T]):
    def __init_subclass__(cls, id_field="id", domain_model_class: type[T] | None = None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._ID_FIELD = id_field
        cls._DOMAIN_MODEL_CLASS = domain_model_class

    def update_from_domain(self, domain_obj: T) -> None:
        """Update the document from domain model.

        Only sets fields that exist on the document class, preventing
        ValueError when the domain model evolves ahead of the document
        (e.g. gateway running stale code while backend has new fields).
        """
        data = domain_obj.model_dump(exclude={"id", "created_at"})
        data[self._ID_FIELD] = domain_obj.id
        if hasattr(self, "updated_at"):
            data["updated_at"] = datetime.now(UTC)

        known_fields = set(self.model_fields)
        for field, value in data.items():
            if field in known_fields:
                setattr(self, field, value)

    def to_domain(self) -> T:
        """Convert MongoDB document to domain model"""
        # Convert to dict and map agent_id to id field
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop(self._ID_FIELD)
        return self._DOMAIN_MODEL_CLASS.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: T) -> Self:
        """Create a new MongoDB agent from domain"""
        # Convert to dict and map id to agent_id field
        data = domain_obj.model_dump()
        data[cls._ID_FIELD] = data.pop("id")
        return cls.model_validate(data)


class UserDocument(BaseDocument[User], id_field="user_id", domain_model_class=User):
    """MongoDB document for User"""

    user_id: str
    fullname: str
    email: str  # Now required field for login
    password_hash: str | None = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    email_verified: bool = False
    totp_secret: str | None = None
    totp_enabled: bool = False
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)
    last_login_at: datetime | None = None

    class Settings:
        name: ClassVar[str] = "users"
        indexes: ClassVar[list[Any]] = [
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
    memories: dict[str, Memory] = Field(default_factory=dict)
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)

    class Settings:
        name: ClassVar[str] = "agents"
        indexes: ClassVar[list[Any]] = [
            "agent_id",
            IndexModel([("created_at", DESCENDING)]),  # Agents by creation time
        ]


# Known AgentEvent types for the discriminated union — used to filter out
# legacy/removed event types so that loading old sessions from MongoDB
# doesn't crash Pydantic validation.
_KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "error",
        "plan",
        "tool",
        "tool_stream",
        "tool_progress",
        "step",
        "message",
        "done",
        "title",
        "wait",
        "knowledge",
        "datasource",
        "idle",
        "mcp_health",
        "mode_change",
        "suggestion",
        "report",
        "skill_delivery",
        "skill_activation",
        "stream",
        "verification",
        "reflection",
        "path",
        "multi_task",
        "workspace",
        "budget",
        "progress",
        "comprehension",
        "task_recreation",
        "phase_transition",
        "checkpoint_saved",
        "wide_research",
        "thought",
        "confidence",
        "canvas_update",
        "flow_selection",
        "flow_transition",
        "research_mode",
        "phase",
    }
)

_doc_logger = logging.getLogger(__name__)


class SessionDocument(BaseDocument[Session], id_field="session_id", domain_model_class=Session):
    """MongoDB model for Session"""

    session_id: str
    user_id: str  # User ID that owns this session
    source: str = "web"  # Channel origin: "web" | "telegram" | "discord" | "cron" | "api"
    sandbox_id: str | None = None
    sandbox_owned: bool = False
    sandbox_lifecycle_mode: str | None = None
    sandbox_created_at: datetime | None = None
    agent_id: str
    task_id: str | None = None
    title: str | None = None
    unread_message_count: int = 0
    latest_message: str | None = None
    latest_message_at: datetime | None = None
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)
    events: list[AgentEvent] = Field(default_factory=list)
    status: SessionStatus

    @model_validator(mode="before")
    @classmethod
    def _filter_unknown_events(cls, data: Any) -> Any:
        """Filter out legacy/removed event types before Pydantic validation.

        MongoDB may contain events with types that have been removed from the
        codebase. Without this filter, the discriminated
        union on AgentEvent would raise a ValidationError and crash the entire
        session load.
        """
        if isinstance(data, dict) and "events" in data:
            raw_events = data["events"]
            if raw_events:
                filtered = []
                for ev in raw_events:
                    ev_type = ev.get("type", "") if isinstance(ev, dict) else getattr(ev, "type", "")
                    if ev_type in _KNOWN_EVENT_TYPES:
                        filtered.append(ev)
                    else:
                        _doc_logger.debug("Skipping unknown event type %r during session load", ev_type)
                data["events"] = filtered
        return data

    files: list[FileInfo] = Field(default_factory=list)
    is_shared: bool | None = False
    mode: AgentMode = AgentMode.DISCUSS  # Agent mode: discuss or agent
    research_mode: ResearchMode = ResearchMode.DEEP_RESEARCH  # Research strategy
    pending_action: PendingAction | None = None
    pending_action_status: PendingActionStatus | None = None
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
    git_remote: dict[str, Any] | None = None

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

    # Timeline tracking
    event_count: int = 0  # Total number of events for efficient queries

    # Browser takeover settings
    persist_login_state: bool | None = None  # Whether to persist browser login state across tasks
    takeover_state: TakeoverState = TakeoverState.IDLE  # Takeover lifecycle state
    takeover_reason: str | None = None  # Reason for current takeover

    # Telegram option commands (channel-level state, not runtime behavior)
    reasoning_visibility: ReasoningVisibility | None = None
    thinking_level: ThinkingLevel | None = None
    verbose_mode: str | None = None  # off | on
    elevated_mode: str | None = None  # off | on

    class Settings:
        name: ClassVar[str] = "sessions"
        indexes: ClassVar[list[Any]] = [
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
    action_id: str | None = None
    sequence_number: int

    # Timing
    created_at: datetime = datetime.now(UTC)

    # Snapshot type
    snapshot_type: str  # SnapshotType enum value

    # Resource identification
    resource_path: str | None = None

    # Snapshot data stored as JSON
    snapshot_data: dict = Field(default_factory=dict)

    # Compression info
    is_compressed: bool = False
    compressed_size_bytes: int | None = None

    class Settings:
        name: ClassVar[str] = "snapshots"
        indexes: ClassVar[list[Any]] = [
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
    created_at: datetime = datetime.now(UTC)

    class Settings:
        name: ClassVar[str] = "usage"
        indexes: ClassVar[list[Any]] = [
            "usage_id",
            "user_id",
            "session_id",
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("session_id", ASCENDING), ("created_at", ASCENDING)]),
        ]


class DailyUsageDocument(
    BaseDocument[DailyUsageAggregate], id_field="usage_id", domain_model_class=DailyUsageAggregate
):
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
    tokens_by_model: dict[str, int] = Field(default_factory=dict)
    cost_by_model: dict[str, float] = Field(default_factory=dict)

    # Sessions active this day
    active_sessions: list[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)

    class Settings:
        name: ClassVar[str] = "daily_usage"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("usage_id", ASCENDING)], unique=True),
            "user_id",
            IndexModel([("user_id", ASCENDING), ("date", DESCENDING)]),
        ]


class AgentRunDocument(Document):
    """MongoDB document for aggregated agent runs."""

    run_id: str
    user_id: str
    session_id: str
    agent_id: str | None = None
    entrypoint: str | None = None
    status: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: float | None = None
    step_count: int = 0
    tool_call_count: int = 0
    mcp_call_count: int = 0
    error_count: int = 0
    total_input_tokens: int = 0
    total_cached_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    provider_billed_cost_usd: float | None = None
    billing_status: str = "estimated"
    primary_model: str | None = None
    primary_provider: str | None = None

    @classmethod
    def from_domain(cls, domain_obj: AgentRun) -> "AgentRunDocument":
        return cls.model_validate(domain_obj.model_dump())

    def to_domain(self) -> AgentRun:
        return AgentRun.model_validate(self.model_dump(exclude={"id"}))

    class Settings:
        name: ClassVar[str] = "agent_runs"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("run_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("started_at", DESCENDING)]),
            IndexModel([("session_id", ASCENDING), ("started_at", DESCENDING)]),
        ]


class AgentStepDocument(Document):
    """MongoDB document for individual agent steps."""

    step_id: str
    run_id: str
    session_id: str
    user_id: str
    step_type: str
    provider: str | None = None
    model: str | None = None
    tool_name: str | None = None
    mcp_server: str | None = None
    status: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: float | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    provider_billed_cost_usd: float | None = None
    error_type: str | None = None
    provider_usage_raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, domain_obj: AgentStep) -> "AgentStepDocument":
        return cls.model_validate(domain_obj.model_dump())

    def to_domain(self) -> AgentStep:
        return AgentStep.model_validate(self.model_dump(exclude={"id"}))

    class Settings:
        name: ClassVar[str] = "agent_steps"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("step_id", ASCENDING)], unique=True),
            IndexModel([("run_id", ASCENDING), ("started_at", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("started_at", DESCENDING)]),
        ]


class PricingSnapshotDocument(Document):
    """MongoDB document for versioned pricing snapshots."""

    pricing_snapshot_id: str
    provider: str
    model_pattern: str
    effective_from: datetime
    effective_to: datetime | None = None
    input_price_per_1m: float
    output_price_per_1m: float
    cached_read_price_per_1m: float | None = None
    cache_write_price_per_1m: float | None = None
    currency: str = "USD"
    source_url: str
    source_retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_domain(cls, domain_obj: PricingSnapshot) -> "PricingSnapshotDocument":
        return cls.model_validate(domain_obj.model_dump())

    def to_domain(self) -> PricingSnapshot:
        return PricingSnapshot.model_validate(self.model_dump(exclude={"id"}))

    class Settings:
        name: ClassVar[str] = "pricing_snapshots"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("pricing_snapshot_id", ASCENDING)], unique=True),
            IndexModel([("provider", ASCENDING), ("model_pattern", ASCENDING), ("effective_from", DESCENDING)]),
        ]


class SkillDocument(BaseDocument[Skill], id_field="skill_id", domain_model_class=Skill):
    """MongoDB document for Skill."""

    skill_id: str  # Unique skill identifier (slug)
    name: str
    description: str
    category: SkillCategory
    source: SkillSource = SkillSource.CUSTOM  # Default to CUSTOM for safety
    icon: str = "sparkles"

    # Tool integration
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)

    # Prompt enhancement
    system_prompt_addition: str | None = None

    # Configuration schema
    configurations: dict[str, dict] = Field(default_factory=dict)
    default_enabled: bool = False

    # Claude-style invocation configuration
    invocation_type: SkillInvocationType = SkillInvocationType.BOTH
    allowed_tools: list[str] | None = None  # Tool restrictions when skill is active
    supports_dynamic_context: bool = False  # !command substitution support
    trigger_patterns: list[str] = Field(default_factory=list)  # Auto-activation patterns

    # Progressive Disclosure Fields (Pythinker AI pattern)
    body: str = ""  # Full instructions from SKILL.md (disclosed at level 2+)
    resources: list[dict] = Field(default_factory=list)  # Bundled resources (disclosed at level 3)

    # Metadata
    version: str = "1.0.0"
    author: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Premium/feature flags
    is_premium: bool = False

    # Custom skill ownership (Phase 1: Custom Skills)
    owner_id: str | None = None
    is_public: bool = False
    parent_skill_id: str | None = None

    # Marketplace features (Phase 2: Skill Marketplace)
    community_rating: float = 0.0  # Average rating (1-5)
    rating_count: int = 0  # Number of ratings
    ratings: dict[str, float] = Field(default_factory=dict)  # user_id -> rating
    install_count: int = 0  # Number of installations
    is_featured: bool = False  # Featured in marketplace
    tags: list[str] = Field(default_factory=list)  # Searchable tags

    class Settings:
        name: ClassVar[str] = "skills"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("skill_id", ASCENDING)], unique=True),
            # "category" and "source" standalone indexes removed — covered by compound prefix below
            IndexModel([("category", ASCENDING), ("source", ASCENDING)]),
            # "owner_id" standalone index removed — covered by compound prefix below
            IndexModel([("owner_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("is_public", ASCENDING), ("created_at", DESCENDING)]),
            "invocation_type",  # Index for AI-invokable skills queries
            # Marketplace indexes
            IndexModel([("is_public", ASCENDING), ("community_rating", DESCENDING)]),
            IndexModel([("is_public", ASCENDING), ("install_count", DESCENDING)]),
            IndexModel([("is_public", ASCENDING), ("is_featured", ASCENDING)]),
            IndexModel([("tags", ASCENDING)]),
        ]


class AgentDecisionDocument(Document):
    """Capture agent decision reasoning for monitoring and analysis."""

    decision_id: str  # UUID
    session_id: str
    agent_id: str
    user_id: str
    timestamp: datetime

    decision_type: str  # "tool_selection", "plan_modification", "mode_selection"
    agent_status: str  # PLANNING, EXECUTING, etc.

    available_options: list[str]
    selected_option: str
    reasoning: str
    confidence: float

    outcome: str | None = None  # "success", "error", "replanned"
    led_to_error: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "agent_decisions"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("session_id", ASCENDING), ("timestamp", ASCENDING)]),
            IndexModel([("decision_type", ASCENDING)]),
            IndexModel([("led_to_error", ASCENDING)]),
            # TTL: auto-delete after 30 days (ephemeral analysis data)
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=30 * 86400),
        ]


class ToolExecutionDocument(Document):
    """Enhanced tool execution tracking with resource usage."""

    execution_id: str
    session_id: str
    tool_name: str
    function_name: str
    function_args: dict[str, Any]

    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None

    success: bool
    error_type: str | None = None
    retry_count: int = 0

    # Resource usage
    container_cpu_percent: float | None = None
    container_memory_mb: float | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "tool_executions"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("session_id", ASCENDING), ("started_at", ASCENDING)]),
            IndexModel([("tool_name", ASCENDING), ("success", ASCENDING)]),
            # TTL: auto-delete after 30 days (ephemeral execution data)
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=30 * 86400),
        ]


class WorkflowStateDocument(Document):
    """Track workflow state transitions for analysis."""

    session_id: str
    timestamp: datetime

    previous_status: str
    current_status: str
    transition_reason: str

    iteration_count: int
    verification_loops: int
    stuck_loop_detected: bool

    context_tokens: int
    context_pressure: str  # "low", "medium", "high", "critical"

    state_duration_ms: float

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "workflow_states"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("session_id", ASCENDING), ("timestamp", ASCENDING)]),
            # TTL: auto-delete after 7 days (short-lived analysis data)
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=7 * 86400),
        ]


class VisitedSourceDocument(BaseDocument[VisitedSource], id_field="source_id", domain_model_class=VisitedSource):
    """MongoDB document for VisitedSource - tracks URLs actually visited during sessions."""

    source_id: str
    session_id: str
    tool_event_id: str  # References ToolEvent.id that produced this

    # URL and access info
    url: str
    final_url: str | None = None  # After redirects
    access_method: ContentAccessMethod
    access_time: datetime = datetime.now(UTC)

    # Content fingerprint
    content_hash: str  # SHA-256 of extracted text content
    content_length: int
    content_preview: str = ""  # First 2000 chars

    # Page metadata
    page_title: str | None = None
    meta_description: str | None = None
    last_modified: datetime | None = None

    # Access status
    access_status: str = "full"  # "full", "partial", "paywall", "error"
    paywall_confidence: float = 0.0

    # Extraction metadata
    extracted_at: datetime = datetime.now(UTC)
    extraction_method: str = "html_to_text"

    class Settings:
        name: ClassVar[str] = "visited_sources"
        indexes: ClassVar[list[Any]] = [
            "source_id",
            "session_id",
            "tool_event_id",
            IndexModel([("session_id", ASCENDING), ("url", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("access_time", DESCENDING)]),
            IndexModel([("content_hash", ASCENDING)]),
        ]


class ScreenshotDocument(
    BaseDocument[SessionScreenshot], id_field="screenshot_id", domain_model_class=SessionScreenshot
):
    """MongoDB document for session screenshots."""

    screenshot_id: str
    session_id: str
    sequence_number: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    storage_key: str = ""  # MinIO S3 object key
    thumbnail_storage_key: str | None = None
    trigger: str = "periodic"
    tool_call_id: str | None = None
    tool_name: str | None = None
    function_name: str | None = None
    action_type: str | None = None
    size_bytes: int = 0
    # Deduplication fields
    perceptual_hash: str | None = None
    is_duplicate: bool = False
    original_storage_key: str | None = None

    class Settings:
        name: ClassVar[str] = "session_screenshots"
        indexes: ClassVar[list[Any]] = [
            "session_id",
            IndexModel([("session_id", ASCENDING), ("sequence_number", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("timestamp", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("perceptual_hash", ASCENDING)]),
        ]


class ClaimProvenanceDocument(
    BaseDocument[ClaimProvenance], id_field="provenance_id", domain_model_class=ClaimProvenance
):
    """MongoDB document for ClaimProvenance - links claims in reports to source evidence."""

    provenance_id: str
    session_id: str
    report_id: str | None = None  # Links to ReportEvent.id

    # The claim itself
    claim_text: str
    claim_type: ClaimType = ClaimType.UNKNOWN
    claim_hash: str  # For deduplication

    # Source linkage (primary evidence)
    source_id: str | None = None  # References VisitedSource.id
    tool_event_id: str | None = None  # References ToolEvent.id
    source_url: str | None = None  # URL for quick reference

    # Evidence from source
    supporting_excerpt: str | None = None
    excerpt_location: str | None = None
    similarity_score: float = 0.0

    # Verification
    verification_status: ClaimVerificationStatus = ClaimVerificationStatus.UNVERIFIED
    verification_method: str | None = None
    verified_at: datetime | None = None
    verifier_confidence: float = 0.0

    # Audit trail
    created_at: datetime = datetime.now(UTC)
    created_by: str = "system"

    # Flags
    is_fabricated: bool = False
    requires_manual_review: bool = False
    is_numeric: bool = False
    extracted_numbers: list[float] = Field(default_factory=list)

    class Settings:
        name: ClassVar[str] = "claim_provenance"
        indexes: ClassVar[list[Any]] = [
            "provenance_id",
            "session_id",
            "report_id",
            "claim_hash",
            IndexModel([("session_id", ASCENDING), ("claim_hash", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("verification_status", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("is_fabricated", ASCENDING)]),
            IndexModel([("session_id", ASCENDING), ("is_numeric", ASCENDING)]),
            IndexModel([("report_id", ASCENDING)]),
        ]


class RatingDocument(Document):
    """MongoDB document for session ratings / user feedback."""

    session_id: str
    report_id: str
    user_id: str
    user_email: str
    user_name: str
    rating: int = Field(ge=1, le=5)
    feedback: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "ratings"
        indexes: ClassVar[list[Any]] = [
            "session_id",
            "user_id",
            IndexModel([("created_at", DESCENDING)]),
        ]
