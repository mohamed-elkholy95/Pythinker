"""Tests for DSPy adapter: Example conversion and metric construction."""

from __future__ import annotations

import json

import pytest

from app.domain.models.prompt_optimization import (
    OptimizationCase,
    OptimizationCaseExpected,
    OptimizationCaseInput,
)
from app.domain.models.prompt_profile import PromptTarget

# ---------------------------------------------------------------------------
# cases_to_dspy_examples
# ---------------------------------------------------------------------------


class TestCasesToDspyExamples:
    """Test the per-target field mapping and tools joining."""

    def _make_case(
        self,
        target: PromptTarget,
        user_request: str = "do something",
        step_description: str = "",
        available_tools: list[str] | None = None,
    ) -> OptimizationCase:
        return OptimizationCase(
            target=target,
            input=OptimizationCaseInput(
                user_request=user_request,
                step_description=step_description,
                available_tools=available_tools or [],
            ),
            expected=OptimizationCaseExpected(min_steps=2, max_steps=5),
        )

    def test_returns_empty_when_dspy_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Graceful offline guard: returns [] when dspy is absent."""
        import app.domain.services.prompt_optimization.dspy_adapter as mod

        monkeypatch.setattr(mod, "_DSPY_AVAILABLE", False)

        cases = [self._make_case(PromptTarget.PLANNER)]
        result = mod.cases_to_dspy_examples(cases)
        assert result == []

    def test_planner_fields(self) -> None:
        """PLANNER examples have user_request and available_tools as inputs."""
        dspy = pytest.importorskip("dspy")  # noqa: F841
        from app.domain.services.prompt_optimization.dspy_adapter import cases_to_dspy_examples

        case = self._make_case(
            PromptTarget.PLANNER,
            user_request="Build an API",
            available_tools=["file_write", "terminal_execute"],
        )
        examples = cases_to_dspy_examples([case])
        assert len(examples) == 1

        ex = examples[0]
        # Input fields
        assert ex.user_request == "Build an API"
        assert ex.available_tools == "file_write, terminal_execute"
        # with_inputs should expose exactly these
        inputs = ex.inputs()
        assert "user_request" in inputs
        assert "available_tools" in inputs
        # request_payload should NOT exist
        assert not hasattr(ex, "request_payload")

    def test_execution_fields(self) -> None:
        """EXECUTION examples include step_description as an input."""
        dspy = pytest.importorskip("dspy")  # noqa: F841
        from app.domain.services.prompt_optimization.dspy_adapter import cases_to_dspy_examples

        case = self._make_case(
            PromptTarget.EXECUTION,
            user_request="Fix the bug",
            step_description="Read and patch the file",
            available_tools=["file_read"],
        )
        examples = cases_to_dspy_examples([case])
        assert len(examples) == 1

        ex = examples[0]
        inputs = ex.inputs()
        assert "user_request" in inputs
        assert "step_description" in inputs
        assert "available_tools" in inputs
        assert ex.step_description == "Read and patch the file"

    def test_empty_tools_joined(self) -> None:
        """Empty tools list produces empty string."""
        dspy = pytest.importorskip("dspy")  # noqa: F841
        from app.domain.services.prompt_optimization.dspy_adapter import cases_to_dspy_examples

        case = self._make_case(PromptTarget.PLANNER, available_tools=[])
        examples = cases_to_dspy_examples([case])
        assert examples[0].available_tools == ""

    def test_expected_constraints_carried(self) -> None:
        """expected_constraints dict is available on each example."""
        dspy = pytest.importorskip("dspy")  # noqa: F841
        from app.domain.services.prompt_optimization.dspy_adapter import cases_to_dspy_examples

        case = self._make_case(PromptTarget.PLANNER)
        examples = cases_to_dspy_examples([case])
        constraints = examples[0].expected_constraints
        assert constraints["min_steps"] == 2
        assert constraints["max_steps"] == 5


# ---------------------------------------------------------------------------
# build_gepa_metric — plan_json parsing (Fix 2)
# ---------------------------------------------------------------------------


class TestGepaMetricPlanJsonParsing:
    """Verify that the metric correctly parses plan_json strings."""

    def test_plan_json_parsed_as_list(self) -> None:
        """prediction.plan_json (a string) is parsed into a list of step dicts."""
        dspy = pytest.importorskip("dspy")
        from app.domain.services.prompt_optimization.dspy_adapter import build_gepa_metric
        from app.domain.services.prompt_optimization.scoring import OptimizationScorer

        scorer = OptimizationScorer()
        metric = build_gepa_metric(scorer, PromptTarget.PLANNER)

        example = dspy.Example(
            user_request="Build an API",
            available_tools="file_write, terminal_execute",
            expected_constraints={"min_steps": 2, "max_steps": 5},
        ).with_inputs("user_request", "available_tools")

        steps = [
            {"description": "Set up the project structure"},
            {"description": "Implement the API endpoints"},
            {"description": "Write tests and verify"},
        ]
        prediction = dspy.Prediction(plan_json=json.dumps(steps))

        result = metric(example, prediction)
        assert result.score > 0.0, "Score should be positive for valid plan"

    def test_malformed_plan_json_returns_zero_steps(self) -> None:
        """Malformed JSON in plan_json should not crash — defaults to [] steps."""
        dspy = pytest.importorskip("dspy")
        from app.domain.services.prompt_optimization.dspy_adapter import build_gepa_metric
        from app.domain.services.prompt_optimization.scoring import OptimizationScorer

        scorer = OptimizationScorer()
        metric = build_gepa_metric(scorer, PromptTarget.PLANNER)

        example = dspy.Example(
            user_request="Build something",
            available_tools="",
            expected_constraints={"min_steps": 2, "max_steps": 5},
        ).with_inputs("user_request", "available_tools")

        prediction = dspy.Prediction(plan_json="not valid json {{{")

        result = metric(example, prediction)
        # Should not crash, score will be low (0 steps < min_steps)
        assert isinstance(result.score, float)
