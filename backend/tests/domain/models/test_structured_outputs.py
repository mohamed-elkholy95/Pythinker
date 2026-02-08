"""Tests for Structured Output Models

Phase 4 Enhancement: Tests for Pydantic structured outputs with validation.
"""

import json

import pytest
from pydantic import ValidationError

from app.domain.models.structured_outputs import (
    Citation,
    CitedResponse,
    ErrorAnalysisOutput,
    PlanOutput,
    PlanUpdateOutput,
    ReflectionOutput,
    SourceType,
    StepDescription,
    SummaryOutput,
    ToolCallOutput,
    ValidationResult,
    VerificationOutput,
    build_validation_feedback,
    validate_llm_output,
)


class TestSourceType:
    """Tests for SourceType enum."""

    def test_source_type_values(self):
        """Test all source type values exist."""
        assert SourceType.WEB.value == "web"
        assert SourceType.TOOL_RESULT.value == "tool_result"
        assert SourceType.MEMORY.value == "memory"
        assert SourceType.INFERENCE.value == "inference"
        assert SourceType.USER_PROVIDED.value == "user_provided"
        assert SourceType.DOCUMENT.value == "document"
        assert SourceType.CODE.value == "code"


class TestCitation:
    """Tests for Citation model."""

    def test_basic_citation(self):
        """Test creating a basic citation."""
        citation = Citation(
            text="Python is a programming language",
            source_type=SourceType.WEB,
            url="https://python.org",
        )
        assert citation.text == "Python is a programming language"
        assert citation.source_type == SourceType.WEB
        assert str(citation.url) == "https://python.org/"

    def test_citation_without_url(self):
        """Test citation without URL."""
        citation = Citation(
            text="Python is great",
            source_type=SourceType.TOOL_RESULT,
            source_id="search_result_123",
        )
        assert citation.url is None
        assert citation.source_id == "search_result_123"

    def test_url_validator_www_prefix(self):
        """Test URL validator adds https to www URLs."""
        citation = Citation(
            text="Example",
            source_type=SourceType.WEB,
            url="www.example.com",
        )
        assert str(citation.url).startswith("https://")

    def test_url_validator_empty_string(self):
        """Test URL validator handles empty string."""
        citation = Citation(
            text="Example",
            source_type=SourceType.WEB,
            url="",
        )
        assert citation.url is None

    def test_url_validator_invalid_url(self):
        """Test URL validator handles invalid URL."""
        citation = Citation(
            text="Example",
            source_type=SourceType.WEB,
            url="not-a-valid-url",
        )
        assert citation.url is None

    def test_citation_confidence(self):
        """Test citation confidence bounds."""
        citation = Citation(
            text="Test",
            source_type=SourceType.INFERENCE,
            confidence=0.95,
        )
        assert citation.confidence == 0.95

    def test_citation_confidence_bounds(self):
        """Test citation confidence validation."""
        with pytest.raises(ValidationError):
            Citation(
                text="Test",
                source_type=SourceType.INFERENCE,
                confidence=1.5,  # Out of bounds
            )


class TestCitedResponse:
    """Tests for CitedResponse model."""

    def test_basic_response(self):
        """Test creating a basic cited response."""
        response = CitedResponse(
            content="Python was created by Guido van Rossum.",
            citations=[
                Citation(
                    text="created by Guido van Rossum",
                    source_type=SourceType.WEB,
                    url="https://python.org/about",
                )
            ],
            confidence=0.95,
        )
        assert response.content == "Python was created by Guido van Rossum."
        assert len(response.citations) == 1
        assert response.confidence == 0.95

    def test_has_citations_true(self):
        """Test has_citations property when citations exist."""
        response = CitedResponse(
            content="Test",
            citations=[Citation(text="Test", source_type=SourceType.INFERENCE)],
        )
        assert response.has_citations is True

    def test_has_citations_false(self):
        """Test has_citations property when no citations."""
        response = CitedResponse(content="Test")
        assert response.has_citations is False

    def test_web_citations(self):
        """Test web_citations property filters correctly."""
        response = CitedResponse(
            content="Test",
            citations=[
                Citation(text="Web", source_type=SourceType.WEB),
                Citation(text="Tool", source_type=SourceType.TOOL_RESULT),
                Citation(text="Web2", source_type=SourceType.WEB),
            ],
        )
        web_citations = response.web_citations
        assert len(web_citations) == 2
        assert all(c.source_type == SourceType.WEB for c in web_citations)

    def test_is_well_grounded_with_citations(self):
        """Test is_well_grounded with citations."""
        response = CitedResponse(
            content="Test",
            citations=[Citation(text="Test", source_type=SourceType.WEB)],
            confidence=0.8,
        )
        assert response.is_well_grounded is True

    def test_is_well_grounded_no_citations(self):
        """Test is_well_grounded without citations."""
        response = CitedResponse(content="Test", confidence=0.9)
        assert response.is_well_grounded is False

    def test_is_well_grounded_with_grounding_score(self):
        """Test is_well_grounded with explicit grounding score."""
        response = CitedResponse(
            content="Test",
            citations=[Citation(text="Test", source_type=SourceType.WEB)],
            confidence=0.3,
            grounding_score=0.7,
        )
        assert response.is_well_grounded is True


class TestStepDescription:
    """Tests for StepDescription model."""

    def test_basic_step(self):
        """Test creating a basic step."""
        step = StepDescription(
            description="Search for Python documentation",
            tool_hint="search",
        )
        assert step.description == "Search for Python documentation"
        assert step.tool_hint == "search"
        assert step.parallel_safe is True

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        step = StepDescription(
            description="Analyze search results",
            dependencies=["step_1", "step_2"],
            parallel_safe=False,
        )
        assert len(step.dependencies) == 2
        assert step.parallel_safe is False

    def test_description_too_short(self):
        """Test description validation for short text."""
        with pytest.raises(ValidationError):
            StepDescription(description="Hi")

    def test_description_placeholder_rejection(self):
        """Test description rejects placeholder text."""
        with pytest.raises(ValidationError):
            StepDescription(description="TODO: Fill in later")

        with pytest.raises(ValidationError):
            StepDescription(description="TBD placeholder step")


class TestPlanOutput:
    """Tests for PlanOutput model."""

    def test_basic_plan(self):
        """Test creating a basic plan."""
        plan = PlanOutput(
            goal="Find Python documentation",
            title="Search for Python docs",
            steps=[StepDescription(description="Search for Python documentation")],
        )
        assert plan.goal == "Find Python documentation"
        assert plan.title == "Search for Python docs"
        assert len(plan.steps) == 1

    def test_plan_with_multiple_steps(self):
        """Test plan with multiple steps."""
        plan = PlanOutput(
            goal="Build a web application",
            title="Web App Development",
            steps=[
                StepDescription(description="Set up project structure"),
                StepDescription(description="Create database schema"),
                StepDescription(description="Implement API endpoints"),
            ],
            reasoning="Breaking down into incremental steps",
            estimated_complexity="complex",
        )
        assert len(plan.steps) == 3
        assert plan.reasoning is not None
        assert plan.estimated_complexity == "complex"

    def test_plan_empty_steps(self):
        """Test plan validation rejects empty steps."""
        with pytest.raises(ValidationError):
            PlanOutput(
                goal="Test",
                title="Test Plan",
                steps=[],
            )

    def test_plan_empty_title(self):
        """Test plan validation rejects empty title."""
        with pytest.raises(ValidationError):
            PlanOutput(
                goal="Test",
                title="   ",  # Whitespace only
                steps=[StepDescription(description="Valid step")],
            )

    def test_plan_json_serialization(self):
        """Test plan can be serialized to JSON."""
        plan = PlanOutput(
            goal="Test goal",
            title="Test Plan",
            steps=[StepDescription(description="Test step description")],
        )
        json_str = plan.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["goal"] == "Test goal"
        assert len(parsed["steps"]) == 1


class TestReflectionOutput:
    """Tests for ReflectionOutput model."""

    def test_continue_decision(self):
        """Test continue decision."""
        reflection = ReflectionOutput(
            decision="continue",
            reasoning="Making good progress",
        )
        assert reflection.decision == "continue"

    def test_adjust_decision(self):
        """Test adjust decision."""
        reflection = ReflectionOutput(
            decision="adjust",
            reasoning="Need to change approach",
            adjustments=["Use different tool", "Retry with new parameters"],
        )
        assert reflection.decision == "adjust"
        assert len(reflection.adjustments) == 2

    def test_invalid_decision(self):
        """Test invalid decision validation."""
        with pytest.raises(ValidationError):
            ReflectionOutput(
                decision="invalid_decision",
                reasoning="Test",
            )

    def test_decision_case_insensitive(self):
        """Test decision validation is case insensitive."""
        reflection = ReflectionOutput(
            decision="CONTINUE",
            reasoning="Test",
        )
        assert reflection.decision == "continue"


class TestVerificationOutput:
    """Tests for VerificationOutput model."""

    def test_pass_verdict(self):
        """Test pass verdict."""
        verification = VerificationOutput(
            verdict="pass",
            score=0.9,
        )
        assert verification.verdict == "pass"
        assert verification.score == 0.9

    def test_revise_verdict(self):
        """Test revise verdict with feedback."""
        verification = VerificationOutput(
            verdict="revise",
            feedback="Missing error handling",
            issues=["No try/catch", "No validation"],
            score=0.5,
        )
        assert verification.verdict == "revise"
        assert len(verification.issues) == 2

    def test_invalid_verdict(self):
        """Test invalid verdict validation."""
        with pytest.raises(ValidationError):
            VerificationOutput(verdict="maybe")


class TestToolCallOutput:
    """Tests for ToolCallOutput model."""

    def test_basic_tool_call(self):
        """Test basic tool call."""
        tool_call = ToolCallOutput(
            tool_name="search",
            arguments={"query": "python tutorials"},
        )
        assert tool_call.tool_name == "search"
        assert tool_call.arguments["query"] == "python tutorials"

    def test_tool_name_with_spaces(self):
        """Test tool name validation rejects spaces."""
        with pytest.raises(ValidationError):
            ToolCallOutput(
                tool_name="my tool",
                arguments={},
            )

    def test_empty_tool_name(self):
        """Test empty tool name validation."""
        with pytest.raises(ValidationError):
            ToolCallOutput(
                tool_name="",
                arguments={},
            )


class TestSummaryOutput:
    """Tests for SummaryOutput model."""

    def test_success_summary(self):
        """Test successful summary."""
        summary = SummaryOutput(
            summary="Task completed successfully",
            outcome="success",
            key_results=["Found information", "Generated report"],
        )
        assert summary.outcome == "success"
        assert len(summary.key_results) == 2

    def test_partial_summary(self):
        """Test partial completion summary."""
        summary = SummaryOutput(
            summary="Partially completed",
            outcome="partial",
            remaining_items=["Review results", "Verify data"],
        )
        assert summary.outcome == "partial"
        assert len(summary.remaining_items) == 2

    def test_invalid_outcome(self):
        """Test invalid outcome validation."""
        with pytest.raises(ValidationError):
            SummaryOutput(
                summary="Test",
                outcome="unknown",
            )


class TestValidateLlmOutput:
    """Tests for validate_llm_output function."""

    def test_valid_plan_output(self):
        """Test validation of valid plan JSON."""
        json_content = json.dumps(
            {
                "goal": "Test goal",
                "title": "Test Plan",
                "steps": [{"description": "Test step description"}],
            }
        )
        result, validation = validate_llm_output(json_content, PlanOutput)
        assert validation.is_valid is True
        assert result is not None
        assert result.goal == "Test goal"

    def test_invalid_json(self):
        """Test validation of invalid JSON."""
        result, validation = validate_llm_output("not valid json", PlanOutput)
        assert validation.is_valid is False
        assert result is None
        assert len(validation.errors) > 0

    def test_missing_required_field(self):
        """Test validation of JSON missing required field."""
        json_content = json.dumps(
            {
                "goal": "Test goal",
                # Missing title
                "steps": [{"description": "Test step"}],
            }
        )
        _result, validation = validate_llm_output(json_content, PlanOutput)
        assert validation.is_valid is False
        assert "required" in validation.suggestions[0].lower()

    def test_low_confidence_warning(self):
        """Test warning for low confidence score."""
        json_content = json.dumps(
            {
                "decision": "continue",
                "reasoning": "Test reasoning",
                "confidence": 0.2,
            }
        )
        _result, validation = validate_llm_output(json_content, ReflectionOutput)
        assert validation.is_valid is True
        assert any("confidence" in w.lower() for w in validation.warnings)

    def test_no_citations_warning(self):
        """Test warning for missing citations."""
        json_content = json.dumps(
            {
                "content": "Test content",
                "citations": [],
            }
        )
        _result, validation = validate_llm_output(json_content, CitedResponse)
        assert validation.is_valid is True
        assert any("citation" in w.lower() for w in validation.warnings)


class TestBuildValidationFeedback:
    """Tests for build_validation_feedback function."""

    def test_with_errors(self):
        """Test feedback with errors."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing required field", "Invalid type"],
        )
        feedback = build_validation_feedback(result)
        assert "ERRORS" in feedback
        assert "Missing required field" in feedback
        assert "Invalid type" in feedback

    def test_with_suggestions(self):
        """Test feedback with suggestions."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error"],
            suggestions=["Try this", "Or that"],
        )
        feedback = build_validation_feedback(result)
        assert "SUGGESTIONS" in feedback
        assert "Try this" in feedback
        assert "Or that" in feedback

    def test_empty_result(self):
        """Test feedback with no errors or suggestions."""
        result = ValidationResult(is_valid=True)
        feedback = build_validation_feedback(result)
        assert feedback == ""


class TestErrorAnalysisOutput:
    """Tests for ErrorAnalysisOutput model."""

    def test_basic_error_analysis(self):
        """Test basic error analysis."""
        analysis = ErrorAnalysisOutput(
            error_type="network_error",
            root_cause="Connection timeout",
            is_recoverable=True,
            suggested_action="Retry with exponential backoff",
        )
        assert analysis.error_type == "network_error"
        assert analysis.is_recoverable is True

    def test_non_recoverable_error(self):
        """Test non-recoverable error analysis."""
        analysis = ErrorAnalysisOutput(
            error_type="authentication_error",
            is_recoverable=False,
            confidence=0.9,
        )
        assert analysis.is_recoverable is False
        assert analysis.confidence == 0.9


class TestPlanUpdateOutput:
    """Tests for PlanUpdateOutput model."""

    def test_incomplete_update(self):
        """Test incomplete plan update."""
        update = PlanUpdateOutput(
            steps=[StepDescription(description="Remaining step one")],
            message="Continuing with plan",
            completed=False,
        )
        assert update.completed is False
        assert len(update.steps) == 1

    def test_completed_update(self):
        """Test completed plan update."""
        update = PlanUpdateOutput(
            steps=[],
            message="All steps completed",
            completed=True,
        )
        assert update.completed is True
        assert len(update.steps) == 0
