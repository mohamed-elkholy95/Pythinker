"""Tests for the Beanie document models used by prompt optimization persistence.

These are pure unit tests for document <-> domain model conversion logic.
They do NOT require a running MongoDB instance — Beanie's collection
initialization is patched out so we can test serialization correctness.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.models.prompt_optimization import (
    OptimizationRun,
    OptimizationRunStatus,
    OptimizerType,
)
from app.domain.models.prompt_profile import (
    PromptPatch,
    PromptProfile,
    PromptTarget,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    profile_id: str = "prof-001",
    is_active: bool = False,
    targets: list[PromptTarget] | None = None,
) -> PromptProfile:
    targets = targets or [PromptTarget.PLANNER]
    patches = [
        PromptPatch(
            target=t,
            profile_id=profile_id,
            variant_id=f"v1-{t.value}",
            patch_text=f"Optimized {t.value} prompt",
        )
        for t in targets
    ]
    return PromptProfile(
        id=profile_id,
        name="Test Profile",
        version="1.0.0",
        source_run_id="run-abc",
        patches=patches,
        validation_summary={"planner_baseline": 0.4, "planner_optimized": 0.7},
        is_active=is_active,
    )


def _make_run(
    run_id: str = "run-001",
    status: OptimizationRunStatus = OptimizationRunStatus.PENDING,
) -> OptimizationRun:
    return OptimizationRun(
        id=run_id,
        target=PromptTarget.PLANNER,
        optimizer=OptimizerType.MIPROV2_LIGHT,
        status=status,
        config={"auto": "light", "min_cases_policy": 100},
    )


@pytest.fixture(autouse=True)
def _patch_beanie_collection():
    """Patch Beanie's get_motor_collection to avoid CollectionWasNotInitialized."""
    mock_collection = MagicMock()
    with patch(
        "beanie.odm.documents.Document.get_motor_collection",
        return_value=mock_collection,
    ):
        yield


# ---------------------------------------------------------------------------
# PromptProfileDocument round-trip
# ---------------------------------------------------------------------------


class TestPromptProfileDocumentRoundTrip:
    """Tests that from_domain -> to_domain preserves all fields."""

    def test_basic_round_trip(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            PromptProfileDocument,
        )

        original = _make_profile()
        doc = PromptProfileDocument.from_domain(original)
        restored = doc.to_domain()

        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.version == original.version
        assert restored.source_run_id == original.source_run_id
        assert restored.is_active == original.is_active
        assert len(restored.patches) == len(original.patches)
        assert restored.validation_summary == original.validation_summary

    def test_patches_round_trip(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            PromptProfileDocument,
        )

        original = _make_profile(targets=[PromptTarget.PLANNER, PromptTarget.EXECUTION])
        doc = PromptProfileDocument.from_domain(original)
        restored = doc.to_domain()

        for orig_patch, rest_patch in zip(original.patches, restored.patches, strict=True):
            assert rest_patch.target == orig_patch.target
            assert rest_patch.profile_id == orig_patch.profile_id
            assert rest_patch.variant_id == orig_patch.variant_id
            assert rest_patch.patch_text == orig_patch.patch_text

    def test_active_flag_preserved(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            PromptProfileDocument,
        )

        original = _make_profile(is_active=True)
        doc = PromptProfileDocument.from_domain(original)
        restored = doc.to_domain()
        assert restored.is_active is True

    def test_profile_id_mapping(self) -> None:
        """Domain 'id' maps to document 'profile_id'."""
        from app.infrastructure.models.prompt_optimization_documents import (
            PromptProfileDocument,
        )

        original = _make_profile(profile_id="custom-id-123")
        doc = PromptProfileDocument.from_domain(original)
        assert doc.profile_id == "custom-id-123"
        restored = doc.to_domain()
        assert restored.id == "custom-id-123"

    def test_empty_patches(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            PromptProfileDocument,
        )

        profile = PromptProfile(
            id="empty-patches",
            name="Empty",
            version="0.1.0",
            source_run_id="run-x",
            patches=[],
        )
        doc = PromptProfileDocument.from_domain(profile)
        restored = doc.to_domain()
        assert restored.patches == []

    def test_validation_summary_preserved(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            PromptProfileDocument,
        )

        original = _make_profile()
        doc = PromptProfileDocument.from_domain(original)
        restored = doc.to_domain()
        assert restored.validation_summary["planner_baseline"] == pytest.approx(0.4)
        assert restored.validation_summary["planner_optimized"] == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# PromptProfileDocument update_from_domain
# ---------------------------------------------------------------------------


class TestPromptProfileDocumentUpdate:
    """Tests for in-place document updates (upsert pattern)."""

    def test_update_from_domain(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            PromptProfileDocument,
        )

        original = _make_profile(profile_id="prof-upd")
        doc = PromptProfileDocument.from_domain(original)

        updated = PromptProfile(
            id="prof-upd",
            name="Updated Profile",
            version="2.0.0",
            source_run_id="run-xyz",
            patches=[
                PromptPatch(
                    target=PromptTarget.SYSTEM,
                    profile_id="prof-upd",
                    variant_id="v2-system",
                    patch_text="System optimization",
                ),
            ],
            validation_summary={"system_optimized": 0.9},
            is_active=True,
        )

        doc.update_from_domain(updated)

        assert doc.name == "Updated Profile"
        assert doc.version == "2.0.0"
        assert doc.source_run_id == "run-xyz"
        assert doc.is_active is True
        assert len(doc.patches) == 1
        assert doc.validation_summary["system_optimized"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# OptimizationRunDocument round-trip
# ---------------------------------------------------------------------------


class TestOptimizationRunDocumentRoundTrip:
    """Tests that from_domain -> to_domain preserves all fields."""

    def test_pending_run_round_trip(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            OptimizationRunDocument,
        )

        original = _make_run()
        doc = OptimizationRunDocument.from_domain(original)
        restored = doc.to_domain()

        assert restored.id == original.id
        assert restored.target == PromptTarget.PLANNER
        assert restored.optimizer == OptimizerType.MIPROV2_LIGHT
        assert restored.status == OptimizationRunStatus.PENDING
        assert restored.config == original.config

    def test_completed_run_round_trip(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            OptimizationRunDocument,
        )

        run = _make_run(status=OptimizationRunStatus.PENDING)
        run.mark_started()
        run.mark_completed(
            baseline_score=0.4,
            optimized_score=0.7,
            artifact_id="art-001",
        )

        doc = OptimizationRunDocument.from_domain(run)
        restored = doc.to_domain()

        assert restored.status == OptimizationRunStatus.COMPLETED
        assert restored.baseline_score == pytest.approx(0.4)
        assert restored.optimized_score == pytest.approx(0.7)
        assert restored.artifact_id == "art-001"
        assert restored.started_at is not None
        assert restored.completed_at is not None

    def test_failed_run_round_trip(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            OptimizationRunDocument,
        )

        run = _make_run()
        run.mark_started()
        run.mark_failed("Out of memory")

        doc = OptimizationRunDocument.from_domain(run)
        restored = doc.to_domain()

        assert restored.status == OptimizationRunStatus.FAILED
        assert restored.error == "Out of memory"

    def test_run_id_mapping(self) -> None:
        """Domain 'id' maps to document 'run_id'."""
        from app.infrastructure.models.prompt_optimization_documents import (
            OptimizationRunDocument,
        )

        run = _make_run(run_id="custom-run-456")
        doc = OptimizationRunDocument.from_domain(run)
        assert doc.run_id == "custom-run-456"
        restored = doc.to_domain()
        assert restored.id == "custom-run-456"

    def test_enum_serialization(self) -> None:
        """Enums are stored as strings in the document."""
        from app.infrastructure.models.prompt_optimization_documents import (
            OptimizationRunDocument,
        )

        run = _make_run()
        doc = OptimizationRunDocument.from_domain(run)
        assert doc.target == "planner"
        assert doc.optimizer == "miprov2_light"
        assert doc.status == "pending"

    def test_improvement_excluded_from_document(self) -> None:
        """@property improvement should not leak into document fields."""
        from app.infrastructure.models.prompt_optimization_documents import (
            OptimizationRunDocument,
        )

        run = _make_run()
        run.mark_started()
        run.mark_completed(baseline_score=0.3, optimized_score=0.6, artifact_id="a1")
        doc = OptimizationRunDocument.from_domain(run)
        data = doc.model_dump()
        assert "improvement" not in data


# ---------------------------------------------------------------------------
# OptimizationRunDocument update_from_domain
# ---------------------------------------------------------------------------


class TestOptimizationRunDocumentUpdate:
    """Tests for in-place run document updates."""

    def test_update_status_transition(self) -> None:
        from app.infrastructure.models.prompt_optimization_documents import (
            OptimizationRunDocument,
        )

        run = _make_run()
        doc = OptimizationRunDocument.from_domain(run)

        # Transition to RUNNING
        run.mark_started()
        doc.update_from_domain(run)
        assert doc.status == "running"
        assert doc.started_at is not None

        # Transition to COMPLETED
        run.mark_completed(baseline_score=0.5, optimized_score=0.8, artifact_id="a1")
        doc.update_from_domain(run)
        assert doc.status == "completed"
        assert doc.completed_at is not None
