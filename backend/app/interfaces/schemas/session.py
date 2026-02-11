from pydantic import BaseModel

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


class CreateSessionRequest(BaseModel):
    """Create session request schema"""

    mode: AgentMode | None = AgentMode.AGENT
    message: str | None = None  # Phase 4 P0: Initial message for intent classification
    require_fresh_sandbox: bool = True
    sandbox_wait_seconds: float = 3.0


class ChatRequest(BaseModel):
    """Chat request schema"""

    timestamp: int | None = None
    message: str | None = None
    attachments: list[dict] | None = None
    event_id: str | None = None
    skills: list[str] | None = None
    deep_research: bool | None = None  # Enable deep research mode (parallel wide_research)
    follow_up: dict[str, str] | None = None  # Follow-up context from suggestion clicks


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
    """Sandbox connection info for optimistic VNC connection (Phase 4)"""

    sandbox_id: str
    vnc_url: str | None = None
    status: str = "initializing"


class CreateSessionResponse(BaseModel):
    """Create session response schema"""

    session_id: str
    mode: AgentMode = AgentMode.AGENT
    sandbox: SandboxInfo | None = None  # Phase 4: Early sandbox info for optimistic VNC
    status: SessionStatus = SessionStatus.PENDING


class GetSessionResponse(BaseModel):
    """Get session response schema"""

    session_id: str
    title: str | None = None
    status: SessionStatus
    events: list[AgentSSEEvent] = []
    is_shared: bool = False
    openreplay_session_id: str | None = None
    openreplay_session_url: str | None = None


class ListSessionItem(BaseModel):
    """List session item schema"""

    session_id: str
    title: str | None = None
    latest_message: str | None = None
    latest_message_at: int | None = None
    status: SessionStatus
    unread_message_count: int
    is_shared: bool = False
    openreplay_session_id: str | None = None
    openreplay_session_url: str | None = None


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
    openreplay_session_id: str | None = None
    openreplay_session_url: str | None = None


class OpenReplaySessionRequest(BaseModel):
    """Link OpenReplay session metadata to a Pythinker session"""

    openreplay_session_id: str
    openreplay_session_url: str | None = None


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
