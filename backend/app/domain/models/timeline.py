"""Timeline models for action recording and replay."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of actions that can be recorded in the timeline."""

    # File operations
    FILE_CREATE = "file_create"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    FILE_READ = "file_read"
    FILE_MOVE = "file_move"

    # Browser operations
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_INTERACT = "browser_interact"
    BROWSER_SCREENSHOT = "browser_screenshot"
    BROWSER_AGENT = "browser_agent"

    # Terminal operations
    TERMINAL_EXECUTE = "terminal_execute"

    # Code operations
    CODE_EXECUTE = "code_execute"

    # API and external calls
    API_CALL = "api_call"
    SEARCH = "search"
    MCP_TOOL = "mcp_tool"

    # Agent cognitive actions
    THINKING = "thinking"
    PLANNING = "planning"
    VERIFICATION = "verification"
    REFLECTION = "reflection"

    # Generic tool use
    TOOL_USE = "tool_use"


class ActionStatus(str, Enum):
    """Status of a timeline action."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileChange(BaseModel):
    """Represents a file change within an action."""

    path: str
    operation: str  # "create", "edit", "delete", "move"
    content_before: str | None = None  # For edit/delete, previous content
    content_after: str | None = None  # For create/edit, new content
    diff: str | None = None  # Unified diff format for edits


class BrowserAction(BaseModel):
    """Represents a browser action within an action."""

    action_type: str  # "navigate", "click", "type", "scroll", etc.
    target: str | None = None  # CSS selector, URL, or element description
    value: str | None = None  # Input value for type actions
    screenshot_before: str | None = None  # Base64 screenshot
    screenshot_after: str | None = None  # Base64 screenshot


class TerminalCommand(BaseModel):
    """Represents a terminal command within an action."""

    command: str
    working_directory: str
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None


class ActionMetadata(BaseModel):
    """Metadata for a timeline action."""

    file_changes: list[FileChange] | None = None
    browser_actions: list[BrowserAction] | None = None
    terminal_commands: list[TerminalCommand] | None = None
    reasoning: str | None = None  # Agent's reasoning for this action
    error_message: str | None = None  # Error details if action failed


class TimelineAction(BaseModel):
    """
    Represents a single action in the timeline.
    Captures all information needed to replay and reconstruct state.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    sequence_number: int  # Ordered position in the timeline

    # Timing
    timestamp: datetime = Field(default_factory=datetime.now)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration_ms: int | None = None  # Computed from started_at and completed_at

    # Action details
    action_type: ActionType
    status: ActionStatus = ActionStatus.PENDING

    # Tool information (if this action is from a tool call)
    tool_name: str | None = None
    tool_call_id: str | None = None
    function_name: str | None = None
    function_args: dict[str, Any] | None = None
    function_result: Any | None = None

    # Rich metadata
    metadata: ActionMetadata = Field(default_factory=ActionMetadata)

    # Event association
    event_id: str | None = None  # Reference to the associated event

    def mark_completed(self, result: Any = None) -> None:
        """Mark this action as completed and calculate duration."""
        self.completed_at = datetime.now()
        self.status = ActionStatus.COMPLETED
        self.function_result = result
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)

    def mark_failed(self, error: str) -> None:
        """Mark this action as failed with error details."""
        self.completed_at = datetime.now()
        self.status = ActionStatus.FAILED
        self.metadata.error_message = error
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
