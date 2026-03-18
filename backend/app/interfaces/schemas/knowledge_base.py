"""API schemas for knowledge base endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class CreateKnowledgeBaseRequest(BaseModel):
    """Request body for creating a knowledge base."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class KnowledgeBaseResponse(BaseModel):
    """Response schema for a knowledge base."""

    id: str
    name: str
    description: str
    status: str
    document_count: int
    storage_path: str
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    """Response schema for a knowledge document."""

    id: str
    knowledge_base_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    chunk_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class QueryKnowledgeBaseRequest(BaseModel):
    """Request body for querying a knowledge base."""

    query: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default="naive", pattern="^(hybrid|local|global|naive|mix)$")


class QueryResponse(BaseModel):
    """Response schema for a knowledge base query."""

    answer: str
    sources: list[str]
    query_time_ms: float
    mode: str
