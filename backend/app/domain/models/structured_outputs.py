"""Structured Output Models for Zero-Hallucination Defense

Phase 4 Enhancement: Pydantic models for structured LLM outputs with validation.

These models provide:
1. Type-safe structured responses from LLMs
2. Citation tracking for source attribution
3. Confidence scoring for response reliability
4. Validation to catch malformed outputs early

Usage:
    # Parse LLM response as structured plan
    try:
        plan = PlanOutput.model_validate_json(response_content)
    except ValidationError as e:
        # Retry with validation feedback
        pass

    # Create cited response
    response = CitedResponse(
        content="Python was created by Guido van Rossum.",
        citations=[Citation(text="Python creator", source_type="web", url="https://...")],
        confidence=0.95
    )
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SourceType(str, Enum):
    """Types of citation sources."""

    WEB = "web"
    TOOL_RESULT = "tool_result"
    MEMORY = "memory"
    INFERENCE = "inference"
    USER_PROVIDED = "user_provided"
    DOCUMENT = "document"
    CODE = "code"


class Citation(BaseModel):
    """A citation for a piece of information.

    Tracks where information in the response came from,
    enabling source verification and hallucination detection.
    """

    text: str = Field(..., description="The text being cited or supported")
    source_type: SourceType = Field(..., description="Type of source")
    url: HttpUrl | None = Field(default=None, description="URL if from web source")
    source_id: str | None = Field(default=None, description="ID of source document/tool result")
    excerpt: str | None = Field(default=None, description="Relevant excerpt from source")
    page_number: int | None = Field(default=None, description="Page number if from document")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence in citation")

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v):
        """Validate URL format."""
        if v is None:
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            if not v.startswith(("http://", "https://")):
                # Try to fix common issues
                if v.startswith("www."):
                    return f"https://{v}"
                # Invalid URL, return None rather than fail
                return None
        return v


class CitedResponse(BaseModel):
    """A response with citations for source attribution.

    Enables zero-hallucination validation by tracking what
    information came from verified sources.
    """

    content: str = Field(..., description="The response content")
    citations: list[Citation] = Field(default_factory=list, description="Citations for claims")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Overall confidence")
    grounding_score: float | None = Field(default=None, description="Score from grounding validation")
    warning: str | None = Field(default=None, description="Any caveats or warnings")

    @field_validator("citations")
    @classmethod
    def validate_citations(cls, v):
        """Validate citation URLs are properly formatted."""
        for citation in v:
            if citation.url and not str(citation.url).startswith(("http://", "https://")):
                raise ValueError(f"Invalid URL in citation: {citation.url}")
        return v

    @property
    def has_citations(self) -> bool:
        """Check if response has any citations."""
        return len(self.citations) > 0

    @property
    def web_citations(self) -> list[Citation]:
        """Get only web-based citations."""
        return [c for c in self.citations if c.source_type == SourceType.WEB]

    @property
    def is_well_grounded(self) -> bool:
        """Check if response is adequately grounded in sources."""
        if not self.citations:
            return False
        if self.grounding_score is not None:
            return self.grounding_score >= 0.5
        return self.confidence >= 0.7


class StepDescription(BaseModel):
    """A single step in an execution plan."""

    description: str = Field(..., min_length=5, description="Step description")
    tool_hint: str | None = Field(default=None, description="Suggested tool to use")
    estimated_complexity: str | None = Field(
        default=None, description="Estimated complexity: low, medium, high"
    )
    dependencies: list[str] = Field(default_factory=list, description="IDs of dependent steps")
    parallel_safe: bool = Field(default=True, description="Whether step can run in parallel")

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        """Ensure description is meaningful."""
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Step description too short")
        # Check for placeholder text
        placeholder_phrases = ["todo", "tbd", "fill in", "placeholder"]
        if any(phrase in v.lower() for phrase in placeholder_phrases):
            raise ValueError("Step description appears to be a placeholder")
        return v


class PlanOutput(BaseModel):
    """Structured output for execution plans.

    Used by PlannerAgent to generate type-safe plans
    with validation for common issues.
    """

    goal: str = Field(..., description="High-level goal of the plan")
    title: str = Field(..., description="Short title for the plan")
    language: str = Field(default="en", description="Response language code")
    message: str | None = Field(default=None, description="Message to user")
    steps: list[StepDescription] = Field(..., min_length=1, description="Plan steps")
    reasoning: str | None = Field(default=None, description="Reasoning for the approach")
    estimated_complexity: str | None = Field(
        default=None, description="Overall complexity: simple, medium, complex"
    )

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v):
        """Validate plan has at least one step."""
        if not v:
            raise ValueError("Plan must have at least one step")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        """Ensure title is not empty."""
        v = v.strip()
        if not v:
            raise ValueError("Plan title cannot be empty")
        return v


class PlanUpdateOutput(BaseModel):
    """Structured output for plan updates."""

    steps: list[StepDescription] = Field(default_factory=list, description="Remaining steps")
    message: str | None = Field(default=None, description="Update message")
    completed: bool = Field(default=False, description="Whether plan is complete")


class ToolCallOutput(BaseModel):
    """Structured output for tool calls.

    Enables validation of tool arguments before execution.
    """

    tool_name: str = Field(..., description="Name of tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    reasoning: str | None = Field(default=None, description="Why this tool is being used")
    expected_outcome: str | None = Field(default=None, description="Expected result")

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v):
        """Validate tool name format."""
        v = v.strip()
        if not v:
            raise ValueError("Tool name cannot be empty")
        if " " in v:
            raise ValueError("Tool name cannot contain spaces")
        return v


class ReflectionOutput(BaseModel):
    """Structured output for reflection/self-assessment.

    Used by ReflectionAgent for type-safe decisions.
    """

    decision: str = Field(
        ..., description="Decision: continue, adjust, replan, escalate, abort"
    )
    reasoning: str = Field(..., description="Reasoning for the decision")
    adjustments: list[str] = Field(default_factory=list, description="Suggested adjustments")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence in decision")

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v):
        """Validate decision is one of allowed values."""
        allowed = {"continue", "adjust", "replan", "escalate", "abort"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"Decision must be one of: {allowed}")
        return v


class VerificationOutput(BaseModel):
    """Structured output for plan verification.

    Used by VerifierAgent for type-safe verdicts.
    """

    verdict: str = Field(..., description="Verdict: pass, revise, fail")
    feedback: str | None = Field(default=None, description="Feedback for improvement")
    issues: list[str] = Field(default_factory=list, description="Specific issues found")
    score: float = Field(default=0.5, ge=0.0, le=1.0, description="Quality score")

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v):
        """Validate verdict is one of allowed values."""
        allowed = {"pass", "revise", "fail"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"Verdict must be one of: {allowed}")
        return v


class ErrorAnalysisOutput(BaseModel):
    """Structured output for error analysis."""

    error_type: str = Field(..., description="Category of error")
    root_cause: str | None = Field(default=None, description="Root cause analysis")
    is_recoverable: bool = Field(default=True, description="Whether error is recoverable")
    suggested_action: str | None = Field(default=None, description="Suggested recovery action")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence in analysis")


class SummaryOutput(BaseModel):
    """Structured output for task summaries."""

    summary: str = Field(..., description="Task summary")
    outcome: str = Field(..., description="Outcome: success, partial, failure")
    key_results: list[str] = Field(default_factory=list, description="Key results achieved")
    remaining_items: list[str] = Field(default_factory=list, description="Unfinished items")
    citations: list[Citation] = Field(default_factory=list, description="Sources used")

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v):
        """Validate outcome is one of allowed values."""
        allowed = {"success", "partial", "failure"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"Outcome must be one of: {allowed}")
        return v


# =============================================================================
# Validation Utilities
# =============================================================================


class ValidationResult(BaseModel):
    """Result of output validation."""

    is_valid: bool = Field(..., description="Whether output is valid")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")
    suggestions: list[str] = Field(default_factory=list, description="Suggestions for improvement")


def validate_llm_output(
    content: str,
    expected_type: type[BaseModel],
) -> tuple[BaseModel | None, ValidationResult]:
    """Validate and parse LLM output as a structured type.

    Args:
        content: Raw LLM output (JSON string)
        expected_type: Pydantic model class to parse as

    Returns:
        Tuple of (parsed_model_or_none, validation_result)
    """
    errors = []
    warnings = []
    suggestions = []

    try:
        # Try to parse as JSON
        parsed = expected_type.model_validate_json(content)

        # Additional validation checks
        if hasattr(parsed, "confidence") and parsed.confidence < 0.3:
            warnings.append("Low confidence score - consider reviewing")

        if hasattr(parsed, "citations") and not parsed.citations:
            warnings.append("No citations provided - response may not be grounded")

        return parsed, ValidationResult(
            is_valid=True,
            errors=[],
            warnings=warnings,
            suggestions=suggestions,
        )

    except Exception as e:
        error_str = str(e)
        errors.append(f"Validation failed: {error_str[:200]}")

        # Generate suggestions based on error type
        if "minimum" in error_str.lower():
            suggestions.append("Ensure all required fields meet minimum length requirements")
        if "required" in error_str.lower():
            suggestions.append("Include all required fields in the response")
        if "json" in error_str.lower():
            suggestions.append("Ensure response is valid JSON format")

        return None, ValidationResult(
            is_valid=False,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )


def build_validation_feedback(result: ValidationResult) -> str:
    """Build feedback string for LLM retry.

    Args:
        result: Validation result

    Returns:
        Formatted feedback string for injection into retry prompt
    """
    parts = []

    if result.errors:
        parts.append("ERRORS (must fix):")
        for err in result.errors:
            parts.append(f"  - {err}")

    if result.suggestions:
        parts.append("\nSUGGESTIONS:")
        for sug in result.suggestions:
            parts.append(f"  - {sug}")

    return "\n".join(parts)


__all__ = [
    # Core models
    "Citation",
    "CitedResponse",
    "SourceType",
    # Agent outputs
    "PlanOutput",
    "PlanUpdateOutput",
    "StepDescription",
    "ToolCallOutput",
    "ReflectionOutput",
    "VerificationOutput",
    "ErrorAnalysisOutput",
    "SummaryOutput",
    # Validation
    "ValidationResult",
    "validate_llm_output",
    "build_validation_feedback",
]
