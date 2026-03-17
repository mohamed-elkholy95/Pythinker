"""Type definitions for the evaluation framework.

Defines the core data structures used throughout the evaluation system.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvalStatus(str, Enum):
    """Status of an evaluation run."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class MetricType(str, Enum):
    """Types of evaluation metrics."""

    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    SIMILARITY = "similarity"
    JSON_SCHEMA = "json_schema"
    TOOL_CALL = "tool_call"
    RESPONSE_TIME = "response_time"
    TOKEN_COUNT = "token_count"
    CUSTOM = "custom"


@dataclass
class MetricScore:
    """Score from a single metric evaluation."""

    metric_name: str
    score: float  # 0.0 to 1.0
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "score": self.score,
            "passed": self.passed,
            "details": self.details,
            "message": self.message,
        }


class EvalCase(BaseModel):
    """A single evaluation test case.

    Defines an input, expected outputs, and evaluation criteria.
    """

    # Identification
    id: str = Field(description="Unique identifier for this case")
    name: str = Field(default="", description="Human-readable name")
    description: str = Field(default="", description="Description of what's being tested")
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")

    # Input
    input: str = Field(description="The input prompt/message")
    input_context: dict[str, Any] = Field(default_factory=dict, description="Additional context for the input")
    attachments: list[str] = Field(default_factory=list)

    # Expected outputs (multiple criteria supported)
    expected_output: str | None = Field(default=None, description="Exact expected output")
    expected_output_contains: list[str] = Field(
        default_factory=list, description="Strings that should appear in output"
    )
    expected_output_not_contains: list[str] = Field(
        default_factory=list, description="Strings that should NOT appear in output"
    )
    expected_json_schema: dict[str, Any] | None = Field(default=None, description="JSON schema the output should match")
    expected_tool_calls: list[dict[str, Any]] = Field(default_factory=list, description="Expected tool calls")

    # Thresholds
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum similarity score to pass")
    max_response_time_seconds: float = Field(default=30.0, ge=0.0, description="Maximum allowed response time")
    max_tokens: int = Field(default=10000, ge=0, description="Maximum allowed tokens in response")

    # Execution configuration
    timeout_seconds: int = Field(default=60, ge=1)
    retries: int = Field(default=0, ge=0, le=3)
    skip: bool = Field(default=False, description="Skip this test case")
    skip_reason: str = Field(default="")

    # Custom evaluation function (name reference)
    custom_evaluator: str | None = Field(default=None, description="Name of custom evaluator function")

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class EvalResult:
    """Result of evaluating a single test case."""

    case_id: str
    status: EvalStatus
    actual_output: str = ""
    scores: list[MetricScore] = field(default_factory=list)
    overall_score: float = 0.0
    passed: bool = False

    # Timing
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    duration_seconds: float = 0.0

    # Resource usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    # Error information
    error: str | None = None
    error_type: str | None = None
    traceback: str | None = None

    # Raw data
    raw_response: dict[str, Any] | None = None

    def complete(self, output: str, end_time: datetime | None = None) -> None:
        """Mark the evaluation as complete."""
        self.actual_output = output
        self.end_time = end_time or datetime.now(UTC)
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()

        # Calculate overall score (average of all metric scores)
        if self.scores:
            self.overall_score = sum(s.score for s in self.scores) / len(self.scores)
            self.passed = all(s.passed for s in self.scores)
            self.status = EvalStatus.PASSED if self.passed else EvalStatus.FAILED
        else:
            self.status = EvalStatus.ERROR

    def fail(self, error: str, error_type: str = "Unknown", traceback: str = "") -> None:
        """Mark the evaluation as failed with an error."""
        self.status = EvalStatus.ERROR
        self.error = error
        self.error_type = error_type
        self.traceback = traceback
        self.passed = False
        self.end_time = datetime.now(UTC)
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status.value,
            "actual_output": self.actual_output,
            "scores": [s.to_dict() for s in self.scores],
            "overall_score": self.overall_score,
            "passed": self.passed,
            "duration_seconds": self.duration_seconds,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "error": self.error,
        }


class EvalDataset(BaseModel):
    """A collection of evaluation test cases.

    Datasets can be loaded from files or created programmatically.
    """

    # Identification
    name: str = Field(description="Dataset name")
    version: str = Field(default="1.0.0")
    description: str = Field(default="")

    # Test cases
    cases: list[EvalCase] = Field(default_factory=list)

    # Configuration
    tags: list[str] = Field(default_factory=list)
    default_timeout: int = Field(default=60)
    parallel_execution: bool = Field(default=True)
    max_parallel: int = Field(default=5)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str) -> "EvalDataset":
        """Load a dataset from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.model_validate(data)

    def to_file(self, path: str) -> None:
        """Save the dataset to a JSON file."""
        with open(path, "w") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, default=str)

    def filter_by_tags(self, tags: list[str]) -> "EvalDataset":
        """Create a new dataset with only cases matching the given tags."""
        filtered_cases = [case for case in self.cases if any(tag in case.tags for tag in tags)]
        return EvalDataset(
            name=f"{self.name}_filtered",
            version=self.version,
            description=f"Filtered by tags: {tags}",
            cases=filtered_cases,
            tags=self.tags,
            default_timeout=self.default_timeout,
            parallel_execution=self.parallel_execution,
            max_parallel=self.max_parallel,
        )

    def get_case(self, case_id: str) -> EvalCase | None:
        """Get a specific case by ID."""
        for case in self.cases:
            if case.id == case_id:
                return case
        return None


class EvalConfig(BaseModel):
    """Configuration for an evaluation run."""

    # Execution settings
    parallel: bool = Field(default=True)
    max_parallel: int = Field(default=5, ge=1, le=20)
    timeout_seconds: int = Field(default=300, ge=30)
    retries: int = Field(default=1, ge=0, le=3)

    # Metrics to run
    metrics: list[str] = Field(
        default_factory=lambda: ["contains", "response_time"], description="List of metric names to evaluate"
    )

    # Thresholds
    min_pass_rate: float = Field(default=0.8, ge=0.0, le=1.0)
    min_average_score: float = Field(default=0.7, ge=0.0, le=1.0)

    # Output settings
    verbose: bool = Field(default=False)
    save_raw_responses: bool = Field(default=True)
    output_format: str = Field(default="json")  # json, markdown, html

    # Filtering
    include_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)  # Run specific cases only

    # Comparison (for A/B testing)
    baseline_report: str | None = Field(default=None)
    comparison_threshold: float = Field(default=0.05)


@dataclass
class EvalReport:
    """Aggregated results from an evaluation run."""

    # Identification
    run_id: str
    dataset_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    # Configuration used
    config: EvalConfig | None = None

    # Results
    results: list[EvalResult] = field(default_factory=list)

    # Aggregated statistics
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    skipped_cases: int = 0

    pass_rate: float = 0.0
    average_score: float = 0.0
    total_duration_seconds: float = 0.0

    # Resource usage
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0

    # Per-metric statistics
    metric_scores: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_result(self, result: EvalResult) -> None:
        """Add a result and update statistics."""
        self.results.append(result)
        self.total_cases += 1

        if result.status == EvalStatus.PASSED:
            self.passed_cases += 1
        elif result.status == EvalStatus.FAILED:
            self.failed_cases += 1
        elif result.status == EvalStatus.ERROR:
            self.error_cases += 1
        elif result.status == EvalStatus.SKIPPED:
            self.skipped_cases += 1

        # Update token counts
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.total_tokens += result.total_tokens

        # Track per-metric scores
        for score in result.scores:
            if score.metric_name not in self.metric_scores:
                self.metric_scores[score.metric_name] = {
                    "total_score": 0.0,
                    "count": 0,
                    "passed": 0,
                    "failed": 0,
                }
            self.metric_scores[score.metric_name]["total_score"] += score.score
            self.metric_scores[score.metric_name]["count"] += 1
            if score.passed:
                self.metric_scores[score.metric_name]["passed"] += 1
            else:
                self.metric_scores[score.metric_name]["failed"] += 1

    def finalize(self) -> None:
        """Finalize the report and calculate final statistics."""
        self.completed_at = datetime.now(UTC)
        self.total_duration_seconds = (self.completed_at - self.started_at).total_seconds()

        # Calculate pass rate
        evaluated = self.total_cases - self.skipped_cases
        if evaluated > 0:
            self.pass_rate = self.passed_cases / evaluated

        # Calculate average score
        if self.results:
            scores = [r.overall_score for r in self.results if r.status != EvalStatus.SKIPPED]
            if scores:
                self.average_score = sum(scores) / len(scores)

        # Calculate per-metric averages
        for stats in self.metric_scores.values():
            if stats["count"] > 0:
                stats["average_score"] = stats["total_score"] / stats["count"]
                stats["pass_rate"] = stats["passed"] / stats["count"]

    def is_passing(self, config: EvalConfig | None = None) -> bool:
        """Check if the report meets passing criteria."""
        cfg = config or self.config or EvalConfig()
        return self.pass_rate >= cfg.min_pass_rate and self.average_score >= cfg.min_average_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dataset_name": self.dataset_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "error_cases": self.error_cases,
            "skipped_cases": self.skipped_cases,
            "pass_rate": self.pass_rate,
            "average_score": self.average_score,
            "total_duration_seconds": self.total_duration_seconds,
            "total_tokens": self.total_tokens,
            "metric_scores": self.metric_scores,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the report to JSON."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_markdown(self) -> str:
        """Generate a markdown report."""
        lines = [
            f"# Evaluation Report: {self.dataset_name}",
            "",
            f"**Run ID:** `{self.run_id}`",
            f"**Started:** {self.started_at.isoformat()}",
            f"**Duration:** {self.total_duration_seconds:.2f}s",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Cases | {self.total_cases} |",
            f"| Passed | {self.passed_cases} ({self.pass_rate * 100:.1f}%) |",
            f"| Failed | {self.failed_cases} |",
            f"| Errors | {self.error_cases} |",
            f"| Skipped | {self.skipped_cases} |",
            f"| Average Score | {self.average_score:.3f} |",
            f"| Total Tokens | {self.total_tokens:,} |",
            "",
        ]

        # Per-metric breakdown
        if self.metric_scores:
            lines.extend(
                [
                    "## Metrics Breakdown",
                    "",
                    "| Metric | Average Score | Pass Rate |",
                    "|--------|--------------|-----------|",
                ]
            )
            for name, stats in self.metric_scores.items():
                avg = stats.get("average_score", 0)
                pr = stats.get("pass_rate", 0)
                lines.append(f"| {name} | {avg:.3f} | {pr * 100:.1f}% |")
            lines.append("")

        # Failed cases
        failed = [r for r in self.results if r.status in (EvalStatus.FAILED, EvalStatus.ERROR)]
        if failed:
            lines.extend(
                [
                    "## Failed Cases",
                    "",
                ]
            )
            for r in failed[:10]:  # Show first 10
                lines.append(f"### {r.case_id}")
                lines.append("")
                lines.append(f"**Status:** {r.status.value}")
                if r.error:
                    lines.append(f"**Error:** {r.error}")
                lines.append(f"**Score:** {r.overall_score:.3f}")
                lines.append("")

        return "\n".join(lines)
