"""Tests for the offline DSPy/GEPA optimizer orchestrator.

Since DSPy is an optional dependency (offline-only), these tests mock
the DSPy library and focus on orchestration logic: dataset validation,
optimizer dispatch, artifact serialization, and score tracking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.domain.models.prompt_optimization import CaseSplit, OptimizerType
from app.domain.models.prompt_profile import PromptTarget
from app.domain.services.prompt_optimization.optimizer_orchestrator import (
    RunResult,
    _make_scalar_metric,
    run_optimization,
)

# ---------------------------------------------------------------------------
# RunResult
# ---------------------------------------------------------------------------


class TestRunResult:
    """Tests for the RunResult dataclass."""

    def test_improvement_positive(self) -> None:
        r = RunResult(
            target=PromptTarget.PLANNER,
            optimizer=OptimizerType.MIPROV2,
            baseline_score=0.4,
            optimized_score=0.7,
            train_count=10,
            val_count=3,
            test_count=0,
            artifact_bytes=b"{}",
            duration_seconds=5.0,
        )
        assert r.improvement == pytest.approx(0.3)

    def test_improvement_negative(self) -> None:
        r = RunResult(
            target=PromptTarget.EXECUTION,
            optimizer=OptimizerType.GEPA,
            baseline_score=0.8,
            optimized_score=0.6,
            train_count=10,
            val_count=3,
            test_count=0,
            artifact_bytes=b"{}",
            duration_seconds=2.0,
        )
        assert r.improvement == pytest.approx(-0.2)

    def test_extra_defaults_empty(self) -> None:
        r = RunResult(
            target=PromptTarget.PLANNER,
            optimizer=OptimizerType.MIPROV2,
            baseline_score=0.5,
            optimized_score=0.5,
            train_count=5,
            val_count=2,
            test_count=0,
            artifact_bytes=b"{}",
            duration_seconds=1.0,
        )
        assert r.extra == {}


# ---------------------------------------------------------------------------
# _make_scalar_metric
# ---------------------------------------------------------------------------


class TestMakeScalarMetric:
    """Tests for the scalar metric wrapper."""

    def test_wraps_prediction_score(self) -> None:
        """Metric returning a prediction object → extract .score."""

        @dataclass
        class FakePrediction:
            score: float
            feedback: str

        def metric(example: Any, prediction: Any, trace: Any = None) -> FakePrediction:
            return FakePrediction(score=0.75, feedback="good")

        scalar = _make_scalar_metric(metric)
        result = scalar(None, None)
        assert result == pytest.approx(0.75)

    def test_wraps_float_return(self) -> None:
        """Metric returning a float → pass through."""

        def metric(example: Any, prediction: Any, trace: Any = None) -> float:
            return 0.42

        scalar = _make_scalar_metric(metric)
        assert scalar(None, None) == pytest.approx(0.42)

    def test_wraps_int_return(self) -> None:
        def metric(example: Any, prediction: Any, trace: Any = None) -> int:
            return 1

        scalar = _make_scalar_metric(metric)
        assert scalar(None, None) == pytest.approx(1.0)

    def test_unknown_return_gives_zero(self) -> None:
        """Metric returning something unexpected → 0.0."""

        def metric(example: Any, prediction: Any, trace: Any = None) -> str:
            return "not a number"

        scalar = _make_scalar_metric(metric)
        assert scalar(None, None) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# run_optimization — insufficient data
# ---------------------------------------------------------------------------


class TestRunOptimizationValidation:
    """Tests that run_optimization validates dataset sizes before running."""

    def test_insufficient_training_data_raises(self) -> None:
        """< 5 training cases → ValueError."""
        # Supply only a tiny curated dataset by mocking the builder
        with (
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.DatasetBuilder") as mock_builder,
        ):
            instance = mock_builder.return_value
            instance.build_combined.return_value = []
            instance.split.return_value = {
                CaseSplit.TRAIN: [],  # 0 train cases
                CaseSplit.VAL: [],
                CaseSplit.TEST: [],
            }

            with pytest.raises(ValueError, match="Insufficient training cases"):
                run_optimization(
                    target=PromptTarget.PLANNER,
                    optimizer_type=OptimizerType.MIPROV2_LIGHT,
                    api_key="test-key",
                    api_base="http://test",
                    model_name="test-model",
                )

    def test_exactly_five_cases_does_not_raise(self) -> None:
        """Exactly 5 training cases should pass validation."""
        from app.domain.models.prompt_optimization import (
            OptimizationCase,
            OptimizationCaseExpected,
            OptimizationCaseInput,
        )

        cases = [
            OptimizationCase(
                id=f"case-{i}",
                target=PromptTarget.PLANNER,
                input=OptimizationCaseInput(user_request=f"Do task {i}"),
                expected=OptimizationCaseExpected(min_steps=1, max_steps=5),
            )
            for i in range(5)
        ]

        with (
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.DatasetBuilder") as mock_builder,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator.cases_to_dspy_examples"
            ) as mock_convert,
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator._configure_dspy_lm"),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.build_gepa_metric") as mock_metric,
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.PlannerProgram") as mock_program,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator._evaluate_program",
                return_value=0.5,
            ),
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator._run_miprov2",
            ) as mock_miprov2,
        ):
            instance = mock_builder.return_value
            instance.build_combined.return_value = cases
            instance.split.return_value = {
                CaseSplit.TRAIN: cases,
                CaseSplit.VAL: [],
                CaseSplit.TEST: [],
            }
            mock_convert.return_value = [MagicMock() for _ in range(5)]
            mock_metric.return_value = MagicMock()

            # Mock the optimized program with save()
            opt_program = MagicMock()
            opt_program.save.side_effect = lambda path: _write_fake_artifact(path)
            mock_miprov2.return_value = opt_program
            mock_program.build.return_value = MagicMock()

            result = run_optimization(
                target=PromptTarget.PLANNER,
                optimizer_type=OptimizerType.MIPROV2_LIGHT,
                api_key="test-key",
                api_base="http://test",
                model_name="test-model",
            )
            assert result.train_count == 5
            assert isinstance(result.artifact_bytes, bytes)


# ---------------------------------------------------------------------------
# run_optimization — optimizer dispatch
# ---------------------------------------------------------------------------


class TestRunOptimizationDispatch:
    """Tests for optimizer type routing."""

    def _run_with_optimizer(self, optimizer_type: OptimizerType) -> RunResult:
        from app.domain.models.prompt_optimization import (
            OptimizationCase,
            OptimizationCaseExpected,
            OptimizationCaseInput,
        )

        cases = [
            OptimizationCase(
                id=f"case-{i}",
                target=PromptTarget.EXECUTION,
                input=OptimizationCaseInput(
                    user_request=f"Task {i}",
                    step_description=f"Step {i}",
                ),
                expected=OptimizationCaseExpected(),
            )
            for i in range(6)
        ]

        with (
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.DatasetBuilder") as mock_builder,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator.cases_to_dspy_examples"
            ) as mock_convert,
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator._configure_dspy_lm"),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.build_gepa_metric"),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.ExecutionProgram") as mock_program,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator._evaluate_program",
                return_value=0.6,
            ),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator._run_miprov2") as mock_miprov2,
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator._run_gepa") as mock_gepa,
        ):
            instance = mock_builder.return_value
            instance.build_combined.return_value = cases
            instance.split.return_value = {
                CaseSplit.TRAIN: cases,
                CaseSplit.VAL: [],
                CaseSplit.TEST: [],
            }
            mock_convert.return_value = [MagicMock() for _ in range(6)]

            opt_program = MagicMock()
            opt_program.save.side_effect = lambda path: _write_fake_artifact(path)
            mock_miprov2.return_value = opt_program
            mock_gepa.return_value = opt_program
            mock_program.build.return_value = MagicMock()

            result = run_optimization(
                target=PromptTarget.EXECUTION,
                optimizer_type=optimizer_type,
                api_key="test-key",
                api_base="http://test",
                model_name="test-model",
            )

            if optimizer_type == OptimizerType.GEPA:
                mock_gepa.assert_called_once()
                mock_miprov2.assert_not_called()
            else:
                mock_miprov2.assert_called_once()
                mock_gepa.assert_not_called()

            return result

    def test_dispatch_gepa(self) -> None:
        result = self._run_with_optimizer(OptimizerType.GEPA)
        assert result.optimizer == OptimizerType.GEPA

    def test_dispatch_miprov2(self) -> None:
        result = self._run_with_optimizer(OptimizerType.MIPROV2)
        assert result.optimizer == OptimizerType.MIPROV2

    def test_dispatch_miprov2_light(self) -> None:
        result = self._run_with_optimizer(OptimizerType.MIPROV2_LIGHT)
        assert result.optimizer == OptimizerType.MIPROV2_LIGHT

    def test_unknown_optimizer_raises(self) -> None:
        """An unrecognized optimizer type should raise ValueError."""
        from app.domain.models.prompt_optimization import (
            OptimizationCase,
            OptimizationCaseExpected,
            OptimizationCaseInput,
        )

        cases = [
            OptimizationCase(
                id=f"case-{i}",
                target=PromptTarget.PLANNER,
                input=OptimizationCaseInput(user_request=f"Task {i}"),
                expected=OptimizationCaseExpected(min_steps=1, max_steps=5),
            )
            for i in range(6)
        ]

        with (
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.DatasetBuilder") as mock_builder,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator.cases_to_dspy_examples"
            ) as mock_convert,
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator._configure_dspy_lm"),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.build_gepa_metric"),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.PlannerProgram") as mock_program,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator._evaluate_program",
                return_value=0.5,
            ),
        ):
            instance = mock_builder.return_value
            instance.build_combined.return_value = cases
            instance.split.return_value = {
                CaseSplit.TRAIN: cases,
                CaseSplit.VAL: [],
                CaseSplit.TEST: [],
            }
            mock_convert.return_value = [MagicMock() for _ in range(6)]
            mock_program.build.return_value = MagicMock()

            # Create a fake "unknown" optimizer via string hacking
            fake_type = MagicMock()
            fake_type.value = "unknown_optimizer"
            fake_type.__eq__ = lambda self, other: False
            fake_type.__hash__ = lambda self: hash("unknown")
            # Use 'in' operator — make it not match MIPROV2/MIPROV2_LIGHT tuple
            with pytest.raises(ValueError, match="Unknown optimizer type"):
                run_optimization(
                    target=PromptTarget.PLANNER,
                    optimizer_type=fake_type,
                    api_key="test-key",
                    api_base="http://test",
                    model_name="test-model",
                )


# ---------------------------------------------------------------------------
# run_optimization — result structure
# ---------------------------------------------------------------------------


class TestRunOptimizationResult:
    """Tests that the result carries correct metadata."""

    def test_result_structure(self) -> None:
        from app.domain.models.prompt_optimization import (
            OptimizationCase,
            OptimizationCaseExpected,
            OptimizationCaseInput,
        )

        train = [
            OptimizationCase(
                id=f"t-{i}",
                target=PromptTarget.PLANNER,
                input=OptimizationCaseInput(user_request=f"Task {i}"),
                expected=OptimizationCaseExpected(min_steps=1, max_steps=5),
            )
            for i in range(8)
        ]
        val = [
            OptimizationCase(
                id=f"v-{i}",
                target=PromptTarget.PLANNER,
                input=OptimizationCaseInput(user_request=f"Val {i}"),
                expected=OptimizationCaseExpected(min_steps=1, max_steps=5),
            )
            for i in range(3)
        ]

        with (
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.DatasetBuilder") as mock_builder,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator.cases_to_dspy_examples"
            ) as mock_convert,
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator._configure_dspy_lm"),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.build_gepa_metric"),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator.PlannerProgram") as mock_program,
            patch(
                "app.domain.services.prompt_optimization.optimizer_orchestrator._evaluate_program",
                side_effect=[0.3, 0.7],  # baseline, optimized
            ),
            patch("app.domain.services.prompt_optimization.optimizer_orchestrator._run_miprov2") as mock_miprov2,
        ):
            instance = mock_builder.return_value
            instance.build_combined.return_value = train + val
            instance.split.return_value = {
                CaseSplit.TRAIN: train,
                CaseSplit.VAL: val,
                CaseSplit.TEST: [],
            }
            mock_convert.return_value = [MagicMock() for _ in range(8)]

            opt_program = MagicMock()
            opt_program.save.side_effect = lambda path: _write_fake_artifact(path)
            mock_miprov2.return_value = opt_program
            mock_program.build.return_value = MagicMock()

            result = run_optimization(
                target=PromptTarget.PLANNER,
                optimizer_type=OptimizerType.MIPROV2,
                api_key="key",
                api_base="http://test",
                model_name="model",
            )

            assert result.target == PromptTarget.PLANNER
            assert result.optimizer == OptimizerType.MIPROV2
            assert result.baseline_score == pytest.approx(0.3)
            assert result.optimized_score == pytest.approx(0.7)
            assert result.improvement == pytest.approx(0.4)
            assert result.train_count == 8
            assert result.val_count == 3
            assert result.test_count == 0
            assert result.duration_seconds > 0
            assert len(result.artifact_bytes) > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fake_artifact(path: str) -> None:
    """Write a minimal JSON artifact to the given path (simulates dspy program.save())."""
    import pathlib

    pathlib.Path(path).write_text(json.dumps({"type": "fake_program", "instructions": "optimized"}))
