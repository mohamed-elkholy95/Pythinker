"""Domain models for offline prompt optimization runs and training cases.

These models represent the lifecycle of a DSPy/GEPA optimization job:
  OptimizationCase  → normalized training/eval example
  OptimizationRun   → metadata for one optimizer run (GEPA or MIPROv2)
  OptimizationScore → scalar + feedback produced by the scorer
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.prompt_profile import PromptTarget


class OptimizerType(str, Enum):
    """Which DSPy optimizer algorithm to use."""

    GEPA = "gepa"
    MIPROV2 = "miprov2"
    MIPROV2_LIGHT = "miprov2_light"


class OptimizationRunStatus(str, Enum):
    """Lifecycle state of an optimization run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CaseSplit(str, Enum):
    """Dataset split assignment."""

    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class OptimizationCaseInput(BaseModel):
    """Normalized input payload for a planner or execution case."""

    user_request: str
    step_description: str = ""
    available_tools: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class OptimizationCaseExpected(BaseModel):
    """Expected constraints used by the scorer to compute the case score."""

    must_call_tools: list[str] = Field(default_factory=list)
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    min_citations: int = 0
    min_steps: int = 0
    max_steps: int = 0  # 0 = no limit
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class OptimizationCase(BaseModel):
    """Normalized training/eval example for the optimizer.

    Each case is converted to a ``dspy.Example`` with individual input fields
    matching the program signature (``user_request``, ``available_tools``, etc.).
    The split field controls whether the case is used for training, validation,
    or held-out testing.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target: PromptTarget
    input: OptimizationCaseInput
    expected: OptimizationCaseExpected
    labels: dict[str, str | float | bool | None] = Field(default_factory=dict)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    split: CaseSplit = CaseSplit.TRAIN
    source_session_id: str | None = None

    def to_request_payload(self) -> dict[str, str | int | float | bool | list[str] | None]:
        """Flatten inputs into a single dict for DSPy Example construction."""
        return {
            "user_request": self.input.user_request,
            "step_description": self.input.step_description,
            "available_tools": self.input.available_tools,
            "attachments": self.input.attachments,
            "target": self.target.value,
            **self.input.extra,
        }


class OptimizationScore(BaseModel):
    """Scalar score + textual feedback for a GEPA metric call.

    GEPA requires the metric to return rich feedback as
    ``dspy.Prediction(score=..., feedback=...)``.
    """

    score: float  # 0.0 .. 1.0
    feedback: str
    components: dict[str, float] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Derived pass/fail threshold (not serialized to DB)."""
        return self.score >= 0.6


class OptimizationRun(BaseModel):
    """Metadata record for a single optimizer invocation.

    One run covers one target (planner|execution|system) and one optimizer
    algorithm.  After completion it points to a GridFS artifact (the
    serialized DSPy program) and optionally to the published PromptProfile.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target: PromptTarget
    optimizer: OptimizerType = OptimizerType.MIPROV2
    status: OptimizationRunStatus = OptimizationRunStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    # Dataset stats
    train_cases: int = 0
    val_cases: int = 0
    test_cases: int = 0

    # Quality metrics
    baseline_score: float | None = None
    optimized_score: float | None = None

    # Artifacts
    artifact_id: str | None = None  # GridFS artifact ID (serialized DSPy program)
    profile_id: str | None = None  # Published PromptProfile ID (if promoted)

    # Run configuration snapshot
    config: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)

    @property
    def improvement(self) -> float | None:
        """Derived improvement delta (not serialized — computed on access)."""
        if self.baseline_score is not None and self.optimized_score is not None:
            return self.optimized_score - self.baseline_score
        return None

    def mark_started(self) -> None:
        self.started_at = datetime.now(UTC)
        self.status = OptimizationRunStatus.RUNNING

    def mark_completed(
        self,
        *,
        baseline_score: float,
        optimized_score: float,
        artifact_id: str,
    ) -> None:
        self.completed_at = datetime.now(UTC)
        self.status = OptimizationRunStatus.COMPLETED
        self.baseline_score = baseline_score
        self.optimized_score = optimized_score
        self.artifact_id = artifact_id

    def mark_failed(self, error: str) -> None:
        self.completed_at = datetime.now(UTC)
        self.status = OptimizationRunStatus.FAILED
        self.error = error
