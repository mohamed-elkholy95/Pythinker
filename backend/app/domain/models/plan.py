import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class PhaseType(str, Enum):
    """Phase types for the structured agent flow."""

    ALIGNMENT = "alignment"
    RESEARCH_FOUNDATION = "research_foundation"
    ANALYSIS_SYNTHESIS = "analysis_synthesis"
    REPORT_GENERATION = "report_generation"
    QUALITY_ASSURANCE = "quality_assurance"
    DELIVERY_FEEDBACK = "delivery_feedback"


class StepType(str, Enum):
    """Step type categorization for routing."""

    EXECUTION = "execution"  # Standard tool-based execution
    SELF_REVIEW = "self_review"  # LLM-only QA review (no tools)
    ALIGNMENT = "alignment"  # Goal clarification
    DELIVERY = "delivery"  # Final delivery with confidence
    FINALIZATION = "finalization"  # Report composition + verification


class ExecutionStatus(str, Enum):
    """Execution status for plan steps with enhanced state tracking."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Step failed and blocks dependent steps
    SKIPPED = "skipped"  # Step skipped due to condition or optimization

    @classmethod
    def get_status_marks(cls) -> dict[str, str]:
        """Get visual markers for UI display."""
        return {
            cls.PENDING.value: "[ ]",
            cls.RUNNING.value: "[→]",
            cls.COMPLETED.value: "[✓]",
            cls.FAILED.value: "[✗]",
            cls.BLOCKED.value: "[!]",
            cls.SKIPPED.value: "[-]",
        }

    @classmethod
    def get_active_statuses(cls) -> list[str]:
        """Get statuses that indicate step needs attention."""
        return [cls.PENDING.value, cls.RUNNING.value]

    @classmethod
    def get_terminal_statuses(cls) -> list[str]:
        """Get statuses that indicate step is done (no further action needed)."""
        return [cls.COMPLETED.value, cls.FAILED.value, cls.BLOCKED.value, cls.SKIPPED.value]

    @classmethod
    def get_success_statuses(cls) -> list[str]:
        """Get statuses that indicate successful completion."""
        return [cls.COMPLETED.value, cls.SKIPPED.value]

    @classmethod
    def get_failure_statuses(cls) -> list[str]:
        """Get statuses that indicate failure."""
        return [cls.FAILED.value, cls.BLOCKED.value]

    def is_active(self) -> bool:
        """Check if this status indicates active/pending work."""
        return self.value in self.get_active_statuses()

    def is_terminal(self) -> bool:
        """Check if this status indicates completion (success or failure)."""
        return self.value in self.get_terminal_statuses()

    def is_success(self) -> bool:
        """Check if this status indicates success."""
        return self.value in self.get_success_statuses()

    def is_failure(self) -> bool:
        """Check if this status indicates failure."""
        return self.value in self.get_failure_statuses()


class Phase(BaseModel):
    """A phase grouping multiple steps in the agent workflow."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    phase_type: PhaseType
    label: str
    description: str = ""
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    order: int = 0
    icon: str = ""  # Lucide icon name for frontend
    color: str = ""  # Tailwind color class
    step_ids: list[str] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ExecutionStatus:
        if isinstance(v, str):
            return ExecutionStatus(v)
        return v

    def is_active(self) -> bool:
        return self.status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING)

    def is_done(self) -> bool:
        return self.status.is_terminal() or self.skipped


class RetryPolicy(BaseModel):
    """Per-step retry configuration."""

    max_retries: int = 0  # 0 means no retry (fail immediately)
    backoff_seconds: float = 2.0  # Initial backoff delay
    backoff_multiplier: float = 2.0  # Exponential backoff factor
    retry_on_timeout: bool = True  # Retry on TimeoutError
    retry_on_tool_error: bool = True  # Retry on tool execution failures


class Step(BaseModel):
    """Step in a plan with enhanced status tracking."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: str | None = None
    error: str | None = None
    success: bool = False
    attachments: list[str] = Field(default_factory=list)
    # Enhanced fields
    notes: str = ""  # Additional context (e.g., why blocked)
    agent_type: str | None = None  # Which agent should handle this
    dependencies: list[str] = Field(default_factory=list)  # Step IDs this depends on
    blocked_by: str | None = None  # ID of step that caused blocking
    # Metadata for merged steps and additional context
    metadata: dict[str, Any] | None = None  # Stores merged_steps, original_descriptions, etc.
    # Phase integration
    phase_id: str | None = None  # Links to parent Phase
    step_type: StepType = StepType.EXECUTION  # Routing: execution, self_review, alignment, delivery
    # Execution control
    expected_output: str | None = None  # Description of what this step should produce
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)  # Per-step retry config

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ExecutionStatus:
        """Coerce string values to ExecutionStatus enum.

        When Steps are deserialized from MongoDB or constructed from dicts,
        the status field arrives as a plain string. Without this validator,
        Pydantic v2 emits PydanticSerializationUnexpectedValue warnings
        during JSON serialization.
        """
        if isinstance(v, str):
            return ExecutionStatus(v)
        return v

    budget_tokens: int | None = None  # Max tokens allocated for this step
    # Structured naming fields (Phase 2: 2026-02-13 plan)
    action_verb: str | None = None  # e.g., "Search", "Browse", "Analyze", "Write"
    target_object: str | None = None  # e.g., "Python 3.12 release notes"
    tool_hint: str | None = None  # e.g., "web_search", "browser", "file"

    @computed_field
    @property
    def display_label(self) -> str:
        """Generate deterministic display label from structured fields."""
        if self.action_verb and self.target_object:
            parts = [self.action_verb, self.target_object]
            if self.tool_hint:
                parts.append(f"via {self.tool_hint}")
            return " ".join(parts)
        return self.description  # Fallback to free-form

    def is_done(self) -> bool:
        """Check if step has reached a terminal state."""
        return self.status.is_terminal()

    def is_actionable(self) -> bool:
        """Check if step can be executed (pending and not blocked)."""
        return self.status == ExecutionStatus.PENDING

    def mark_blocked(self, reason: str, blocked_by: str | None = None) -> None:
        """Mark this step as blocked with a reason."""
        self.status = ExecutionStatus.BLOCKED
        self.notes = reason
        self.blocked_by = blocked_by
        self.success = False

    def mark_skipped(self, reason: str) -> None:
        """Mark this step as skipped with a reason."""
        self.status = ExecutionStatus.SKIPPED
        self.notes = reason
        self.success = True  # Skipped is considered successful

    def get_status_mark(self) -> str:
        """Get visual marker for this step's status."""
        marks = ExecutionStatus.get_status_marks()
        return marks.get(self.status.value, "[ ]")


class Plan(BaseModel):
    """Plan with steps and enhanced progress tracking."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    goal: str = ""
    language: str | None = "en"
    steps: list[Step] = Field(default_factory=list)
    phases: list[Phase] = Field(default_factory=list)
    message: str | None = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ExecutionStatus:
        if isinstance(v, str):
            return ExecutionStatus(v)
        return v

    @field_validator("result", mode="before")
    @classmethod
    def _coerce_result(cls, v: Any) -> dict[str, Any] | None:
        """Coerce string results from LLM into dict format."""
        if v is None:
            return None
        if isinstance(v, str):
            return {"message": v}
        return v

    def is_done(self) -> bool:
        """Check if plan has reached a terminal state."""
        return self.status.is_terminal()

    def get_next_step(self) -> Step | None:
        """Get next step that needs execution."""
        for step in self.steps:
            if step.is_actionable():
                return step
        return None

    def has_blocked_steps(self) -> bool:
        """Check if there are any blocked steps remaining."""
        return any(step.status == ExecutionStatus.BLOCKED for step in self.steps)

    def get_blocked_steps(self) -> list[Step]:
        """Get all currently blocked steps."""
        return [step for step in self.steps if step.status == ExecutionStatus.BLOCKED]

    def unblock_independent_steps(self) -> list[str]:
        """Unblock steps whose blocking dependency has partial results or completed.

        When a step fails but still produced partial results (non-empty result),
        its dependent steps can be unblocked back to PENDING so they can attempt
        execution with whatever data is available.

        Returns:
            List of step IDs that were unblocked
        """
        unblocked_ids: list[str] = []

        for step in self.steps:
            if step.status != ExecutionStatus.BLOCKED or not step.blocked_by:
                continue

            blocker = self.get_step_by_id(step.blocked_by)
            if not blocker:
                # Blocker no longer exists — unblock
                step.status = ExecutionStatus.PENDING
                step.notes = ""
                step.blocked_by = None
                unblocked_ids.append(step.id)
                continue

            # Unblock if blocker completed (race condition fix), skipped, or has partial results
            if blocker.status == ExecutionStatus.COMPLETED:
                step.status = ExecutionStatus.PENDING
                step.notes = ""
                step.blocked_by = None
                unblocked_ids.append(step.id)
            elif blocker.status == ExecutionStatus.SKIPPED:
                step.status = ExecutionStatus.PENDING
                step.notes = f"Unblocked: blocker {blocker.id} was skipped (error recovery)"
                step.blocked_by = None
                unblocked_ids.append(step.id)
            elif blocker.status == ExecutionStatus.FAILED and blocker.result:
                # Blocker failed but produced partial results — unblock dependents
                step.status = ExecutionStatus.PENDING
                step.notes = f"Unblocked: blocker {blocker.id} has partial results"
                step.blocked_by = None
                unblocked_ids.append(step.id)

        return unblocked_ids

    def get_running_step(self) -> Step | None:
        """Get currently running step if any."""
        for step in self.steps:
            if step.status == ExecutionStatus.RUNNING:
                return step
        return None

    def get_progress(self) -> dict[str, Any]:
        """Get progress statistics for the plan."""
        total = len(self.steps)
        if total == 0:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "blocked": 0,
                "skipped": 0,
                "pending": 0,
                "running": 0,
                "progress_pct": 0.0,
            }

        status_counts = {status.value: 0 for status in ExecutionStatus}
        for step in self.steps:
            status_counts[step.status.value] += 1

        completed = status_counts[ExecutionStatus.COMPLETED.value]
        skipped = status_counts[ExecutionStatus.SKIPPED.value]
        successful = completed + skipped
        progress_pct = (successful / total) * 100 if total > 0 else 0.0

        return {
            "total": total,
            "completed": completed,
            "failed": status_counts[ExecutionStatus.FAILED.value],
            "blocked": status_counts[ExecutionStatus.BLOCKED.value],
            "skipped": skipped,
            "pending": status_counts[ExecutionStatus.PENDING.value],
            "running": status_counts[ExecutionStatus.RUNNING.value],
            "progress_pct": progress_pct,
        }

    def format_progress_text(self) -> str:
        """Format plan progress as human-readable text.

        Includes running steps count to provide accurate progress even when
        steps are actively being executed (fixes "0/4" stall issue).
        """
        progress = self.get_progress()
        ExecutionStatus.get_status_marks()

        # Build progress string with running indicator for better visibility
        progress_parts = []
        if progress["running"] > 0:
            progress_parts.append(f"{progress['running']} running")
        progress_parts.append(f"{progress['completed']}/{progress['total']} completed")
        if progress["failed"] > 0:
            progress_parts.append(f"{progress['failed']} failed")

        lines = [
            f"Plan: {self.title or self.goal[:50]}",
            f"Progress: {', '.join(progress_parts)} ({progress['progress_pct']:.1f}%)",
            "",
        ]

        for i, step in enumerate(self.steps):
            mark = step.get_status_mark()
            lines.append(f"{i + 1}. {mark} {step.description}")
            if step.notes:
                lines.append(f"   Notes: {step.notes}")

        return "\n".join(lines)

    def mark_blocked_cascade(self, blocked_step_id: str, reason: str) -> list[str]:
        """Mark all steps that depend on a blocked step as blocked.

        Args:
            blocked_step_id: ID of the step that failed
            reason: Reason for the blocking

        Returns:
            List of step IDs that were marked as blocked
        """
        blocked_ids = []

        for step in self.steps:
            if blocked_step_id in step.dependencies and step.status == ExecutionStatus.PENDING:
                step.mark_blocked(reason=f"Blocked by step {blocked_step_id}: {reason}", blocked_by=blocked_step_id)
                blocked_ids.append(step.id)
                # Recursively block dependents
                blocked_ids.extend(self.mark_blocked_cascade(step.id, reason))

        return blocked_ids

    def infer_sequential_dependencies(self) -> None:
        """Infer sequential dependencies based on step order.

        By default, each step depends on the previous step in sequence.
        This provides basic dependency tracking for plans without explicit dependencies.
        """
        for i, step in enumerate(self.steps):
            if i > 0 and not step.dependencies:
                # Add dependency on previous step if not already set
                prev_step = self.steps[i - 1]
                step.dependencies = [prev_step.id]

    def infer_smart_dependencies(self, use_sequential_fallback: bool = False) -> None:
        """Infer dependencies based on step descriptions.

        Analyzes step descriptions to identify logical dependencies
        based on keyword patterns. Supports:
        - Previous step dependencies (most common)
        - All-previous dependencies for aggregation steps
        - Independent steps that don't need dependencies

        Args:
            use_sequential_fallback: If True, steps without detected patterns
                default to depending on the previous step. If False, they
                remain independent (useful for parallel execution).
        """
        # Patterns indicating dependency on the previous step
        previous_step_patterns = [
            "using the",
            "based on",
            "from the",
            "with the",
            "using results",
            "after",
            "once",
            "then",
            "following",
            "continue",
            "next",
            "proceed with",
            "take the",
        ]

        # Patterns indicating aggregation (depends on ALL previous steps)
        aggregation_patterns = [
            "combine",
            "summarize",
            "compile",
            "aggregate",
            "consolidate",
            "merge",
            "finalize",
            "conclude",
            "final report",
            "all findings",
            "all results",
            "everything",
        ]

        # Patterns indicating independent steps (no dependencies needed)
        independent_patterns = [
            "first,",
            "start by",
            "begin with",
            "initially",
            "to begin",
        ]

        for i, step in enumerate(self.steps):
            if step.dependencies:
                continue  # Already has explicit dependencies

            desc_lower = step.description.lower()

            # Check for independent step (typically first step)
            is_independent = any(pattern in desc_lower for pattern in independent_patterns)
            if is_independent or i == 0:
                step.dependencies = []
                continue

            # Check for aggregation pattern (depends on all previous)
            is_aggregation = any(pattern in desc_lower for pattern in aggregation_patterns)
            if is_aggregation and i > 0:
                step.dependencies = [s.id for s in self.steps[:i]]
                continue

            # Check for explicit previous-step dependency patterns
            has_previous_pattern = any(pattern in desc_lower for pattern in previous_step_patterns)
            if has_previous_pattern and i > 0:
                step.dependencies = [self.steps[i - 1].id]
                continue

            # Fallback behavior
            if use_sequential_fallback and i > 0:
                step.dependencies = [self.steps[i - 1].id]
            # else: leave dependencies empty for parallel execution

    def get_step_by_id(self, step_id: str) -> Step | None:
        """Get a step by its ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_phase_by_type(self, phase_type: PhaseType) -> Phase | None:
        """Get a phase by its type."""
        for phase in self.phases:
            if phase.phase_type == phase_type:
                return phase
        return None

    def get_phase_by_id(self, phase_id: str) -> Phase | None:
        """Get a phase by its ID."""
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        return None

    def get_steps_for_phase(self, phase_id: str) -> list[Step]:
        """Get all steps belonging to a phase."""
        return [s for s in self.steps if s.phase_id == phase_id]

    def get_current_phase(self) -> Phase | None:
        """Get the currently active phase (first non-completed, non-skipped)."""
        for phase in sorted(self.phases, key=lambda p: p.order):
            if not phase.skipped and phase.status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING):
                return phase
        return None

    def advance_phase(self, phase_id: str) -> Phase | None:
        """Mark a phase as completed and return the next phase."""
        phase = self.get_phase_by_id(phase_id)
        if phase:
            phase.status = ExecutionStatus.COMPLETED
        # Return next pending phase
        return self.get_current_phase()

    def dump_json(self) -> str:
        return self.model_dump_json(include={"goal", "language", "steps"})

    def get_quality_metrics(
        self,
        user_request: str = "",
        available_tools: list[str] | None = None,
    ) -> "PlanQualityMetrics":
        """Get comprehensive quality metrics for this plan.

        Args:
            user_request: Original user request for completeness analysis
            available_tools: List of available tool names for feasibility check

        Returns:
            PlanQualityMetrics with scores across all dimensions
        """
        analyzer = PlanQualityAnalyzer(available_tools=available_tools)
        return analyzer.analyze(self, user_request)

    def validate_plan(self) -> "ValidationResult":
        """Pre-execution plan validation.

        Checks:
        - Circular dependencies
        - Orphan steps (referencing non-existent steps)
        - Empty/invalid steps

        Returns:
            ValidationResult with passed, errors[], warnings[]
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not self.steps:
            errors.append("Plan has no steps")
            return ValidationResult(passed=False, errors=errors, warnings=warnings)

        step_ids_list = [step.id for step in self.steps]
        step_ids = set(step_ids_list)
        if len(step_ids_list) != len(step_ids):
            seen = set()
            for step_id in step_ids_list:
                if step_id in seen:
                    errors.append(f"Duplicate step id detected: {step_id}")
                else:
                    seen.add(step_id)

        # Check for empty/invalid steps
        errors.extend(
            f"Step {step.id} has empty description"
            for step in self.steps
            if not step.description or not step.description.strip()
        )

        # Check for orphan dependencies (referencing non-existent steps)
        errors.extend(
            f"Step {step.id} depends on non-existent step {dep_id}"
            for step in self.steps
            for dep_id in step.dependencies
            if dep_id not in step_ids
        )

        # Check for circular dependencies using DFS
        def has_cycle(step_id: str, visited: set, rec_stack: set) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            step = self.get_step_by_id(step_id)
            if step:
                for dep_id in step.dependencies:
                    if dep_id not in visited:
                        if has_cycle(dep_id, visited, rec_stack):
                            return True
                    elif dep_id in rec_stack:
                        return True

            rec_stack.remove(step_id)
            return False

        visited: set = set()
        for step in self.steps:
            if step.id not in visited and has_cycle(step.id, visited, set()):
                errors.append(f"Circular dependency detected involving step {step.id}")
                break

        # Check for self-dependencies
        errors.extend(f"Step {step.id} depends on itself" for step in self.steps if step.id in step.dependencies)

        # Warnings for potentially problematic plans
        if len(self.steps) > 12:
            warnings.append(f"Plan has {len(self.steps)} steps, consider simplifying")

        # Check for steps with too many dependencies
        warnings.extend(
            f"Step {step.id} has {len(step.dependencies)} dependencies, may be overly complex"
            for step in self.steps
            if len(step.dependencies) > 5
        )

        return ValidationResult(passed=len(errors) == 0, errors=errors, warnings=warnings)


@dataclass
class ValidationResult:
    """Result of plan validation."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {"passed": self.passed, "errors": self.errors, "warnings": self.warnings}


class QualityDimension(str, Enum):
    """Dimensions of plan quality assessment."""

    CLARITY = "clarity"  # How clear and actionable are steps
    COMPLETENESS = "completeness"  # Does plan cover all task aspects
    STRUCTURE = "structure"  # Dependency and organization quality
    FEASIBILITY = "feasibility"  # Risk and executability
    EFFICIENCY = "efficiency"  # Optimal step count and parallelism


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""

    dimension: QualityDimension
    score: float  # 0.0-1.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        """Get letter grade for this dimension."""
        if self.score >= 0.9:
            return "A"
        if self.score >= 0.8:
            return "B"
        if self.score >= 0.7:
            return "C"
        if self.score >= 0.6:
            return "D"
        return "F"


@dataclass
class PlanQualityMetrics:
    """Comprehensive quality assessment for a plan.

    Evaluates plans across multiple dimensions:
    - Clarity: Step descriptions are clear, specific, and actionable
    - Completeness: Plan addresses all aspects of the task
    - Structure: Dependencies are well-defined, no circular refs
    - Feasibility: Steps are realistic and executable
    - Efficiency: Optimal step count, parallelism opportunities
    """

    dimensions: dict[QualityDimension, DimensionScore] = field(default_factory=dict)
    overall_score: float = 0.0
    overall_grade: str = "F"
    risk_factors: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)
    analyzed_at: str = field(default_factory=lambda: "")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "dimensions": {
                d.value: {
                    "score": ds.score,
                    "grade": ds.grade,
                    "issues": ds.issues,
                    "suggestions": ds.suggestions,
                }
                for d, ds in self.dimensions.items()
            },
            "overall_score": self.overall_score,
            "overall_grade": self.overall_grade,
            "risk_factors": self.risk_factors,
            "improvement_suggestions": self.improvement_suggestions,
            "analyzed_at": self.analyzed_at,
        }

    @property
    def needs_improvement(self) -> bool:
        """Check if plan needs improvement (score < 0.7)."""
        return self.overall_score < 0.7

    @property
    def is_high_quality(self) -> bool:
        """Check if plan is high quality (score >= 0.85)."""
        return self.overall_score >= 0.85

    @property
    def worst_dimension(self) -> DimensionScore | None:
        """Get the lowest-scoring dimension."""
        if not self.dimensions:
            return None
        return min(self.dimensions.values(), key=lambda d: d.score)


class PlanQualityAnalyzer:
    """Analyzes plan quality across multiple dimensions.

    Provides actionable feedback for improving plans before execution.
    """

    # Vague words that reduce clarity
    VAGUE_WORDS: ClassVar[list[str]] = [
        "maybe",
        "perhaps",
        "possibly",
        "somehow",
        "something",
        "stuff",
        "things",
        "etc",
        "various",
        "some",
        "certain",
        "might",
        "could be",
        "kind of",
        "sort of",
        "probably",
    ]

    # Action verbs that indicate clear, actionable steps
    ACTION_VERBS: ClassVar[list[str]] = [
        "search",
        "find",
        "read",
        "write",
        "create",
        "update",
        "delete",
        "browse",
        "navigate",
        "click",
        "extract",
        "download",
        "upload",
        "run",
        "execute",
        "install",
        "configure",
        "analyze",
        "summarize",
        "compare",
        "compile",
        "test",
        "verify",
        "validate",
        "deploy",
    ]

    # Risk indicators
    RISK_INDICATORS: ClassVar[list[str]] = [
        "if possible",
        "try to",
        "attempt",
        "hopefully",
        "delete",
        "remove",
        "overwrite",
        "force",
        "production",
        "live",
        "real data",
        "admin",
        "root",
        "sudo",
    ]

    def __init__(self, available_tools: list[str] | None = None):
        """Initialize analyzer with available tools context.

        Args:
            available_tools: List of available tool names for feasibility check
        """
        self.available_tools = set(available_tools or [])

    def analyze(self, plan: "Plan", user_request: str = "") -> PlanQualityMetrics:
        """Analyze plan quality and return comprehensive metrics.

        Args:
            plan: The plan to analyze
            user_request: Original user request for completeness check

        Returns:
            PlanQualityMetrics with scores and suggestions
        """
        from datetime import UTC, datetime

        dimensions = {}

        # Analyze each dimension
        dimensions[QualityDimension.CLARITY] = self._analyze_clarity(plan)
        dimensions[QualityDimension.COMPLETENESS] = self._analyze_completeness(plan, user_request)
        dimensions[QualityDimension.STRUCTURE] = self._analyze_structure(plan)
        dimensions[QualityDimension.FEASIBILITY] = self._analyze_feasibility(plan)
        dimensions[QualityDimension.EFFICIENCY] = self._analyze_efficiency(plan)

        # Calculate overall score (weighted average)
        weights = {
            QualityDimension.CLARITY: 0.25,
            QualityDimension.COMPLETENESS: 0.25,
            QualityDimension.STRUCTURE: 0.20,
            QualityDimension.FEASIBILITY: 0.15,
            QualityDimension.EFFICIENCY: 0.15,
        }

        overall_score = sum(dimensions[dim].score * weights[dim] for dim in dimensions)

        # Determine overall grade
        if overall_score >= 0.9:
            overall_grade = "A"
        elif overall_score >= 0.8:
            overall_grade = "B"
        elif overall_score >= 0.7:
            overall_grade = "C"
        elif overall_score >= 0.6:
            overall_grade = "D"
        else:
            overall_grade = "F"

        # Collect risk factors
        risk_factors = self._identify_risk_factors(plan)

        # Generate improvement suggestions
        improvement_suggestions = self._generate_suggestions(dimensions)

        return PlanQualityMetrics(
            dimensions=dimensions,
            overall_score=overall_score,
            overall_grade=overall_grade,
            risk_factors=risk_factors,
            improvement_suggestions=improvement_suggestions,
            analyzed_at=datetime.now(UTC).isoformat(),
        )

    def _analyze_clarity(self, plan: Plan) -> DimensionScore:
        """Analyze clarity of step descriptions."""
        issues: list[str] = []
        suggestions: list[str] = []
        scores: list[float] = []

        for step in plan.steps:
            step_score = 1.0
            desc = step.description.lower()

            # Check for vague words
            vague_count = sum(1 for v in self.VAGUE_WORDS if v in desc)
            if vague_count > 0:
                step_score -= 0.1 * min(vague_count, 3)
                issues.append(f"Step '{step.description[:30]}...' contains vague language")

            # Check for action verbs
            has_action_verb = any(v in desc for v in self.ACTION_VERBS)
            if not has_action_verb:
                step_score -= 0.15
                suggestions.append(f"Step '{step.description[:30]}...' lacks clear action verb")

            # Check description length
            word_count = len(step.description.split())
            if word_count < 3:
                step_score -= 0.2
                issues.append(f"Step '{step.description}' is too short")
            elif word_count > 50:
                step_score -= 0.1
                suggestions.append(f"Step '{step.description[:30]}...' is verbose, consider simplifying")

            # Check for specific targets
            has_specific = any(c in step.description for c in ["/", '"', "'", "http", ".py", ".md", ".json"])
            if has_specific:
                step_score += 0.05  # Bonus for specificity

            scores.append(max(0.0, min(1.0, step_score)))

        avg_score = sum(scores) / len(scores) if scores else 0.5

        return DimensionScore(
            dimension=QualityDimension.CLARITY,
            score=avg_score,
            issues=issues[:5],  # Limit to top 5
            suggestions=suggestions[:3],
        )

    def _analyze_completeness(self, plan: Plan, user_request: str) -> DimensionScore:
        """Analyze if plan covers all aspects of the task."""
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        # Check if plan has goal
        if not plan.goal or len(plan.goal) < 10:
            score -= 0.2
            issues.append("Plan lacks clear goal statement")

        # Check minimum step count
        if len(plan.steps) == 0:
            score = 0.0
            issues.append("Plan has no steps")
        elif len(plan.steps) == 1:
            score -= 0.1
            suggestions.append("Single-step plans may be oversimplified")

        # Check for output/deliverable step
        all_descs = " ".join(s.description.lower() for s in plan.steps)
        output_indicators = ["write", "create", "save", "output", "report", "summarize", "deliver"]
        has_output = any(ind in all_descs for ind in output_indicators)
        if not has_output:
            score -= 0.15
            suggestions.append("Consider adding a step to produce deliverable output")

        # Check coverage of user request keywords
        if user_request:
            request_words = set(user_request.lower().split())
            # Filter to meaningful words
            meaningful = {w for w in request_words if len(w) > 3}
            covered = sum(1 for w in meaningful if w in all_descs)
            coverage_ratio = covered / len(meaningful) if meaningful else 1.0
            if coverage_ratio < 0.5:
                score -= 0.2
                issues.append("Plan may not fully address the request")

        return DimensionScore(
            dimension=QualityDimension.COMPLETENESS,
            score=max(0.0, min(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def _analyze_structure(self, plan: Plan) -> DimensionScore:
        """Analyze structural quality of the plan."""
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        # Run validation
        validation = plan.validate_plan()
        if not validation.passed:
            score -= 0.3
            issues.extend(validation.errors[:3])

        if validation.warnings:
            score -= 0.05 * len(validation.warnings)
            suggestions.extend(validation.warnings[:2])

        # Check dependency structure
        steps_with_deps = sum(1 for s in plan.steps if s.dependencies)
        if len(plan.steps) > 2 and steps_with_deps == 0:
            score -= 0.1
            suggestions.append("Consider adding dependencies between steps")

        # Check for potential parallel execution
        independent_steps = sum(1 for s in plan.steps if not s.dependencies)
        if independent_steps > 3 and len(plan.steps) > 4:
            score -= 0.05
            suggestions.append("Many independent steps could run in parallel")

        # Check for consistent ID format
        step_ids = [s.id for s in plan.steps]
        if any("-" in sid for sid in step_ids):
            # UUID format - this is fine
            pass
        elif not all(sid.isdigit() or sid.startswith("step") for sid in step_ids):
            score -= 0.05
            issues.append("Inconsistent step ID format")

        return DimensionScore(
            dimension=QualityDimension.STRUCTURE,
            score=max(0.0, min(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def _analyze_feasibility(self, plan: Plan) -> DimensionScore:
        """Analyze feasibility and risks of the plan."""
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        all_descs = " ".join(s.description.lower() for s in plan.steps)

        # Check for risk indicators
        for risk in self.RISK_INDICATORS:
            if risk in all_descs:
                score -= 0.05
                issues.append(f"Potentially risky operation: '{risk}'")

        # Check for overly complex steps
        for step in plan.steps:
            word_count = len(step.description.split())
            if word_count > 40:
                score -= 0.05
                issues.append(f"Step '{step.description[:30]}...' may be too complex to execute atomically")

        # Check for tool availability if tools context provided
        if self.available_tools:
            tool_keywords = {
                "search": ["search", "find", "query", "look up"],
                "browser": ["browse", "navigate", "click", "visit", "webpage", "website"],
                "file": ["read", "write", "create file", "save", "open file"],
                "shell": ["run", "execute", "command", "terminal", "install", "pip", "npm"],
            }
            for tool, keywords in tool_keywords.items():
                if any(k in all_descs for k in keywords) and tool not in self.available_tools:
                    score -= 0.1
                    issues.append(f"Plan requires '{tool}' tool which may not be available")

        # Bonus for explicit error handling mentions
        if "if" in all_descs and ("fail" in all_descs or "error" in all_descs):
            score += 0.05
            suggestions.append("Good: Plan considers error scenarios")

        return DimensionScore(
            dimension=QualityDimension.FEASIBILITY,
            score=max(0.0, min(1.0, score)),
            issues=issues[:5],
            suggestions=suggestions[:2],
        )

    def _analyze_efficiency(self, plan: Plan) -> DimensionScore:
        """Analyze efficiency of the plan."""
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        step_count = len(plan.steps)

        # Check step count
        if step_count > 10:
            score -= 0.1 * ((step_count - 10) / 5)
            issues.append(f"Plan has {step_count} steps, may be overly detailed")
        elif step_count < 2 and plan.goal and len(plan.goal) > 50:
            score -= 0.1
            suggestions.append("Complex goal may need more steps")

        # Check for duplicate-looking steps
        descriptions = [s.description.lower()[:50] for s in plan.steps]
        seen = set()
        duplicates = 0
        for desc in descriptions:
            if desc in seen:
                duplicates += 1
            seen.add(desc)
        if duplicates > 0:
            score -= 0.1 * duplicates
            issues.append(f"{duplicates} potentially duplicate steps detected")

        # Check for parallelization opportunities
        max_parallel = sum(1 for s in plan.steps if not s.dependencies)
        if step_count > 3 and max_parallel > 2:
            suggestions.append(f"{max_parallel} steps could potentially run in parallel")

        # Check for sequential vs batch operations
        batch_keywords = ["each", "all", "every", "batch"]
        has_batch = any(k in plan.goal.lower() for k in batch_keywords)
        if has_batch and step_count > 5:
            score -= 0.05
            suggestions.append("Consider batching similar operations")

        return DimensionScore(
            dimension=QualityDimension.EFFICIENCY,
            score=max(0.0, min(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def _identify_risk_factors(self, plan: Plan) -> list[str]:
        """Identify risk factors in the plan."""
        risks: list[str] = []

        all_descs = " ".join(s.description.lower() for s in plan.steps)

        # Data loss risks
        if any(w in all_descs for w in ["delete", "remove", "overwrite", "truncate"]):
            risks.append("Plan involves destructive operations - ensure backups exist")

        # Permission risks
        if any(w in all_descs for w in ["sudo", "root", "admin", "permission"]):
            risks.append("Plan may require elevated permissions")

        # External dependency risks
        if any(w in all_descs for w in ["api", "external", "third-party", "download"]):
            risks.append("Plan depends on external services - consider availability")

        # Long-running risks
        if len(plan.steps) > 8:
            risks.append("Long plan may be affected by token limits or timeouts")

        # Rate limiting risks
        if all_descs.count("search") > 3 or all_descs.count("browse") > 5:
            risks.append("Multiple search/browse operations may hit rate limits")

        return risks[:5]  # Limit to top 5 risks

    def _generate_suggestions(
        self,
        dimensions: dict[QualityDimension, DimensionScore],
    ) -> list[str]:
        """Generate improvement suggestions based on dimension scores."""
        suggestions: list[str] = []

        # Prioritize suggestions from lowest-scoring dimensions
        sorted_dims = sorted(dimensions.values(), key=lambda d: d.score)

        for dim_score in sorted_dims[:3]:  # Focus on bottom 3
            if dim_score.score < 0.8:
                suggestions.extend(dim_score.suggestions)

        # Add general suggestions for low overall scores
        if all(d.score < 0.7 for d in dimensions.values()):
            suggestions.append("Consider rewriting the plan with more specific, actionable steps")

        return suggestions[:5]  # Limit to 5 suggestions
