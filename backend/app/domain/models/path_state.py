"""Path state models for Tree-of-Thoughts multi-path exploration.

These models support exploring multiple solution strategies in parallel,
scoring them, and selecting the best approach for complex tasks.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dataclasses import dataclass, field
from datetime import datetime
import uuid


class PathStatus(str, Enum):
    """Status of a path in multi-path exploration."""
    CREATED = "created"           # Path created but not started
    EXPLORING = "exploring"       # Currently being explored
    COMPLETED = "completed"       # Successfully completed
    ABANDONED = "abandoned"       # Abandoned due to low score
    FAILED = "failed"             # Failed during exploration
    SELECTED = "selected"         # Selected as the winning path


class BranchingDecision(str, Enum):
    """Decision on how to approach a task."""
    LINEAR = "linear"                       # No branching, single path
    BRANCH_STRATEGIES = "branch_strategies"  # 2-3 different approaches
    BRANCH_PARAMETERS = "branch_parameters"  # Same approach, different params
    BRANCH_VERIFICATION = "branch_verification"  # Main + verification path


@dataclass
class PathMetrics:
    """Metrics for scoring a path."""
    steps_completed: int = 0
    errors_encountered: int = 0
    tokens_consumed: int = 0
    time_elapsed_ms: float = 0
    confidence_scores: List[float] = field(default_factory=list)
    results_quality: float = 0.0  # 0.0-1.0 assessment of result quality

    @property
    def average_confidence(self) -> float:
        """Calculate average confidence across steps."""
        if not self.confidence_scores:
            return 0.5
        return sum(self.confidence_scores) / len(self.confidence_scores)

    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        total = self.steps_completed + self.errors_encountered
        if total == 0:
            return 0.0
        return self.errors_encountered / total


@dataclass
class PathState:
    """State of a single exploration path."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    strategy: str = ""  # Description of the approach being used
    status: PathStatus = PathStatus.CREATED

    # Plan for this path
    steps: List[Dict[str, Any]] = field(default_factory=list)
    current_step_index: int = 0

    # Metrics
    metrics: PathMetrics = field(default_factory=PathMetrics)

    # Results
    intermediate_results: List[Dict[str, Any]] = field(default_factory=list)
    final_result: Optional[str] = None

    # Scoring
    score: float = 0.0  # Combined score (0.0-1.0)
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def start(self) -> None:
        """Mark path as started."""
        self.status = PathStatus.EXPLORING
        self.started_at = datetime.now()

    def complete(self, final_result: str) -> None:
        """Mark path as completed."""
        self.status = PathStatus.COMPLETED
        self.final_result = final_result
        self.completed_at = datetime.now()

    def fail(self, reason: str) -> None:
        """Mark path as failed."""
        self.status = PathStatus.FAILED
        self.final_result = f"Failed: {reason}"
        self.completed_at = datetime.now()

    def abandon(self, reason: str) -> None:
        """Abandon path due to low score."""
        self.status = PathStatus.ABANDONED
        self.final_result = f"Abandoned: {reason}"
        self.completed_at = datetime.now()

    def select(self) -> None:
        """Mark path as the selected winner."""
        self.status = PathStatus.SELECTED

    def add_result(self, step_id: str, result: Any, confidence: float = 0.8) -> None:
        """Add an intermediate result."""
        self.intermediate_results.append({
            "step_id": step_id,
            "result": result,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat()
        })
        self.metrics.confidence_scores.append(confidence)
        self.metrics.steps_completed += 1

    def record_error(self) -> None:
        """Record an error."""
        self.metrics.errors_encountered += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "description": self.description,
            "strategy": self.strategy,
            "status": self.status.value,
            "score": self.score,
            "metrics": {
                "steps_completed": self.metrics.steps_completed,
                "errors": self.metrics.errors_encountered,
                "avg_confidence": self.metrics.average_confidence,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TaskComplexity(str, Enum):
    """Task complexity levels."""
    SIMPLE = "simple"        # 1-2 straightforward steps
    MODERATE = "moderate"    # 3-5 steps, single approach clear
    COMPLEX = "complex"      # 5+ steps, multiple approaches possible
    RESEARCH = "research"    # Requires exploring multiple sources/strategies


@dataclass
class ComplexityAnalysis:
    """Result of analyzing task complexity."""
    complexity: TaskComplexity
    confidence: float
    branching_decision: BranchingDecision
    suggested_strategies: List[str] = field(default_factory=list)
    reasoning: str = ""
    estimated_steps: int = 0
    estimated_token_budget: int = 0

    def should_branch(self) -> bool:
        """Determine if branching is recommended."""
        return self.branching_decision != BranchingDecision.LINEAR


class PathScoreWeights(BaseModel):
    """Weights for path scoring components."""
    result_quality: float = Field(default=0.4, ge=0.0, le=1.0)
    confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    efficiency: float = Field(default=0.2, ge=0.0, le=1.0)
    error_penalty: float = Field(default=0.15, ge=0.0, le=1.0)


@dataclass
class TreeOfThoughtsConfig:
    """Configuration for Tree-of-Thoughts exploration."""
    enabled: bool = True
    max_paths: int = 3
    min_paths: int = 2
    token_budget_per_session: int = 100000
    auto_abandon_threshold: float = 0.3  # Abandon paths below this score
    min_steps_before_abandon: int = 2  # Wait this many steps before abandoning
    budget_exhaustion_threshold: float = 0.6  # Fallback to linear at this usage
    score_weights: PathScoreWeights = field(default_factory=PathScoreWeights)
    complexity_threshold: TaskComplexity = TaskComplexity.COMPLEX  # When to use ToT
