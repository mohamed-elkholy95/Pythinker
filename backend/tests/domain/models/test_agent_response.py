"""Tests for agent response structured output models."""

import pytest
from pydantic import ValidationError

from app.domain.models.agent_response import (
    ExecutionStepResult,
    PlanResponse,
    PlanUpdateResponse,
    StepResponse,
)


@pytest.mark.unit
class TestStepResponse:
    def test_construction(self) -> None:
        step = StepResponse(id="s1", description="Research the topic")
        assert step.id == "s1"
        assert step.description == "Research the topic"

    def test_frozen(self) -> None:
        step = StepResponse(id="s1", description="test")
        with pytest.raises(ValidationError):
            step.id = "s2"


@pytest.mark.unit
class TestPlanResponse:
    def test_construction(self) -> None:
        plan = PlanResponse(
            goal="Research AI trends",
            title="AI Research",
            steps=[StepResponse(id="s1", description="Search")],
        )
        assert plan.goal == "Research AI trends"
        assert plan.title == "AI Research"
        assert len(plan.steps) == 1
        assert plan.language == "en"

    def test_default_language(self) -> None:
        plan = PlanResponse(goal="Test", title="T", steps=[])
        assert plan.language == "en"

    def test_optional_message(self) -> None:
        plan = PlanResponse(goal="Test", title="T", steps=[], message="Starting now")
        assert plan.message == "Starting now"


@pytest.mark.unit
class TestPlanUpdateResponse:
    def test_construction(self) -> None:
        update = PlanUpdateResponse(
            steps=[StepResponse(id="s2", description="Next step")],
        )
        assert len(update.steps) == 1

    def test_empty_steps(self) -> None:
        update = PlanUpdateResponse(steps=[])
        assert update.steps == []


@pytest.mark.unit
class TestExecutionStepResult:
    def test_construction_success(self) -> None:
        result = ExecutionStepResult(
            success=True,
            result="Completed research on topic",
        )
        assert result.result == "Completed research on topic"
        assert result.success is True
        assert result.error is None
        assert result.attachments == []

    def test_construction_failure(self) -> None:
        result = ExecutionStepResult(success=False, error="Timeout exceeded")
        assert result.success is False
        assert result.error == "Timeout exceeded"
