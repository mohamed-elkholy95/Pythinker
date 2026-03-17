"""Domain models for task delegation.

Defines typed roles, lifecycle statuses, and the request/result value
objects used by DelegateTool.  All types are pure Pydantic v2 models
with no infrastructure dependencies.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DelegateRole(str, enum.Enum):
    """Typed role that scopes how a delegated subtask is executed."""

    RESEARCHER = "researcher"
    EXECUTOR = "executor"
    CODER = "coder"
    BROWSER = "browser"
    ANALYST = "analyst"
    WRITER = "writer"


class DelegateStatus(str, enum.Enum):
    """Lifecycle status of a delegated subtask."""

    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


class DelegateRequest(BaseModel):
    """Input contract for a delegation request.

    Attributes:
        task: Natural-language description of what the subtask must accomplish.
        role: Typed role that determines the execution path.
        label: Short human-readable label for tracking (defaults to empty string).
        search_types: Optional list of search provider types to restrict the
            researcher role to (e.g. ["web", "news"]).
        timeout_seconds: Maximum wall-clock seconds the subtask may run.
            Clamped between 30 s and 1 hour.
        max_turns: Maximum agent turns before the subtask is forcibly stopped.
    """

    task: str
    role: DelegateRole
    label: str = ""
    search_types: list[str] | None = None
    timeout_seconds: int = Field(default=900, ge=30, le=3600)
    max_turns: int = Field(default=50, ge=1, le=200)


class DelegateResult(BaseModel):
    """Result returned by DelegateTool after executing a delegation request.

    Attributes:
        task_id: Short identifier for the spawned subtask (12-char uuid4 prefix).
            Empty string when the request was rejected before spawning.
        status: Final lifecycle status of the subtask.
        result: Textual output produced by the subtask on success.
        error: Human-readable error description on failure or rejection.
    """

    task_id: str = ""
    status: DelegateStatus
    result: str | None = None
    error: str | None = None
