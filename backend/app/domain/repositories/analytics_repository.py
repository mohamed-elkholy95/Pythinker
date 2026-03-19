"""Repository interface for analytics and diagnostic data.

Provides access to session, tool execution, and workflow state data
for analysis purposes without coupling to infrastructure storage.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class SessionAnalytics(BaseModel):
    """Session data for analytics."""

    session_id: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ToolExecutionAnalytics(BaseModel):
    """Tool execution data for analytics."""

    session_id: str
    tool_name: str
    success: bool
    started_at: datetime | None = None
    duration_ms: float | None = None
    error_message: str | None = None
    container_cpu_percent: float | None = None
    container_memory_mb: float | None = None


class AgentDecisionAnalytics(BaseModel):
    """Agent decision data for analytics."""

    session_id: str
    decision_type: str
    selected_option: str | None = None
    led_to_error: bool = False
    timestamp: datetime | None = None


class WorkflowStateAnalytics(BaseModel):
    """Workflow state data for analytics."""

    session_id: str
    verification_loops: int = 0
    stuck_loop_detected: bool = False
    context_pressure: str | None = None
    timestamp: datetime | None = None


class AnalyticsRepository(ABC):
    """Abstract repository for analytics data access.

    Implementations should provide efficient access to historical
    data for pattern detection and root cause analysis.
    """

    @abstractmethod
    async def get_failed_sessions(
        self,
        since: datetime,
        limit: int = 100,
    ) -> list[SessionAnalytics]:
        """Get failed sessions since a given date.

        Args:
            since: Start date for query
            limit: Maximum sessions to return

        Returns:
            List of failed session analytics
        """
        ...

    @abstractmethod
    async def get_tool_executions_for_session(
        self,
        session_id: str,
    ) -> list[ToolExecutionAnalytics]:
        """Get tool executions for a session.

        Args:
            session_id: Session to query

        Returns:
            List of tool execution analytics, sorted by time
        """
        ...

    @abstractmethod
    async def get_failed_tool_executions(
        self,
        since: datetime,
        limit: int = 500,
    ) -> list[ToolExecutionAnalytics]:
        """Get failed tool executions since a given date.

        Args:
            since: Start date for query
            limit: Maximum executions to return

        Returns:
            List of failed tool execution analytics
        """
        ...

    @abstractmethod
    async def get_agent_decisions_for_session(
        self,
        session_id: str,
    ) -> list[AgentDecisionAnalytics]:
        """Get agent decisions for a session.

        Args:
            session_id: Session to query

        Returns:
            List of agent decision analytics, sorted by time
        """
        ...

    @abstractmethod
    async def get_mode_selection_decisions(
        self,
        since: datetime,
        limit: int = 500,
    ) -> list[AgentDecisionAnalytics]:
        """Get mode selection decisions since a given date.

        Args:
            since: Start date for query
            limit: Maximum decisions to return

        Returns:
            List of mode selection decision analytics
        """
        ...

    @abstractmethod
    async def get_workflow_states_for_session(
        self,
        session_id: str,
    ) -> list[WorkflowStateAnalytics]:
        """Get workflow states for a session.

        Args:
            session_id: Session to query

        Returns:
            List of workflow state analytics, sorted by time
        """
        ...

    @abstractmethod
    async def get_sessions_since(
        self,
        since: datetime,
        limit: int = 500,
    ) -> list[SessionAnalytics]:
        """Get all sessions since a given date.

        Args:
            since: Start date for query
            limit: Maximum sessions to return

        Returns:
            List of session analytics
        """
        ...

    @abstractmethod
    async def get_tool_executions_since(
        self,
        since: datetime,
        limit: int = 1000,
    ) -> list[ToolExecutionAnalytics]:
        """Get all tool executions since a given date.

        Args:
            since: Start date for query
            limit: Maximum executions to return

        Returns:
            List of tool execution analytics
        """
        ...


# ===== Module-level Repository Singleton =====

_analytics_repo: AnalyticsRepository | None = None


def set_analytics_repository(repo: AnalyticsRepository) -> None:
    """Set the global analytics repository instance.

    This should be called during application startup to inject the
    infrastructure implementation.

    Args:
        repo: AnalyticsRepository implementation to use globally
    """
    global _analytics_repo
    _analytics_repo = repo


def get_analytics_repository() -> AnalyticsRepository | None:
    """Get the global analytics repository instance.

    Returns the configured repository or None if none is configured.

    Returns:
        AnalyticsRepository implementation or None
    """
    return _analytics_repo
