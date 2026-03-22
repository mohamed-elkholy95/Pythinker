from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.application.schemas.session import (
    ConsoleRecord as ApplicationConsoleRecord,
)
from app.application.schemas.session import (
    ShellViewResponse as ApplicationShellViewResponse,
)
from app.domain.models.session import AgentMode, ResearchMode, SessionStatus
from app.domain.models.source_citation import SourceCitation
from app.interfaces.schemas.event import AgentSSEEvent

ConsoleRecord = ApplicationConsoleRecord
ShellViewResponse = ApplicationShellViewResponse
StreamingMode = Literal["cdp_only"]


class CreateSessionRequest(BaseModel):
    """Create session request schema"""

    mode: AgentMode | None = AgentMode.AGENT
    research_mode: ResearchMode | None = ResearchMode.DEEP_RESEARCH
    message: str | None = Field(
        default=None, max_length=100_000
    )  # Phase 4 P0: Initial message for intent classification
    require_fresh_sandbox: bool = True
    sandbox_wait_seconds: float = 3.0
    project_id: str | None = None  # Link session to a project

    @field_validator("message", mode="before")
    @classmethod
    def _reject_empty_message(cls, v: object) -> str | None:
        """Reject empty or whitespace-only messages.

        Returns 422 instead of creating a session that immediately cancels.
        """
        if v is None:
            return None
        if isinstance(v, str):
            if not v.strip():
                msg = "Message must not be empty or whitespace-only."
                raise ValueError(msg)
            return v
        return v


class FollowUpContext(BaseModel):
    """Follow-up context from suggestion clicks"""

    selected_suggestion: str = Field(..., description="The suggestion text that was clicked")
    anchor_event_id: str = Field(..., description="Event ID to anchor context to")
    source: str = Field(default="suggestion_click", description="Source of follow-up")


class ChatRequest(BaseModel):
    """Chat request schema

    Attributes:
        timestamp: Unix timestamp when message was sent
        message: User message text
        attachments: List of attached files
        event_id: Optional event ID to resume from (skips events up to this ID).
                 Used for page refresh resumption to avoid re-sending old events.
        skills: List of skill IDs to enable for this request
        follow_up: Follow-up context from suggestion clicks
    """

    timestamp: int | None = None
    message: str | None = Field(default=None, min_length=1, max_length=100_000)
    attachments: list[dict] | None = None
    event_id: str | None = None
    skills: list[str] | None = None
    thinking_mode: str | None = None  # Model tier override: 'auto', 'fast', 'deep_think'
    follow_up: FollowUpContext | None = None


class ResumeSessionRequest(BaseModel):
    """Resume session request schema (for user takeover exit)"""

    context: str | None = None
    persist_login_state: bool | None = None


class TakeoverStartRequest(BaseModel):
    """Start takeover request schema"""

    reason: str | None = "manual"  # manual|captcha|login|2fa|payment|verification


class TakeoverEndRequest(BaseModel):
    """End takeover request schema"""

    context: str | None = None
    persist_login_state: bool | None = None
    resume_agent: bool = True


class TakeoverStatusResponse(BaseModel):
    """Takeover status response schema"""

    session_id: str
    takeover_state: str
    reason: str | None = None


class TakeoverNavigationResponse(BaseModel):
    """Takeover navigation command response schema."""

    ok: bool = True
    action: Literal["back", "forward", "reload", "stop"]
    message: str | None = None


class TakeoverNavigationHistoryEntry(BaseModel):
    id: int
    url: str
    title: str


class TakeoverNavigationHistoryResponse(BaseModel):
    current_index: int
    entries: list[TakeoverNavigationHistoryEntry] = Field(default_factory=list)


class ShellViewRequest(BaseModel):
    """Shell view request schema"""

    session_id: str


class ConfirmActionRequest(BaseModel):
    """Tool action confirmation request"""

    accept: bool


class SandboxInfo(BaseModel):
    """Sandbox connection info returned at session creation."""

    sandbox_id: str
    streaming_mode: StreamingMode = "cdp_only"
    status: str = "initializing"


class CreateSessionResponse(BaseModel):
    """Create session response schema"""

    session_id: str
    mode: AgentMode = AgentMode.AGENT
    research_mode: ResearchMode = ResearchMode.DEEP_RESEARCH
    sandbox: SandboxInfo | None = None  # Phase 4: Early sandbox info for optimistic live preview setup
    status: SessionStatus = SessionStatus.PENDING


class GetSessionResponse(BaseModel):
    """Get session response schema"""

    session_id: str
    title: str | None = None
    status: SessionStatus
    source: str = "web"
    research_mode: ResearchMode = ResearchMode.DEEP_RESEARCH
    streaming_mode: StreamingMode | None = None
    events: list[AgentSSEEvent] = Field(default_factory=list)
    is_shared: bool = False


class SessionStatusResponse(BaseModel):
    """Lightweight session status response for polling."""

    session_id: str
    status: SessionStatus
    sandbox_id: str | None = None
    streaming_mode: StreamingMode | None = None
    created_at: float | None = None


class ActiveSessionResponse(BaseModel):
    """Response for active session lookup."""

    session: SessionStatusResponse | None = None


class ListSessionItem(BaseModel):
    """List session item schema"""

    session_id: str
    title: str | None = None
    latest_message: str | None = None
    latest_message_at: int | None = None
    status: SessionStatus
    unread_message_count: int
    is_shared: bool = False
    source: str = "web"


class ListSessionResponse(BaseModel):
    """List session response schema"""

    sessions: list[ListSessionItem]


class ShareSessionResponse(BaseModel):
    """Share session response schema"""

    session_id: str
    is_shared: bool


class SharedSessionResponse(BaseModel):
    """Shared session response schema (for public access)"""

    session_id: str
    title: str | None = None
    status: SessionStatus
    events: list[AgentSSEEvent] = Field(default_factory=list)
    is_shared: bool


class BrowseUrlRequest(BaseModel):
    """Browse URL request schema - for direct browser navigation from search results"""

    url: str


class RenameSessionRequest(BaseModel):
    """Rename session request schema"""

    title: str = Field(..., min_length=1, max_length=500, description="New title for the session")


class ReportPdfDownloadRequest(BaseModel):
    """Request body for generating a report PDF."""

    title: str = Field(default="Report", min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    sources: list[SourceCitation] = Field(default_factory=list)
    author: str | None = Field(default=None, max_length=200)


class DeleteSessionResponse(BaseModel):
    """Delete session response schema"""

    warnings: list[str] = Field(default_factory=list, description="Non-fatal cleanup warnings")


class SandboxUrlResponse(BaseModel):
    """Sandbox URL response for CDP screencast access"""

    sandbox_url: str
