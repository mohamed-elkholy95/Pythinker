"""
Knowledge Gap domain models for meta-cognitive awareness.

This module defines models for tracking what the agent knows
and doesn't know, enabling better self-awareness.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GapType(str, Enum):
    """Types of knowledge gaps."""

    FACTUAL = "factual"  # Missing factual information
    PROCEDURAL = "procedural"  # Missing how-to knowledge
    CONTEXTUAL = "contextual"  # Missing context/background
    TEMPORAL = "temporal"  # Information may be outdated
    CAPABILITY = "capability"  # Tool or skill limitation
    ACCESS = "access"  # Cannot access needed resource


class GapSeverity(str, Enum):
    """Severity of knowledge gaps."""

    CRITICAL = "critical"  # Blocks task completion
    HIGH = "high"  # Significantly impacts quality
    MEDIUM = "medium"  # Noticeable impact on quality
    LOW = "low"  # Minor impact, can proceed


class KnowledgeGap(BaseModel):
    """A specific gap in knowledge or capability.

    Represents something the agent doesn't know or can't do
    that may be relevant to the current task.
    """

    id: str = Field(default_factory=lambda: f"gap_{datetime.now().timestamp()}")
    gap_type: GapType
    severity: GapSeverity
    description: str
    topic: str  # The topic or area of the gap
    impact: str | None = None  # How this gap affects the task
    resolution_options: list[str] = Field(default_factory=list)
    can_be_filled: bool = True  # Whether this gap can potentially be filled
    requires_external: bool = False  # Requires external resources
    created_at: datetime = Field(default_factory=datetime.now)

    def is_blocking(self) -> bool:
        """Check if this gap blocks progress."""
        return self.severity == GapSeverity.CRITICAL

    def is_fillable_by_tool(self) -> bool:
        """Check if this gap can be filled by available tools."""
        return (
            self.can_be_filled and not self.requires_external and self.gap_type in [GapType.FACTUAL, GapType.CONTEXTUAL]
        )


class InformationRequest(BaseModel):
    """A request for information to fill a knowledge gap.

    Represents an actionable request that could resolve
    one or more knowledge gaps.
    """

    id: str = Field(default_factory=lambda: f"request_{datetime.now().timestamp()}")
    gap_ids: list[str]  # Gaps this request addresses
    request_type: str  # search, ask_user, read_file, etc.
    query: str  # The specific query/request
    priority: int = Field(default=1, ge=1, le=5)  # 1 = highest priority
    expected_info: str | None = None  # What info we expect to get
    alternative_queries: list[str] = Field(default_factory=list)


class KnowledgeDomain(BaseModel):
    """A domain of knowledge with confidence assessment.

    Tracks the agent's knowledge in a specific area
    with confidence levels and limitations.
    """

    name: str  # e.g., "Python", "Web Development", "Machine Learning"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    known_topics: list[str] = Field(default_factory=list)
    unknown_topics: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.now)

    def has_knowledge(self, topic: str) -> bool:
        """Check if the domain includes knowledge of a topic."""
        topic_lower = topic.lower()
        return any(t.lower() in topic_lower or topic_lower in t.lower() for t in self.known_topics)

    def lacks_knowledge(self, topic: str) -> bool:
        """Check if the domain explicitly lacks knowledge of a topic."""
        topic_lower = topic.lower()
        return any(t.lower() in topic_lower or topic_lower in t.lower() for t in self.unknown_topics)


class KnowledgeAssessment(BaseModel):
    """Assessment of knowledge for a specific task.

    Provides a comprehensive view of what is known and unknown
    relative to a task, with actionable gaps identified.
    """

    task: str  # The task being assessed
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    relevant_domains: list[KnowledgeDomain] = Field(default_factory=list)
    gaps: list[KnowledgeGap] = Field(default_factory=list)
    information_requests: list[InformationRequest] = Field(default_factory=list)
    can_proceed: bool = True
    blocking_gaps: list[str] = Field(default_factory=list)  # IDs of blocking gaps
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def has_critical_gaps(self) -> bool:
        """Check if there are any critical knowledge gaps."""
        return any(g.severity == GapSeverity.CRITICAL for g in self.gaps)

    def has_blocking_gaps(self) -> bool:
        """Check if there are gaps that block progress."""
        return len(self.blocking_gaps) > 0

    def get_fillable_gaps(self) -> list[KnowledgeGap]:
        """Get gaps that can potentially be filled."""
        return [g for g in self.gaps if g.can_be_filled]

    def get_tool_fillable_gaps(self) -> list[KnowledgeGap]:
        """Get gaps that can be filled by tools."""
        return [g for g in self.gaps if g.is_fillable_by_tool()]

    def get_priority_requests(self, limit: int = 3) -> list[InformationRequest]:
        """Get highest priority information requests."""
        sorted_requests = sorted(self.information_requests, key=lambda r: r.priority)
        return sorted_requests[:limit]

    def get_summary(self) -> str:
        """Get a summary of the knowledge assessment."""
        lines = [
            f"Task: {self.task[:100]}...",
            f"Overall Confidence: {self.overall_confidence:.2f}",
            f"Can Proceed: {self.can_proceed}",
            f"Knowledge Gaps: {len(self.gaps)}",
        ]

        if self.gaps:
            lines.append("\nKey Gaps:")
            lines.extend(f"  - [{gap.severity.value}] {gap.description[:60]}..." for gap in self.gaps[:3])

        if self.information_requests:
            lines.append(f"\nInformation Requests: {len(self.information_requests)}")

        return "\n".join(lines)


class CapabilityAssessment(BaseModel):
    """Assessment of agent capabilities for a task.

    Tracks what tools and capabilities are available
    and what is missing for the task.
    """

    task: str
    available_tools: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    capability_match_score: float = Field(default=0.0, ge=0.0, le=1.0)
    can_accomplish: bool = True
    workarounds: list[str] = Field(default_factory=list)

    def get_capability_coverage(self) -> float:
        """Calculate what percentage of required capabilities are available."""
        if not self.required_capabilities:
            return 1.0
        covered = len(self.required_capabilities) - len(self.missing_capabilities)
        return covered / len(self.required_capabilities)
