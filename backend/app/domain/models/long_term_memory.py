"""Long-term memory models for cross-session knowledge persistence.

This module defines the data structures for storing and retrieving
memories across agent sessions, enabling:
- User preference learning
- Project context retention
- Task outcome history
- Entity and fact extraction
"""

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Types of memories that can be stored."""

    FACT = "fact"  # Extracted factual information
    PREFERENCE = "preference"  # User preferences learned over time
    ENTITY = "entity"  # Named entities (people, places, projects)
    TASK_OUTCOME = "task_outcome"  # Results of completed tasks
    CONVERSATION = "conversation"  # Important conversation snippets
    PROCEDURE = "procedure"  # How-to knowledge / procedures
    ERROR_PATTERN = "error_pattern"  # Common errors and solutions
    PROJECT_CONTEXT = "project"  # Project-specific information


class MemoryImportance(str, Enum):
    """Importance levels for memory prioritization."""

    CRITICAL = "critical"  # Must always retrieve (e.g., user allergies)
    HIGH = "high"  # Important for task quality
    MEDIUM = "medium"  # Useful context
    LOW = "low"  # Nice to have


class MemorySource(str, Enum):
    """Source of the memory."""

    USER_EXPLICIT = "user_explicit"  # User directly stated
    USER_INFERRED = "user_inferred"  # Inferred from user behavior
    TASK_RESULT = "task_result"  # From completed task
    SYSTEM = "system"  # System-generated
    EXTERNAL = "external"  # From external source


class MemoryEntry(BaseModel):
    """A single memory entry in long-term storage.

    Memories are stored with embeddings for semantic retrieval
    and metadata for filtering and relevance scoring.
    """

    id: str = Field(description="Unique identifier for this memory")
    user_id: str = Field(description="User who owns this memory")

    # Core content
    content: str = Field(description="The memory content (text)")
    memory_type: MemoryType = Field(description="Type of memory")
    importance: MemoryImportance = Field(default=MemoryImportance.MEDIUM)
    source: MemorySource = Field(default=MemorySource.SYSTEM)

    # Semantic search
    embedding: list[float] | None = Field(default=None, description="Vector embedding for semantic search")
    keywords: list[str] = Field(default_factory=list, description="Extracted keywords for keyword search")

    # Context and relationships
    session_id: str | None = Field(default=None, description="Session where memory was created")
    related_memories: list[str] = Field(default_factory=list, description="IDs of related memories")
    entities: list[str] = Field(default_factory=list, description="Named entities mentioned in this memory")
    tags: list[str] = Field(default_factory=list, description="User or system tags")

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    context: str | None = Field(default=None, description="Context in which memory was created")

    # Timestamps and lifecycle
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime | None = Field(default=None)
    access_count: int = Field(default=0, description="Times this memory was retrieved")

    # Validity
    expires_at: datetime | None = Field(default=None, description="When this memory expires (None = never)")
    is_active: bool = Field(default=True)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in this memory's accuracy")

    def content_hash(self) -> str:
        """Generate hash of content for deduplication."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def is_expired(self) -> bool:
        """Check if memory has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def record_access(self) -> None:
        """Record that this memory was accessed."""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1


class MemoryQuery(BaseModel):
    """Query parameters for memory retrieval."""

    user_id: str = Field(description="User to query memories for")

    # Search methods (at least one required)
    query_text: str | None = Field(default=None, description="Semantic search query")
    keywords: list[str] = Field(default_factory=list, description="Keyword filter")
    entity_filter: list[str] = Field(default_factory=list, description="Filter by entities")
    tag_filter: list[str] = Field(default_factory=list, description="Filter by tags")

    # Type filters
    memory_types: list[MemoryType] = Field(default_factory=list, description="Filter by memory types")
    min_importance: MemoryImportance | None = Field(default=None, description="Minimum importance level")

    # Time filters
    created_after: datetime | None = Field(default=None)
    created_before: datetime | None = Field(default=None)
    accessed_after: datetime | None = Field(default=None)

    # Pagination
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    # Scoring
    min_relevance: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum relevance score for semantic search")
    include_expired: bool = Field(default=False)


class MemorySearchResult(BaseModel):
    """Result from a memory search."""

    memory: MemoryEntry
    relevance_score: float = Field(ge=0.0, le=1.0, description="Relevance to query (1.0 = perfect match)")
    match_type: str = Field(description="How this result matched (semantic, keyword, exact)")


class MemoryBatch(BaseModel):
    """Batch of memories for bulk operations."""

    memories: list[MemoryEntry] = Field(default_factory=list)
    total_count: int = Field(default=0)
    has_more: bool = Field(default=False)


class MemoryStats(BaseModel):
    """Statistics about a user's memory store."""

    user_id: str
    total_memories: int = 0
    active_memories: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_importance: dict[str, int] = Field(default_factory=dict)
    oldest_memory: datetime | None = None
    newest_memory: datetime | None = None
    most_accessed: str | None = None  # ID of most accessed memory


class MemoryUpdate(BaseModel):
    """Update payload for modifying a memory."""

    content: str | None = None
    importance: MemoryImportance | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None
    confidence: float | None = None
    expires_at: datetime | None = None


class ExtractedMemory(BaseModel):
    """Memory extracted from conversation or task results.

    Used by the memory extraction pipeline to propose new memories.
    """

    content: str
    memory_type: MemoryType
    importance: MemoryImportance = MemoryImportance.MEDIUM
    confidence: float = 0.8
    entities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_text: str | None = None  # Original text this was extracted from
    reasoning: str | None = None  # Why this was deemed memorable
