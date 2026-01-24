"""Structured response schemas for agent outputs.

These Pydantic models define the expected output structure from LLM calls,
enabling native JSON schema validation instead of fallback parsing strategies.
Use with OpenAI's structured output feature for type-safe responses.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class StepResponse(BaseModel):
    """A single step in a plan."""
    id: str = Field(description="Unique identifier for the step")
    description: str = Field(description="What this step will accomplish")


class PlanResponse(BaseModel):
    """Response schema for plan creation.

    Used by PlannerAgent when creating or updating execution plans.
    """
    goal: str = Field(description="The overall objective being accomplished")
    title: str = Field(description="Short title for the plan (2-6 words)")
    language: str = Field(
        default="en",
        description="ISO language code for responses (e.g., 'en', 'zh', 'ja')"
    )
    message: Optional[str] = Field(
        default=None,
        description="Optional message to user about the plan"
    )
    steps: List[StepResponse] = Field(
        description="Ordered list of steps to execute"
    )


class PlanUpdateResponse(BaseModel):
    """Response schema for plan updates after step completion.

    Contains remaining steps to execute after current step completes.
    """
    steps: List[StepResponse] = Field(
        description="Remaining steps to execute (may be modified based on progress)"
    )


class ExecutionStepResult(BaseModel):
    """Response schema for step execution results.

    Used by ExecutionAgent after completing a step.
    """
    success: bool = Field(description="Whether the step completed successfully")
    result: Optional[str] = Field(
        default=None,
        description="Summary of what was accomplished in this step"
    )
    attachments: List[str] = Field(
        default_factory=list,
        description="List of file paths created or modified"
    )


class SummarizeResponse(BaseModel):
    """Response schema for task summarization.

    Used by ExecutionAgent when summarizing completed tasks.
    """
    message: str = Field(description="Summary of completed work")
    title: Optional[str] = Field(
        default=None,
        description="Optional title for the report"
    )
    attachments: List[str] = Field(
        default_factory=list,
        description="List of deliverable file paths"
    )


class DiscussResponse(BaseModel):
    """Response schema for discuss mode conversations.

    Used when agent is in conversational mode without task execution.
    """
    message: str = Field(description="Response to user query")
    should_switch_to_agent: bool = Field(
        default=False,
        description="Whether this query requires agent mode execution"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for mode switch recommendation"
    )


# Schema registry for easy lookup
RESPONSE_SCHEMAS = {
    "plan": PlanResponse,
    "plan_update": PlanUpdateResponse,
    "execution": ExecutionStepResult,
    "summarize": SummarizeResponse,
    "discuss": DiscussResponse,
}


def get_json_schema(schema_name: str) -> dict:
    """Get JSON schema for OpenAI structured output.

    Args:
        schema_name: One of 'plan', 'plan_update', 'execution', 'summarize', 'discuss'

    Returns:
        JSON schema dict compatible with OpenAI's response_format parameter
    """
    if schema_name not in RESPONSE_SCHEMAS:
        raise ValueError(f"Unknown schema: {schema_name}. Available: {list(RESPONSE_SCHEMAS.keys())}")

    model = RESPONSE_SCHEMAS[schema_name]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": model.model_json_schema()
        }
    }
