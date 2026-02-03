from pydantic import BaseModel

from app.domain.models.session import AgentMode, SessionStatus
from app.interfaces.schemas.event import AgentSSEEvent


class CreateSessionRequest(BaseModel):
    """Create session request schema"""

    mode: AgentMode | None = AgentMode.AGENT
    message: str | None = None  # Phase 4 P0: Initial message for intent classification


class ChatRequest(BaseModel):
    """Chat request schema"""

    timestamp: int | None = None
    message: str | None = None
    attachments: list[dict] | None = None
    event_id: str | None = None
    skills: list[str] | None = None
    deep_research: bool | None = None  # Enable deep research mode (parallel wide_research)


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


class ConsoleRecord(BaseModel):
    """Console record schema"""

    ps1: str
    command: str
    output: str


class ShellViewResponse(BaseModel):
    """Shell view response schema"""

    output: str
    session_id: str
    console: list[ConsoleRecord] | None = None


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
