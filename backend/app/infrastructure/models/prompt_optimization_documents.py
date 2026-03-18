"""Beanie documents for prompt optimization profile and run persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.domain.models.prompt_optimization import (
    OptimizationRun,
    OptimizationRunStatus,
    OptimizerType,
)
from app.domain.models.prompt_profile import PromptPatch, PromptProfile, PromptTarget
from app.infrastructure.models.documents import BaseDocument


class PromptProfileDocument(
    BaseDocument[PromptProfile],
    id_field="profile_id",
    domain_model_class=PromptProfile,
):
    """MongoDB document for prompt profiles produced by the optimizer."""

    profile_id: str
    name: str
    version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_run_id: str
    patches: list[dict[str, Any]] = Field(default_factory=list)
    validation_summary: dict[str, float] = Field(default_factory=dict)
    is_active: bool = False

    class Settings:
        name: ClassVar[str] = "prompt_profiles"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("profile_id", ASCENDING)], unique=True),
            IndexModel([("is_active", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("source_run_id", ASCENDING)]),
        ]

    def to_domain(self) -> PromptProfile:
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop("profile_id")
        data["patches"] = [PromptPatch.model_validate(p) for p in data.get("patches", [])]
        return PromptProfile.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: PromptProfile) -> PromptProfileDocument:
        data = domain_obj.model_dump()
        data["profile_id"] = data.pop("id")
        data["patches"] = [p.model_dump() for p in domain_obj.patches]
        return cls.model_validate(data)

    def update_from_domain(self, domain_obj: PromptProfile) -> None:
        self.name = domain_obj.name
        self.version = domain_obj.version
        self.source_run_id = domain_obj.source_run_id
        self.patches = [p.model_dump() for p in domain_obj.patches]
        self.validation_summary = domain_obj.validation_summary
        self.is_active = domain_obj.is_active


class OptimizationRunDocument(
    BaseDocument[OptimizationRun],
    id_field="run_id",
    domain_model_class=OptimizationRun,
):
    """MongoDB document for optimization run metadata."""

    run_id: str
    target: str  # PromptTarget.value
    optimizer: str = OptimizerType.MIPROV2.value
    status: str = OptimizationRunStatus.PENDING.value
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    train_cases: int = 0
    val_cases: int = 0
    test_cases: int = 0
    baseline_score: float | None = None
    optimized_score: float | None = None
    artifact_id: str | None = None
    profile_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name: ClassVar[str] = "optimization_runs"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("run_id", ASCENDING)], unique=True),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("target", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]

    def to_domain(self) -> OptimizationRun:
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop("run_id")
        data["target"] = PromptTarget(data["target"])
        data["optimizer"] = OptimizerType(data["optimizer"])
        data["status"] = OptimizationRunStatus(data["status"])
        return OptimizationRun.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: OptimizationRun) -> OptimizationRunDocument:
        data = domain_obj.model_dump()
        data["run_id"] = data.pop("id")
        data["target"] = domain_obj.target.value
        data["optimizer"] = domain_obj.optimizer.value
        data["status"] = domain_obj.status.value
        # Remove computed field
        data.pop("improvement", None)
        return cls.model_validate(data)

    def update_from_domain(self, domain_obj: OptimizationRun) -> None:
        self.status = domain_obj.status.value
        self.started_at = domain_obj.started_at
        self.completed_at = domain_obj.completed_at
        self.error = domain_obj.error
        self.train_cases = domain_obj.train_cases
        self.val_cases = domain_obj.val_cases
        self.test_cases = domain_obj.test_cases
        self.baseline_score = domain_obj.baseline_score
        self.optimized_score = domain_obj.optimized_score
        self.artifact_id = domain_obj.artifact_id
        self.profile_id = domain_obj.profile_id
