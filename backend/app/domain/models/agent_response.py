"""Structured response schemas for agent outputs.

These Pydantic models define the expected output structure from LLM calls,
enabling native JSON schema validation instead of fallback parsing strategies.
Use with OpenAI's structured output feature for type-safe responses.

All response models use ConfigDict with:
- strict=True: Reject type coercion (prevents LLM confusion)
- frozen=True: Immutable instances for safety
- extra='forbid': No extra fields allowed
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.exceptions.base import ConfigurationException


class StepResponse(BaseModel):
    """A single step in a plan."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    id: str = Field(description="Unique identifier for the step")
    description: str = Field(description="What this step will accomplish")


class PlanResponse(BaseModel):
    """Response schema for plan creation.

    Used by PlannerAgent when creating or updating execution plans.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    goal: str = Field(description="The overall objective being accomplished")
    title: str = Field(description="Short title for the plan (2-6 words)")
    language: str = Field(default="en", description="ISO language code for responses (e.g., 'en', 'zh', 'ja')")
    message: str | None = Field(default=None, description="Optional message to user about the plan")
    steps: list[StepResponse] = Field(description="Ordered list of steps to execute")


class PlanUpdateResponse(BaseModel):
    """Response schema for plan updates after step completion.

    Contains remaining steps to execute after current step completes.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    steps: list[StepResponse] = Field(description="Remaining steps to execute (may be modified based on progress)")


class ExecutionStepResult(BaseModel):
    """Response schema for step execution results.

    Used by ExecutionAgent after completing a step.
    Extra fields are ignored to tolerate LLMs that return additional
    keys (e.g. ``thinking``, ``confidence``) beyond the schema.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    success: bool = Field(description="Whether the step completed successfully")
    result: str | None = Field(default=None, description="Summary of what was accomplished in this step")
    attachments: list[str] = Field(default_factory=list, description="List of file paths created or modified")


class SummarizeResponse(BaseModel):
    """Response schema for task summarization.

    Used by ExecutionAgent when summarizing completed tasks.
    Accepts both new format (message) and legacy format (success/result) for backward compatibility.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore", populate_by_name=True)

    message: str = Field(
        default="",
        alias="result",
        description="Summary of completed work (accepts 'result' as alias for backward compatibility)",
    )
    title: str | None = Field(default=None, description="Optional title for the report")
    attachments: list[str] = Field(default_factory=list, description="List of deliverable file paths")
    suggestions: list[str] = Field(default_factory=list, description="Follow-up suggestions for the user (max 3)")

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        """Override to handle legacy format with success/result fields."""
        if isinstance(obj, dict):
            # Handle legacy format: {success: bool, result: str}
            if "result" in obj and "message" not in obj:
                obj = dict(obj)  # Make a copy
                obj["message"] = obj.get("result", "")
            # Remove success field if present (legacy format)
            if "success" in obj:
                obj = {k: v for k, v in obj.items() if k != "success"}
        return super().model_validate(obj, *args, **kwargs)


class DiscussResponse(BaseModel):
    """Response schema for discuss mode conversations.

    Used when agent is in conversational mode without task execution.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    message: str = Field(description="Response to user query")
    should_switch_to_agent: bool = Field(default=False, description="Whether this query requires agent mode execution")
    reason: str | None = Field(default=None, description="Reason for mode switch recommendation")


# ============================================================================
# Plan Verification Schemas (Phase 1: Plan-Verify-Execute)
# ============================================================================


class VerificationVerdict(str, Enum):
    """Possible verdicts from plan verification."""

    PASS = "pass"  # Plan is solid, proceed with execution
    REVISE = "revise"  # Plan has fixable issues, return for replanning
    FAIL = "fail"  # Plan is fundamentally flawed, exit gracefully


class ToolFeasibility(BaseModel):
    """Feasibility assessment for a tool in a step."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    step_id: str = Field(description="ID of the step being assessed")
    tool: str = Field(description="Tool being checked")
    feasible: bool = Field(description="Whether the tool can accomplish the step")
    reason: str = Field(description="Explanation of feasibility assessment")


class PrerequisiteCheck(BaseModel):
    """Check for a prerequisite condition."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    check: str = Field(description="What is being checked")
    satisfied: bool = Field(description="Whether the prerequisite is met")
    detail: str = Field(description="Additional details about the check")


class DependencyIssue(BaseModel):
    """An identified dependency issue in the plan."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    step_id: str = Field(description="ID of the affected step")
    depends_on: str = Field(description="What this step depends on")
    issue: str = Field(description="Description of the dependency problem")


class VerificationResponse(BaseModel):
    """Response schema for plan verification.

    Used by VerifierAgent to validate plans before execution.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    verdict: VerificationVerdict = Field(description="Verification verdict")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the verdict (0.0-1.0)")
    tool_feasibility: list[ToolFeasibility] = Field(
        default_factory=list, description="Tool feasibility assessments for each step"
    )
    prerequisite_checks: list[PrerequisiteCheck] = Field(
        default_factory=list, description="Results of prerequisite checks"
    )
    dependency_issues: list[DependencyIssue] = Field(default_factory=list, description="Identified dependency issues")
    revision_feedback: str | None = Field(
        default=None, description="Specific guidance for replanning (if verdict is 'revise')"
    )
    summary: str = Field(description="Brief explanation of the verification result")


class SimpleVerificationResponse(BaseModel):
    """Simplified verification response for quick checks."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    verdict: VerificationVerdict = Field(description="Verification verdict")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in verdict")
    summary: str = Field(description="Brief reason for the verdict")


# ============================================================================
# Reflection Schemas (Phase 2: Enhanced Self-Reflection)
# ============================================================================


class ReflectionDecision(str, Enum):
    """Possible decisions from reflection."""

    CONTINUE = "continue"  # Proceed as planned
    ADJUST_STRATEGY = "adjust"  # Minor tactical change
    REPLAN = "replan"  # Major replanning needed
    ESCALATE = "escalate"  # Need user input
    ABORT = "abort"  # Cannot complete


class ProgressMetrics(BaseModel):
    """Metrics about current execution progress."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    steps_completed: int = Field(description="Number of completed steps")
    steps_remaining: int = Field(description="Number of remaining steps")
    success_rate: float = Field(ge=0.0, le=1.0, description="Success rate of completed steps")
    estimated_progress: float = Field(ge=0.0, le=1.0, description="Estimated overall progress (0.0-1.0)")
    error_count: int = Field(default=0, description="Number of errors encountered")


class ReflectionResponse(BaseModel):
    """Response schema for reflection during execution.

    Used by ReflectionAgent to assess progress and determine next actions.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    decision: ReflectionDecision = Field(description="Reflection decision")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the decision")
    progress_assessment: str = Field(description="Assessment of current progress toward goal")
    issues_identified: list[str] = Field(default_factory=list, description="Issues identified during reflection")
    strategy_adjustment: str | None = Field(
        default=None, description="Suggested strategy adjustment (if decision is 'adjust')"
    )
    replan_reason: str | None = Field(default=None, description="Reason for replanning (if decision is 'replan')")
    user_question: str | None = Field(default=None, description="Question for user (if decision is 'escalate')")
    summary: str = Field(description="Brief summary of reflection")


# Schema registry for easy lookup
RESPONSE_SCHEMAS = {
    "plan": PlanResponse,
    "plan_update": PlanUpdateResponse,
    "execution": ExecutionStepResult,
    "summarize": SummarizeResponse,
    "discuss": DiscussResponse,
    "verification": VerificationResponse,
    "simple_verification": SimpleVerificationResponse,
    "reflection": ReflectionResponse,
}


def get_json_schema(schema_name: str) -> dict:
    """Get JSON schema for OpenAI structured output.

    Args:
        schema_name: One of 'plan', 'plan_update', 'execution', 'summarize', 'discuss'

    Returns:
        JSON schema dict compatible with OpenAI's response_format parameter
    """
    if schema_name not in RESPONSE_SCHEMAS:
        raise ConfigurationException(f"Unknown schema: {schema_name}. Available: {list(RESPONSE_SCHEMAS.keys())}")

    model = RESPONSE_SCHEMAS[schema_name]
    return {
        "type": "json_schema",
        "json_schema": {"name": schema_name, "strict": True, "schema": model.model_json_schema()},
    }
