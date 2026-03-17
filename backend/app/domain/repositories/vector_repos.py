"""Domain-layer ports for vector database repositories.

Provides abstract interfaces and module-level singletons for:
- Task artifact storage/retrieval (cross-session learning)
- Tool execution log storage/retrieval (error pattern learning)
- Embedding generation (shared by all vector operations)

Infrastructure implementations are injected at startup via set_*() functions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding generation."""

    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class TaskArtifactRepository(ABC):
    """Abstract repository for task artifact vectors."""

    @abstractmethod
    async def store_task_artifact(
        self,
        artifact_id: str,
        user_id: str,
        session_id: str,
        embedding: list[float],
        artifact_type: str,
        agent_role: str = "executor",
        task_id: str | None = None,
        step_index: int | None = None,
        success: bool | None = None,
        content_summary: str = "",
    ) -> None: ...

    @abstractmethod
    async def find_similar_tasks(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int = 5,
        min_score: float = 0.5,
        artifact_types: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def delete_user_artifacts(self, user_id: str) -> None: ...


class ToolLogRepository(ABC):
    """Abstract repository for tool execution log vectors."""

    @abstractmethod
    async def log_tool_execution(
        self,
        log_id: str,
        user_id: str,
        session_id: str,
        tool_name: str,
        embedding: list[float],
        outcome: str,
        input_summary: str = "",
        error_type: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def find_similar_tool_executions(
        self,
        user_id: str,
        query_vector: list[float],
        tool_name: str | None = None,
        outcome: str | None = None,
        limit: int = 5,
        min_score: float = 0.4,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def delete_user_logs(self, user_id: str) -> None: ...


# ===== Module-level singletons =====

_task_artifact_repo: TaskArtifactRepository | None = None
_tool_log_repo: ToolLogRepository | None = None
_embedding_provider: EmbeddingProvider | None = None


def set_task_artifact_repository(repo: TaskArtifactRepository | None) -> None:
    """Set the global task artifact repository."""
    global _task_artifact_repo
    _task_artifact_repo = repo


def get_task_artifact_repository() -> TaskArtifactRepository | None:
    """Get the global task artifact repository (None if not configured)."""
    return _task_artifact_repo


def set_tool_log_repository(repo: ToolLogRepository | None) -> None:
    """Set the global tool log repository."""
    global _tool_log_repo
    _tool_log_repo = repo


def get_tool_log_repository() -> ToolLogRepository | None:
    """Get the global tool log repository (None if not configured)."""
    return _tool_log_repo


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Set the global embedding provider."""
    global _embedding_provider
    _embedding_provider = provider


def get_embedding_provider() -> EmbeddingProvider | None:
    """Get the global embedding provider (None if not configured)."""
    return _embedding_provider
