from typing import Literal

from pydantic import BaseModel, Field

from app.application.schemas.session import (
    ConsoleRecord as ApplicationConsoleRecord,
)
from app.application.schemas.session import (
    ShellViewResponse as ApplicationShellViewResponse,
)
from app.domain.models.session import AgentMode, SessionStatus
from app.interfaces.schemas.event import AgentSSEEvent

ConsoleRecord = ApplicationConsoleRecord
ShellViewResponse = ApplicationShellViewResponse
StreamingMode = Literal["cdp_only"]


class CreateSessionRequest(BaseModel):
    """Create session request schema"""

    mode: AgentMode | None = AgentMode.AGENT
    message: str | None = None  # Phase 4 P0: Initial message for intent classification
    require_fresh_sandbox: bool = True
    sandbox_wait_seconds: float = 3.0


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
        deep_research: Enable deep research mode (parallel wide_research)
        follow_up: Follow-up context from suggestion clicks
    """

    timestamp: int | None = None
    message: str | None = None
    attachments: list[dict] | None = None
    event_id: str | None = None
    skills: list[str] | None = None
    deep_research: bool | None = None
    follow_up: FollowUpContext | None = None


class ResumeSessionRequest(BaseModel):
    """Resume session request schema (for user takeover exit)"""

    context: str | None = None
    persist_login_state: bool | None = None


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
    sandbox: SandboxInfo | None = None  # Phase 4: Early sandbox info for optimistic live preview setup
    status: SessionStatus = SessionStatus.PENDING


class GetSessionResponse(BaseModel):
    """Get session response schema"""

    session_id: str
    title: str | None = None
    status: SessionStatus
    streaming_mode: StreamingMode | None = None
    events: list[AgentSSEEvent] = []
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
    events: list[AgentSSEEvent] = []
    is_shared: bool


class DeepResearchApproveRequest(BaseModel):
    """Approve deep research request"""

    pass  # No body needed, just the action


class DeepResearchSkipRequest(BaseModel):
    """Skip deep research query request"""

    query_id: str | None = None  # If None, skip all


class DeepResearchStatusResponse(BaseModel):
    """Deep research status response"""

    research_id: str
    status: str
    total_queries: int
    completed_queries: int


class BrowseUrlRequest(BaseModel):
    """Browse URL request schema - for direct browser navigation from search results"""

    url: str


class SandboxUrlResponse(BaseModel):
    """Sandbox URL response for CDP screencast access"""

    sandbox_url: str
