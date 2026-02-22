"""Request/response schemas for the prompt optimization admin API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.models.prompt_optimization import OptimizationRunStatus, OptimizerType
from app.domain.models.prompt_profile import PromptProfileSummary, PromptTarget

# ---------------------------------------------------------------------------
# Optimization Run Schemas
# ---------------------------------------------------------------------------


class StartOptimizationRunRequest(BaseModel):
    """Request to start a new optimization run."""

    target: PromptTarget
    optimizer: OptimizerType = OptimizerType.MIPROV2_LIGHT
    auto: str = Field(default="light", pattern="^(light|medium|heavy)$")
    max_sessions: int = Field(default=100, ge=0, le=5000)
    publish_on_complete: bool = False


class OptimizationRunResponse(BaseModel):
    """Response for a single optimization run."""

    id: str
    target: PromptTarget
    optimizer: OptimizerType
    status: OptimizationRunStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    train_cases: int = 0
    val_cases: int = 0
    test_cases: int = 0
    baseline_score: float | None = None
    optimized_score: float | None = None
    improvement: float | None = None
    artifact_id: str | None = None
    profile_id: str | None = None


class ListRunsResponse(BaseModel):
    runs: list[OptimizationRunResponse]
    total: int


# ---------------------------------------------------------------------------
# Prompt Profile Schemas
# ---------------------------------------------------------------------------


class PromptProfileResponse(BaseModel):
    """Full profile response."""

    id: str
    name: str
    version: str
    created_at: datetime
    source_run_id: str
    is_active: bool
    targets: list[PromptTarget]
    validation_summary: dict[str, float] = Field(default_factory=dict)
    patches: list[dict[str, Any]] = Field(default_factory=list)


class ListProfilesResponse(BaseModel):
    profiles: list[PromptProfileSummary]
    total: int


# ---------------------------------------------------------------------------
# Patch Preview Schema
# ---------------------------------------------------------------------------


class ProfilePatchPreviewRequest(BaseModel):
    """Preview how a profile patch would modify a sample prompt."""

    profile_id: str
    target: PromptTarget
    sample_request: str = ""


class ProfilePatchPreviewResponse(BaseModel):
    profile_id: str
    target: PromptTarget
    baseline_prompt_length: int
    patched_prompt_length: int
    patch_applied: bool
    patch_text: str | None = None
