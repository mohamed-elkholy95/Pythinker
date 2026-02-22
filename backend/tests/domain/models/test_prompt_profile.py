"""Unit tests for prompt profile and optimization domain models (PR-1)."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.domain.models.prompt_optimization import (
    CaseSplit,
    OptimizationCase,
    OptimizationCaseExpected,
    OptimizationCaseInput,
    OptimizationRun,
    OptimizationRunStatus,
    OptimizationScore,
    OptimizerType,
)
from app.domain.models.prompt_profile import (
    PromptPatch,
    PromptProfile,
    PromptProfileSummary,
    PromptTarget,
)

# ---------------------------------------------------------------------------
# PromptTarget
# ---------------------------------------------------------------------------


class TestPromptTarget:
    def test_enum_values(self):
        assert PromptTarget.PLANNER.value == "planner"
        assert PromptTarget.EXECUTION.value == "execution"
        assert PromptTarget.SYSTEM.value == "system"

    def test_str_coercion(self):
        assert PromptTarget("planner") is PromptTarget.PLANNER


# ---------------------------------------------------------------------------
# PromptPatch
# ---------------------------------------------------------------------------


class TestPromptPatch:
    def test_basic_construction(self):
        patch = PromptPatch(
            target=PromptTarget.PLANNER,
            profile_id="prof-1",
            variant_id="var-1",
            patch_text="<optimized> step by step </optimized>",
        )
        assert patch.target is PromptTarget.PLANNER
        assert patch.metadata == {}

    def test_metadata_stored(self):
        patch = PromptPatch(
            target=PromptTarget.EXECUTION,
            profile_id="p",
            variant_id="v",
            patch_text="x",
            metadata={"score": 0.88, "run": "run-123"},
        )
        assert patch.metadata["score"] == 0.88


# ---------------------------------------------------------------------------
# PromptProfile
# ---------------------------------------------------------------------------


class TestPromptProfile:
    def _make_profile(
        self,
        targets: list[PromptTarget] | None = None,
        profile_id: str = "prof-test",
    ) -> PromptProfile:
        targets = targets or [PromptTarget.PLANNER]
        patches = [
            PromptPatch(
                target=t,
                profile_id=profile_id,
                variant_id=f"var-{t.value}",
                patch_text=f"patch for {t.value}",
            )
            for t in targets
        ]
        return PromptProfile(
            id=profile_id,
            name="test-profile",
            version="1.0.0",
            source_run_id="run-abc",
            patches=patches,
        )

    def test_auto_id(self):
        """Profile auto-generates a UUID4 when no ID is provided."""
        p = PromptProfile(name="auto", version="1.0.0", source_run_id="run-1")
        assert p.id and len(p.id) == 36  # UUID4

    def test_defaults(self):
        p = self._make_profile()
        assert p.is_active is False
        assert p.validation_summary == {}
        assert isinstance(p.created_at, datetime)

    def test_get_patch_found(self):
        p = self._make_profile([PromptTarget.PLANNER, PromptTarget.EXECUTION])
        patch = p.get_patch(PromptTarget.PLANNER)
        assert patch is not None
        assert patch.target is PromptTarget.PLANNER

    def test_get_patch_not_found(self):
        p = self._make_profile([PromptTarget.PLANNER])
        assert p.get_patch(PromptTarget.SYSTEM) is None

    def test_has_patch(self):
        p = self._make_profile([PromptTarget.PLANNER])
        assert p.has_patch(PromptTarget.PLANNER) is True
        assert p.has_patch(PromptTarget.EXECUTION) is False

    def test_targets_property(self):
        p = self._make_profile([PromptTarget.PLANNER, PromptTarget.SYSTEM])
        assert set(p.targets) == {PromptTarget.PLANNER, PromptTarget.SYSTEM}

    def test_frozen_model(self):
        """PromptProfile is immutable (frozen=True)."""
        p = self._make_profile()
        with pytest.raises(ValidationError):
            p.name = "changed"

    def test_patch_profile_id_mismatch_rejected(self):
        """Validator catches patches with wrong profile_id."""
        with pytest.raises(ValidationError, match="does not match"):
            PromptProfile(
                id="prof-A",
                name="test",
                version="1.0.0",
                source_run_id="run-1",
                patches=[
                    PromptPatch(
                        target=PromptTarget.PLANNER,
                        profile_id="prof-B",  # mismatch
                        variant_id="v1",
                        patch_text="x",
                    )
                ],
            )


# ---------------------------------------------------------------------------
# PromptProfileSummary
# ---------------------------------------------------------------------------


class TestPromptProfileSummary:
    def test_from_profile(self):
        profile = PromptProfile(
            id="prof-1",
            name="my-profile",
            version="2.0.0",
            source_run_id="run-1",
            patches=[
                PromptPatch(
                    target=PromptTarget.EXECUTION,
                    profile_id="prof-1",
                    variant_id="v1",
                    patch_text="x",
                )
            ],
            is_active=True,
            validation_summary={"planner_score": 0.9},
        )
        summary = PromptProfileSummary.from_profile(profile)
        assert summary.id == "prof-1"
        assert summary.is_active is True
        assert PromptTarget.EXECUTION in summary.targets
        assert summary.validation_summary["planner_score"] == 0.9


# ---------------------------------------------------------------------------
# OptimizationCase
# ---------------------------------------------------------------------------


class TestOptimizationCase:
    def test_construction(self):
        case = OptimizationCase(
            target=PromptTarget.EXECUTION,
            input=OptimizationCaseInput(
                user_request="summarize Python 3.13 features",
                step_description="research step",
                available_tools=["info_search_web"],
            ),
            expected=OptimizationCaseExpected(
                must_call_tools=["info_search_web"],
                must_contain=["Python 3.13"],
                min_citations=2,
            ),
            split=CaseSplit.TRAIN,
        )
        assert case.id and len(case.id) == 36
        assert case.split is CaseSplit.TRAIN

    def test_to_request_payload(self):
        case = OptimizationCase(
            target=PromptTarget.PLANNER,
            input=OptimizationCaseInput(user_request="build a plan"),
            expected=OptimizationCaseExpected(),
        )
        payload = case.to_request_payload()
        assert payload["user_request"] == "build a plan"
        assert payload["target"] == "planner"


# ---------------------------------------------------------------------------
# OptimizationScore
# ---------------------------------------------------------------------------


class TestOptimizationScore:
    def test_passed_true(self):
        s = OptimizationScore(score=0.75, feedback="good")
        assert s.passed is True

    def test_passed_false(self):
        s = OptimizationScore(score=0.55, feedback="needs work")
        assert s.passed is False

    def test_components(self):
        s = OptimizationScore(
            score=0.8,
            feedback="ok",
            components={"deterministic": 0.9, "llm_judge": 0.7},
        )
        assert s.components["deterministic"] == 0.9


# ---------------------------------------------------------------------------
# OptimizationRun lifecycle
# ---------------------------------------------------------------------------


class TestOptimizationRun:
    def test_initial_state(self):
        run = OptimizationRun(
            target=PromptTarget.PLANNER,
            optimizer=OptimizerType.GEPA,
        )
        assert run.status is OptimizationRunStatus.PENDING
        assert run.started_at is None
        assert run.improvement is None

    def test_mark_started(self):
        run = OptimizationRun(target=PromptTarget.PLANNER)
        run.mark_started()
        assert run.status is OptimizationRunStatus.RUNNING
        assert run.started_at is not None

    def test_mark_completed(self):
        run = OptimizationRun(target=PromptTarget.EXECUTION)
        run.mark_started()
        run.mark_completed(baseline_score=0.6, optimized_score=0.8, artifact_id="art-1")
        assert run.status is OptimizationRunStatus.COMPLETED
        assert run.improvement == pytest.approx(0.2)
        assert run.artifact_id == "art-1"

    def test_mark_failed(self):
        run = OptimizationRun(target=PromptTarget.SYSTEM)
        run.mark_failed("timeout error")
        assert run.status is OptimizationRunStatus.FAILED
        assert run.error == "timeout error"
        assert run.completed_at is not None

    def test_improvement_none_when_incomplete(self):
        run = OptimizationRun(target=PromptTarget.PLANNER)
        run.mark_started()
        assert run.improvement is None
