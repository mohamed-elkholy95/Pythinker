"""
Agent Capability domain models.

This module defines models for tracking agent capabilities
and enabling intelligent agent routing.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CapabilityCategory(str, Enum):
    """Categories of agent capabilities."""

    RESEARCH = "research"  # Information gathering, search, analysis
    CODING = "coding"  # Code generation, debugging, review
    ANALYSIS = "analysis"  # Data analysis, pattern recognition
    CREATIVE = "creative"  # Content creation, writing
    BROWSER = "browser"  # Web browsing and interaction
    FILE = "file"  # File operations
    SHELL = "shell"  # Command line operations
    PLANNING = "planning"  # Task planning and decomposition
    VERIFICATION = "verification"  # Quality assurance, validation
    COMMUNICATION = "communication"  # User interaction


class CapabilityLevel(str, Enum):
    """Proficiency levels for capabilities."""

    EXPERT = "expert"  # Highly proficient, optimal for this capability
    PROFICIENT = "proficient"  # Good capability, can handle most cases
    BASIC = "basic"  # Can perform but not optimal
    LIMITED = "limited"  # Minimal capability
    NONE = "none"  # Cannot perform


class AgentCapability(BaseModel):
    """A specific capability of an agent.

    Represents what an agent can do and how well it can do it.
    """

    name: str  # e.g., "web_research", "code_review", "data_analysis"
    category: CapabilityCategory
    level: CapabilityLevel = CapabilityLevel.PROFICIENT
    description: str = ""
    required_tools: list[str] = Field(default_factory=list)  # Tools needed for this capability
    performance_score: float = Field(default=0.5, ge=0.0, le=1.0)  # Historical performance
    usage_count: int = 0
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_suitable_for(self, task_category: CapabilityCategory) -> bool:
        """Check if this capability is suitable for a task category."""
        return self.category == task_category and self.level in [
            CapabilityLevel.EXPERT,
            CapabilityLevel.PROFICIENT,
        ]

    def update_performance(self, success: bool, duration_ms: float) -> None:
        """Update performance metrics based on usage."""
        self.usage_count += 1
        # Update success rate with exponential moving average
        alpha = 0.1
        self.success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * self.success_rate
        # Update average duration
        self.average_duration_ms = alpha * duration_ms + (1 - alpha) * self.average_duration_ms
        # Update performance score
        self.performance_score = (self.success_rate * 0.7) + (0.3 if duration_ms < 5000 else 0.15)


class AgentProfile(BaseModel):
    """Profile of an agent with its capabilities.

    Provides a comprehensive view of what an agent can do
    and its historical performance.
    """

    agent_type: str  # e.g., "planner", "executor", "critic", "researcher"
    agent_name: str  # Instance identifier
    capabilities: list[AgentCapability] = Field(default_factory=list)
    primary_category: CapabilityCategory | None = None
    max_concurrent_tasks: int = 1
    is_available: bool = True
    current_load: int = 0
    total_tasks_completed: int = 0
    overall_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_capability(self, name: str) -> AgentCapability | None:
        """Get a specific capability by name."""
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    def get_capabilities_by_category(
        self,
        category: CapabilityCategory,
    ) -> list[AgentCapability]:
        """Get all capabilities in a category."""
        return [c for c in self.capabilities if c.category == category]

    def has_capability(self, name: str, min_level: CapabilityLevel = CapabilityLevel.BASIC) -> bool:
        """Check if agent has a capability at minimum level."""
        cap = self.get_capability(name)
        if not cap:
            return False
        level_order = [
            CapabilityLevel.NONE,
            CapabilityLevel.LIMITED,
            CapabilityLevel.BASIC,
            CapabilityLevel.PROFICIENT,
            CapabilityLevel.EXPERT,
        ]
        return level_order.index(cap.level) >= level_order.index(min_level)

    def get_best_capability_for_category(
        self,
        category: CapabilityCategory,
    ) -> AgentCapability | None:
        """Get the best capability for a category."""
        caps = self.get_capabilities_by_category(category)
        if not caps:
            return None
        return max(caps, key=lambda c: c.performance_score)

    def can_take_task(self) -> bool:
        """Check if agent can take another task."""
        return self.is_available and self.current_load < self.max_concurrent_tasks

    def calculate_suitability(
        self,
        required_category: CapabilityCategory,
        required_tools: list[str] | None = None,
    ) -> float:
        """Calculate how suitable this agent is for a task.

        Args:
            required_category: The category of capability needed
            required_tools: Optional list of required tools

        Returns:
            Suitability score between 0 and 1
        """
        caps = self.get_capabilities_by_category(required_category)
        if not caps:
            return 0.0

        # Best capability score
        best_cap = max(caps, key=lambda c: c.performance_score)
        score = best_cap.performance_score

        # Availability factor
        if not self.can_take_task():
            score *= 0.5

        # Tool coverage
        if required_tools:
            available_tools = set()
            for cap in caps:
                available_tools.update(cap.required_tools)
            coverage = len(set(required_tools) & available_tools) / len(required_tools)
            score *= 0.5 + 0.5 * coverage

        return min(1.0, score)


class TaskRequirement(BaseModel):
    """Requirements for a task that needs agent assignment.

    Specifies what capabilities and resources are needed.
    """

    task_id: str
    task_description: str
    required_category: CapabilityCategory
    required_level: CapabilityLevel = CapabilityLevel.BASIC
    required_tools: list[str] = Field(default_factory=list)
    complexity: str = "medium"  # simple, medium, complex
    estimated_duration_ms: float | None = None
    priority: int = Field(default=1, ge=1, le=5)
    constraints: dict[str, Any] = Field(default_factory=dict)

    def matches_capability(self, capability: AgentCapability) -> bool:
        """Check if a capability matches this requirement."""
        if capability.category != self.required_category:
            return False

        level_order = [
            CapabilityLevel.NONE,
            CapabilityLevel.LIMITED,
            CapabilityLevel.BASIC,
            CapabilityLevel.PROFICIENT,
            CapabilityLevel.EXPERT,
        ]
        if level_order.index(capability.level) < level_order.index(self.required_level):
            return False

        # Check tool requirements
        return not (self.required_tools and not all(t in capability.required_tools for t in self.required_tools))


class AgentAssignment(BaseModel):
    """Assignment of an agent to a task."""

    task_id: str
    agent_name: str
    agent_type: str
    capability_used: str
    suitability_score: float
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    success: bool | None = None
    result_summary: str | None = None
