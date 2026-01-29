"""Deep Research domain models for parallel search execution."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ResearchQueryStatus(str, Enum):
    """Individual research query status"""
    PENDING = "pending"
    SEARCHING = "searching"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class ResearchQuery(BaseModel):
    """Individual research query with status tracking"""
    id: str
    query: str
    status: ResearchQueryStatus = ResearchQueryStatus.PENDING
    result: list[dict] | None = None  # List of SearchResultItem dicts
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_event_data(self) -> dict:
        """Convert to event-compatible dict"""
        return {
            "id": self.id,
            "query": self.query,
            "status": self.status.value,
            "result": self.result,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class DeepResearchConfig(BaseModel):
    """Configuration for deep research execution"""
    queries: list[str] = Field(..., description="List of search queries to execute")
    auto_run: bool = Field(default=False, description="Skip approval and run immediately")
    max_concurrent: int = Field(default=5, ge=1, le=10, description="Maximum concurrent searches")
    timeout_per_query: int = Field(default=30, ge=5, le=120, description="Timeout per query in seconds")


class DeepResearchSession(BaseModel):
    """Deep research session state"""
    research_id: str
    session_id: str
    config: DeepResearchConfig
    queries: list[ResearchQuery]
    status: str = "pending"  # pending, awaiting_approval, started, completed, cancelled
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def completed_count(self) -> int:
        """Count of completed queries (including skipped)"""
        return sum(
            1 for q in self.queries
            if q.status in (ResearchQueryStatus.COMPLETED, ResearchQueryStatus.SKIPPED, ResearchQueryStatus.FAILED)
        )

    @property
    def total_count(self) -> int:
        """Total number of queries"""
        return len(self.queries)
