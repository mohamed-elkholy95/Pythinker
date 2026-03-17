import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.memory import Memory


class AgentPersona(BaseModel):
    """Persona configuration for an agent's communication style and expertise."""

    style: str = "balanced"  # reasoning style: balanced, analytical, creative, concise
    domain_expertise: list[str] = Field(default_factory=list)  # specialized domains
    communication_tone: str = "professional"  # professional, friendly, technical


class AgentPerformanceState(BaseModel):
    """Tracks runtime performance metrics for an agent."""

    tasks_completed: int = 0
    success_rate: float = 1.0
    avg_latency_ms: float = 0.0
    tool_usage_counts: dict[str, int] = Field(default_factory=dict)
    last_updated: datetime | None = None


class AgentLearningState(BaseModel):
    """Tracks learning state and preferences accumulated across tasks."""

    confidence_scores: dict[str, float] = Field(default_factory=dict)  # domain -> confidence
    preferred_strategies: list[str] = Field(default_factory=list)
    avoided_patterns: list[str] = Field(default_factory=list)


class Agent(BaseModel):
    """
    Agent aggregate root that manages the lifecycle and state of an AI agent
    Including its execution context, memory, and current plan.

    Phase 3 extensions add persona, capabilities, performance tracking,
    and cross-session learning state.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    memories: dict[str, Memory] = Field(default_factory=dict)
    model_name: str = Field(default="")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=2000)

    # Context related fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))  # Creation timestamp
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))  # Last update timestamp

    # Phase 3: Agent intelligence extensions
    persona: AgentPersona = Field(default_factory=AgentPersona)
    capabilities: list[str] = Field(default_factory=list)  # tool names this agent can use
    performance_state: AgentPerformanceState = Field(default_factory=AgentPerformanceState)
    learning_state: AgentLearningState = Field(default_factory=AgentLearningState)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Validate temperature is between 0 and 1"""
        if not 0 <= v <= 1:
            raise ValueError("Temperature must be between 0 and 1")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int | None) -> int | None:
        """Validate max_tokens is positive if provided"""
        if v is not None and v <= 0:
            raise ValueError("Max tokens must be positive")
        return v

    model_config = ConfigDict(arbitrary_types_allowed=True)
