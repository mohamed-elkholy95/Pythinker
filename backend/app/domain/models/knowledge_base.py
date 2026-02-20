"""Domain models for knowledge base management."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class KnowledgeBaseStatus(str, Enum):
    """Lifecycle status of a knowledge base."""

    CREATING = "creating"
    READY = "ready"
    INDEXING = "indexing"
    ERROR = "error"


class DocumentStatus(str, Enum):
    """Processing status of an indexed document."""

    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class KnowledgeBase(BaseModel):
    """A user-owned knowledge base backed by RAG-Anything."""

    id: str
    user_id: str
    name: str
    description: str = ""
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.CREATING
    document_count: int = 0
    storage_path: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeDocument(BaseModel):
    """A document indexed into a knowledge base."""

    id: str
    knowledge_base_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus = DocumentStatus.PENDING
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeQueryResult(BaseModel):
    """Result of a knowledge base query."""

    answer: str
    sources: list[str] = Field(default_factory=list)
    query_time_ms: float = 0.0
    mode: str = "hybrid"
