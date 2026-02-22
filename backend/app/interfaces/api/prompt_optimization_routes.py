"""Admin API routes for prompt optimization management.

All endpoints require admin role.

Endpoints:
  POST   /api/v1/prompt-optimization/runs              — Start tracking run
  GET    /api/v1/prompt-optimization/runs              — List runs
  GET    /api/v1/prompt-optimization/runs/{run_id}     — Get run status
  GET    /api/v1/prompt-optimization/profiles          — List profiles
  GET    /api/v1/prompt-optimization/profiles/{id}     — Get profile
  POST   /api/v1/prompt-optimization/profiles/{id}/activate  — Activate
  POST   /api/v1/prompt-optimization/profiles/{id}/rollback  — Rollback
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.services.prompt_optimization_service import PromptOptimizationService
from app.domain.models.prompt_optimization import OptimizationRun
from app.domain.models.prompt_profile import PromptProfile, PromptProfileSummary
from app.domain.models.user import User
from app.interfaces.dependencies import (
    get_prompt_optimization_service,
    require_admin_user,
)
from app.interfaces.schemas.prompt_optimization import (
    ListProfilesResponse,
    ListRunsResponse,
    OptimizationRunResponse,
    PromptProfileResponse,
    StartOptimizationRunRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/prompt-optimization",
    tags=["prompt-optimization"],
)


def _run_to_response(run: OptimizationRun) -> OptimizationRunResponse:
    return OptimizationRunResponse(
        id=run.id,
        target=run.target,
        optimizer=run.optimizer,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error=run.error,
        train_cases=run.train_cases,
        val_cases=run.val_cases,
        test_cases=run.test_cases,
        baseline_score=run.baseline_score,
        optimized_score=run.optimized_score,
        improvement=run.improvement,
        artifact_id=run.artifact_id,
        profile_id=run.profile_id,
    )


def _profile_to_response(profile: PromptProfile) -> PromptProfileResponse:
    return PromptProfileResponse(
        id=profile.id,
        name=profile.name,
        version=profile.version,
        created_at=profile.created_at,
        source_run_id=profile.source_run_id,
        is_active=profile.is_active,
        targets=profile.targets,
        validation_summary=profile.validation_summary,
        patches=[p.model_dump() for p in profile.patches],
    )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.post(
    "/runs",
    response_model=OptimizationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new optimization run tracking record",
)
async def start_optimization_run(
    request: StartOptimizationRunRequest,
    _user: User = Depends(require_admin_user),
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> OptimizationRunResponse:
    """Create a PENDING run record.

    The actual optimization runs offline via:
    ``python backend/scripts/run_dspy_prompt_optimization.py``
    This endpoint creates the tracking record for status polling.
    """
    run = await service.start_run(
        target=request.target,
        optimizer=request.optimizer,
        config={
            "auto": request.auto,
            "max_sessions": request.max_sessions,
            "publish_on_complete": request.publish_on_complete,
        },
    )
    return _run_to_response(run)


@router.get(
    "/runs",
    response_model=ListRunsResponse,
    summary="List optimization runs",
)
async def list_optimization_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_admin_user),
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> ListRunsResponse:
    runs = await service.list_runs(limit=limit)
    return ListRunsResponse(
        runs=[_run_to_response(r) for r in runs],
        total=len(runs),
    )


@router.get(
    "/runs/{run_id}",
    response_model=OptimizationRunResponse,
    summary="Get optimization run status",
)
async def get_optimization_run(
    run_id: str,
    _user: User = Depends(require_admin_user),
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> OptimizationRunResponse:
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _run_to_response(run)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@router.get(
    "/profiles",
    response_model=ListProfilesResponse,
    summary="List prompt profiles",
)
async def list_profiles(
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_admin_user),
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> ListProfilesResponse:
    profiles = await service.list_profiles(limit=limit)
    return ListProfilesResponse(
        profiles=[PromptProfileSummary.from_profile(p) for p in profiles],
        total=len(profiles),
    )


@router.get(
    "/profiles/{profile_id}",
    response_model=PromptProfileResponse,
    summary="Get a specific prompt profile",
)
async def get_profile(
    profile_id: str,
    _user: User = Depends(require_admin_user),
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> PromptProfileResponse:
    profile = await service.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return _profile_to_response(profile)


@router.post(
    "/profiles/{profile_id}/activate",
    response_model=PromptProfileResponse,
    summary="Activate a prompt profile",
)
async def activate_profile(
    profile_id: str,
    _user: User = Depends(require_admin_user),
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> PromptProfileResponse:
    """Activate a profile, deactivating any currently active profile.

    After activation the PromptProfileResolver will apply patches
    to incoming requests (subject to feature flags and canary policy).
    """
    try:
        profile = await service.activate_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _profile_to_response(profile)


@router.post(
    "/profiles/{profile_id}/rollback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rollback (deactivate) a prompt profile",
)
async def rollback_profile(
    profile_id: str,
    _user: User = Depends(require_admin_user),
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> None:
    """One-click rollback: deactivate this profile.

    After rollback all feature-flag-gated paths immediately fall back
    to baseline prompt behavior.
    """
    try:
        await service.rollback_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
