"""Context memory model for file-system-as-context pattern.

This module implements the externalized memory pattern from Pythinker AI architecture,
where the sandbox file system serves as the agent's working memory.

This pattern enables:
- Bypassing context window limits by storing context in files
- Persistent memory across conversation turns
- Attention manipulation via todo.md pattern
- Clear separation of different context types (goals, todos, state, knowledge)
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContextType(str, Enum):
    """Types of externalized context.

    Each type represents a different aspect of the agent's working memory:
    - GOAL: High-level objectives the agent is trying to achieve
    - TODO: Current task checklist (implements the todo.md attention pattern)
    - STATE: Current execution state and progress
    - KNOWLEDGE: Accumulated knowledge base from research and exploration
    - RESEARCH: Research findings and gathered information
    """

    GOAL = "goal"
    TODO = "todo"
    STATE = "state"
    KNOWLEDGE = "knowledge"
    RESEARCH = "research"


class ContextMemory(BaseModel):
    """Externalized memory stored in sandbox file system.

    This model represents a piece of context that can be:
    1. Stored in the sandbox file system for persistence
    2. Loaded into the agent's prompt for attention
    3. Updated as the task progresses

    The file-system-as-context pattern allows the agent to:
    - Work with context larger than the LLM's context window
    - Maintain state across multiple API calls
    - Prioritize what information gets attention via the priority field
    """

    session_id: str = Field(..., description="Session this context belongs to")
    context_type: ContextType = Field(..., description="Type of context")
    content: str = Field(..., description="The actual context content")
    priority: int = Field(default=0, description="Priority for attention (higher = more important)")
    file_path: str | None = Field(default=None, description="Path in sandbox if persisted")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage.

        Returns:
            Dictionary representation suitable for MongoDB or JSON storage.
        """
        return {
            "session_id": self.session_id,
            "context_type": self.context_type.value,
            "content": self.content,
            "priority": self.priority,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextMemory":
        """Deserialize from storage.

        Args:
            data: Dictionary representation from storage.

        Returns:
            ContextMemory instance.
        """
        return cls(
            session_id=data["session_id"],
            context_type=ContextType(data["context_type"]),
            content=data["content"],
            priority=data.get("priority", 0),
            file_path=data.get("file_path"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
