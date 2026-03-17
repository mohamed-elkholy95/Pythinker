"""Tests for the optimization scoring service."""

from __future__ import annotations

from app.domain.models.prompt_optimization import (
    OptimizationCase,
    OptimizationCaseExpected,
    OptimizationCaseInput,
)
from app.domain.models.prompt_profile import PromptTarget
from app.domain.services.prompt_optimization.scoring import OptimizationScorer


def _make_planner_case(
    min_steps: int = 2,
    max_steps: int = 5,
    available_tools: list[str] | None = None,
) -> OptimizationCase:
    return OptimizationCase(
        target=PromptTarget.PLANNER,
        input=OptimizationCaseInput(
            user_request="Build something",
            available_tools=available_tools or [],
        ),
        expected=OptimizationCaseExpected(min_steps=min_steps, max_steps=max_steps),
    )


def _make_execution_case(
    must_call_tools: list[str] | None = None,
    must_contain: list[str] | None = None,
    min_citations: int = 0,
) -> OptimizationCase:
    return OptimizationCase(
        target=PromptTarget.EXECUTION,
        input=OptimizationCaseInput(
            user_request="Do something",
            step_description="Execute the task",
        ),
        expected=OptimizationCaseExpected(
            must_call_tools=must_call_tools or [],
            must_contain=must_contain or [],
            min_citations=min_citations,
        ),
    )


class TestPlannerScoring:
    """Tests for _score_planner via OptimizationScorer."""

    def test_valid_plan_within_bounds(self) -> None:
        scorer = OptimizationScorer()
        case = _make_planner_case(min_steps=2, max_steps=5)
        output = {
            "steps": [
                {"description": "Set up the project structure and install dependencies"},
                {"description": "Implement the core functionality and API endpoints"},
                {"description": "Write tests and verify the application works"},
            ]
        }
        result = scorer.score(case, output)
        assert result.score > 0.5, f"Expected good score, got {result.score}"
        assert result.passed

    def test_empty_steps_penalized(self) -> None:
        scorer = OptimizationScorer()
        case = _make_planner_case(min_steps=2)
        output = {"steps": []}
        result = scorer.score(case, output)
        assert result.score < 0.5
        assert "too few steps" in result.feedback.lower()

    def test_step_count_bounds(self) -> None:
        scorer = OptimizationScorer()
        case = _make_planner_case(min_steps=3, max_steps=5)

        # Too few
        output_few = {"steps": [{"description": "Step 1"}]}
        result_few = scorer.score(case, output_few)

        # Within range
        output_ok = {"steps": [{"description": f"Step {i} description here"} for i in range(4)]}
        result_ok = scorer.score(case, output_ok)

        assert result_ok.score > result_few.score

    def test_steps_as_list_of_dicts(self) -> None:
        """Steps must be list[dict] — not a raw string."""
        scorer = OptimizationScorer()
        case = _make_planner_case(min_steps=1, max_steps=5)
        # Valid list of dicts
        output = {"steps": [{"description": "Do the work"}]}
        result = scorer.score(case, output)
        assert result.score > 0.0


class TestExecutionScoring:
    """Tests for _score_execution via OptimizationScorer."""

    def test_basic_scoring(self) -> None:
        scorer = OptimizationScorer()
        case = _make_execution_case(
            must_call_tools=["info_search_web"],
            must_contain=["result"],
        )
        output = {
            "response_text": "Here is the result from our search.",
            "tools_called": ["info_search_web"],
        }
        result = scorer.score(case, output)
        assert result.score > 0.3

    def test_missing_tools_penalized(self) -> None:
        scorer = OptimizationScorer()
        case = _make_execution_case(must_call_tools=["file_write", "terminal_execute"])
        output = {
            "response_text": "Done.",
            "tools_called": [],
        }
        result = scorer.score(case, output)
        assert "Missing required tool calls" in result.feedback

    def test_forbidden_content_penalized(self) -> None:
        scorer = OptimizationScorer()
        case = OptimizationCase(
            target=PromptTarget.EXECUTION,
            input=OptimizationCaseInput(user_request="test"),
            expected=OptimizationCaseExpected(must_not_contain=["secret"]),
        )
        output = {"response_text": "The secret is out.", "tools_called": []}
        result = scorer.score(case, output)
        assert "forbidden content" in result.feedback.lower()

    def test_citation_scoring(self) -> None:
        scorer = OptimizationScorer()
        case = _make_execution_case(min_citations=2)
        output_with_citations = {
            "response_text": "See [1] and https://example.com for details.",
            "tools_called": [],
        }
        output_without = {
            "response_text": "No sources here.",
            "tools_called": [],
        }
        result_with = scorer.score(case, output_with_citations)
        result_without = scorer.score(case, output_without)
        assert result_with.score > result_without.score
