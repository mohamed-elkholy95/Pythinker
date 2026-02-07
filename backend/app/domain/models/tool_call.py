"""Standardized tool call envelope for consistent tool execution tracking.

Every tool invocation flows through this envelope, providing:
- Consistent metadata (timing, status, arguments)
- Uniform logging fields
- Status lifecycle (PENDING -> RUNNING -> COMPLETED/FAILED)
"""

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolCallStatus(str, Enum):
    """Tool call lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ToolCallEnvelope(BaseModel):
    """Envelope wrapping every tool call with standardized metadata.

    Attributes:
        tool_call_id: Unique identifier for this tool call
        tool_name: Category name of the tool (browser, shell, file, etc.)
        function_name: Specific function being called
        arguments: Arguments passed to the tool
        status: Current lifecycle status
        started_at: Epoch time when execution started
        completed_at: Epoch time when execution finished
        duration_ms: Execution duration in milliseconds
        success: Whether execution succeeded
        error: Error message if failed
        result_summary: Short summary of result for logging
    """

    tool_call_id: str
    tool_name: str
    function_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: float | None = None
    success: bool | None = None
    error: str | None = None
    result_summary: str | None = None

    def mark_started(self) -> None:
        """Transition to RUNNING status."""
        self.status = ToolCallStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self, success: bool, message: str | None = None) -> None:
        """Transition to COMPLETED status with result."""
        self.status = ToolCallStatus.COMPLETED
        self.completed_at = time.time()
        self.success = success
        if self.started_at:
            self.duration_ms = round((self.completed_at - self.started_at) * 1000, 2)
        self.result_summary = message[:200] if message else None

    def mark_failed(self, error: str) -> None:
        """Transition to FAILED status with error."""
        self.status = ToolCallStatus.FAILED
        self.completed_at = time.time()
        self.success = False
        self.error = error[:500]
        if self.started_at:
            self.duration_ms = round((self.completed_at - self.started_at) * 1000, 2)

    def mark_blocked(self, reason: str) -> None:
        """Transition to BLOCKED status (security block)."""
        self.status = ToolCallStatus.BLOCKED
        self.success = False
        self.error = reason

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dict suitable for structured logging extra fields."""
        d: dict[str, Any] = {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "function_name": self.function_name,
            "status": self.status.value,
        }
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        if self.success is not None:
            d["success"] = self.success
        if self.error:
            d["error"] = self.error
        return d
