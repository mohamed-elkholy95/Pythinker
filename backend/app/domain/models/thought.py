"""
Thought domain models for Chain-of-Thought reasoning.

This module defines structured representations of reasoning processes,
enabling explicit step-by-step thinking before agent decisions.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ThoughtType(str, Enum):
    """Types of thoughts in a reasoning chain."""

    OBSERVATION = "observation"  # Noting facts from context
    ANALYSIS = "analysis"  # Breaking down the problem
    HYPOTHESIS = "hypothesis"  # Forming tentative conclusions
    INFERENCE = "inference"  # Drawing logical conclusions
    EVALUATION = "evaluation"  # Assessing options or outcomes
    DECISION = "decision"  # Final decision point
    REFLECTION = "reflection"  # Meta-cognitive observation
    UNCERTAINTY = "uncertainty"  # Acknowledging unknowns


class ThoughtQuality(str, Enum):
    """Quality assessment of a thought."""

    HIGH = "high"  # Well-supported, clear reasoning
    MEDIUM = "medium"  # Reasonable but could be stronger
    LOW = "low"  # Weak support or unclear reasoning
    UNCERTAIN = "uncertain"  # Cannot assess quality


class Thought(BaseModel):
    """A single thought in a reasoning chain.

    Represents an atomic reasoning step with its type, content,
    and quality assessment.
    """

    id: str = Field(default_factory=lambda: f"thought_{datetime.now(UTC).timestamp()}")
    type: ThoughtType
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    quality: ThoughtQuality = ThoughtQuality.MEDIUM
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)  # IDs of thoughts this depends on
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_high_quality(self) -> bool:
        """Check if this thought is high quality with good confidence."""
        return self.quality == ThoughtQuality.HIGH and self.confidence >= 0.7

    def has_evidence(self) -> bool:
        """Check if this thought has supporting evidence."""
        return len(self.supporting_evidence) > 0

    def is_contested(self) -> bool:
        """Check if this thought has contradicting evidence."""
        return len(self.contradicting_evidence) > 0


class ReasoningStep(BaseModel):
    """A step in structured reasoning with multiple thoughts.

    Groups related thoughts together for a coherent reasoning step.
    """

    id: str = Field(default_factory=lambda: f"step_{datetime.now(UTC).timestamp()}")
    name: str  # e.g., "Problem Analysis", "Option Evaluation"
    thoughts: list[Thought] = Field(default_factory=list)
    conclusion: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    is_complete: bool = False

    def add_thought(self, thought: Thought) -> None:
        """Add a thought to this step."""
        self.thoughts.append(thought)

    def get_average_confidence(self) -> float:
        """Calculate average confidence across all thoughts."""
        if not self.thoughts:
            return 0.0
        return sum(t.confidence for t in self.thoughts) / len(self.thoughts)

    def get_high_quality_thoughts(self) -> list[Thought]:
        """Get only high-quality thoughts from this step."""
        return [t for t in self.thoughts if t.is_high_quality()]


class ThoughtChain(BaseModel):
    """A complete chain of reasoning for a problem.

    Represents the full thinking process from problem to decision,
    with explicit reasoning steps and traceability.
    """

    id: str = Field(default_factory=lambda: f"chain_{datetime.now(UTC).timestamp()}")
    problem: str  # The original problem/question
    context: dict[str, Any] = Field(default_factory=dict)
    steps: list[ReasoningStep] = Field(default_factory=list)
    final_decision: str | None = None
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_step(self, step: ReasoningStep) -> None:
        """Add a reasoning step to the chain."""
        self.steps.append(step)

    def get_all_thoughts(self) -> list[Thought]:
        """Get all thoughts across all steps."""
        return [thought for step in self.steps for thought in step.thoughts]

    def get_thoughts_by_type(self, thought_type: ThoughtType) -> list[Thought]:
        """Get all thoughts of a specific type."""
        return [t for t in self.get_all_thoughts() if t.type == thought_type]

    def get_uncertainties(self) -> list[Thought]:
        """Get all uncertainty-type thoughts (things we don't know)."""
        return self.get_thoughts_by_type(ThoughtType.UNCERTAINTY)

    def get_decisions(self) -> list[Thought]:
        """Get all decision-type thoughts."""
        return self.get_thoughts_by_type(ThoughtType.DECISION)

    def calculate_overall_confidence(self) -> float:
        """Calculate overall confidence based on all steps."""
        if not self.steps:
            return 0.0

        step_confidences = [step.get_average_confidence() for step in self.steps]
        return sum(step_confidences) / len(step_confidences)

    def is_complete(self) -> bool:
        """Check if the chain has a final decision."""
        return self.final_decision is not None and self.completed_at is not None

    def has_high_uncertainty(self) -> bool:
        """Check if there are significant uncertainties."""
        uncertainties = self.get_uncertainties()
        return len(uncertainties) >= 2 or any(u.confidence < 0.3 for u in uncertainties)

    def get_summary(self) -> str:
        """Get a summary of the reasoning chain."""
        lines = [f"Problem: {self.problem[:100]}..."]

        for step in self.steps:
            lines.append(f"\n{step.name}:")
            lines.extend(
                f"  - [{thought.type.value}] {thought.content[:80]}..."
                for thought in step.thoughts[:3]  # Limit to 3 thoughts per step
            )

            if step.conclusion:
                lines.append(f"  Conclusion: {step.conclusion[:100]}")

        if self.final_decision:
            lines.append(f"\nFinal Decision: {self.final_decision}")

        lines.append(f"Overall Confidence: {self.overall_confidence:.2f}")
        return "\n".join(lines)


class Decision(BaseModel):
    """A decision extracted from a thought chain.

    Represents the actionable outcome of reasoning with
    supporting rationale and confidence.
    """

    id: str = Field(default_factory=lambda: f"decision_{datetime.now(UTC).timestamp()}")
    action: str  # What to do
    rationale: str  # Why to do it
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives_considered: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    source_chain_id: str | None = None  # Reference to the thought chain
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_high_confidence(self) -> bool:
        """Check if this decision has high confidence (>0.8)."""
        return self.confidence > 0.8

    def is_medium_confidence(self) -> bool:
        """Check if this decision has medium confidence (0.5-0.8)."""
        return 0.5 <= self.confidence <= 0.8

    def is_low_confidence(self) -> bool:
        """Check if this decision has low confidence (<0.5)."""
        return self.confidence < 0.5

    def requires_verification(self) -> bool:
        """Check if this decision should be verified before execution."""
        return self.is_medium_confidence() or len(self.risks) > 0

    def requires_user_confirmation(self) -> bool:
        """Check if this decision requires user confirmation."""
        return self.is_low_confidence()


class ValidationResult(BaseModel):
    """Result of validating a reasoning chain."""

    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

    def has_critical_issues(self) -> bool:
        """Check if there are critical validation issues."""
        return not self.is_valid and len(self.issues) > 0
