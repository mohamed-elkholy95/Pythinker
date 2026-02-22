"""Application service for prompt optimization operations.

Orchestrates export → optimize → validate → publish → rollback flows,
delegating to domain services and repositories.

This service is the single authority for optimization lifecycle management;
API routes should only call this service, never domain services directly.
"""

from __future__ import annotations

import logging

from app.domain.models.prompt_optimization import OptimizationRun, OptimizerType
from app.domain.models.prompt_profile import PromptProfile, PromptTarget
from app.domain.repositories.prompt_profile_repository import (
    OptimizationRunRepository,
    PromptArtifactRepository,
    PromptProfileRepository,
)
from app.domain.services.agents.learning.prompt_optimizer import get_prompt_optimizer

logger = logging.getLogger(__name__)


class PromptOptimizationService:
    """Application-layer orchestrator for prompt optimization lifecycle."""

    def __init__(
        self,
        profile_repo: PromptProfileRepository,
        run_repo: OptimizationRunRepository,
        artifact_repo: PromptArtifactRepository,
    ) -> None:
        self._profile_repo = profile_repo
        self._run_repo = run_repo
        self._artifact_repo = artifact_repo

    # ------------------------------------------------------------------
    # Optimization Runs
    # ------------------------------------------------------------------

    async def start_run(
        self,
        *,
        target: PromptTarget,
        optimizer: OptimizerType = OptimizerType.MIPROV2_LIGHT,
        config: dict | None = None,
    ) -> OptimizationRun:
        """Create and persist a PENDING optimization run record.

        The actual optimization is run offline via the CLI script
        ``backend/scripts/run_dspy_prompt_optimization.py``.  This method
        creates the tracking record so the API can poll status.
        """
        run = OptimizationRun(
            target=target,
            optimizer=optimizer,
            config=config or {},
        )
        await self._run_repo.save_run(run)
        logger.info("Created optimization run %s for target=%s", run.id, target.value)
        return run

    async def get_run(self, run_id: str) -> OptimizationRun | None:
        return await self._run_repo.get_run(run_id)

    async def list_runs(self, limit: int = 20) -> list[OptimizationRun]:
        return await self._run_repo.list_runs(limit=limit)

    # ------------------------------------------------------------------
    # Prompt Profiles
    # ------------------------------------------------------------------

    async def get_profile(self, profile_id: str) -> PromptProfile | None:
        return await self._profile_repo.get_profile(profile_id)

    async def get_active_profile(self) -> PromptProfile | None:
        return await self._profile_repo.get_active_profile()

    async def list_profiles(self, limit: int = 20) -> list[PromptProfile]:
        return await self._profile_repo.list_profiles(limit=limit)

    async def activate_profile(self, profile_id: str) -> PromptProfile:
        """Activate a profile and seed the runtime Thompson-sampling bandit.

        This is the publish step: after activation the PromptProfileResolver
        will start applying the profile's patches to incoming requests
        (subject to feature flags and canary policy).
        """
        profile = await self._profile_repo.get_profile(profile_id)
        if profile is None:
            raise ValueError(f"PromptProfile not found: {profile_id}")

        await self._profile_repo.activate_profile(profile_id)
        # Re-fetch to get the updated is_active state (PromptProfile is frozen)
        profile = await self._profile_repo.get_profile(profile_id)
        if profile is None:
            raise ValueError(f"PromptProfile disappeared after activation: {profile_id}")

        # Seed the runtime Thompson-sampling bandit so the A/B framework
        # starts with a meaningful prior from the offline validation score.
        optimizer = get_prompt_optimizer()
        for patch in profile.patches:
            val_score = profile.validation_summary.get(f"{patch.target.value}_optimized", 0.0)
            try:
                optimizer.register_dspy_profile(
                    profile_id=profile.id,
                    target=patch.target.value,
                    patch_text=patch.patch_text,
                    validation_score=val_score,
                )
            except Exception as exc:
                logger.warning("Failed to seed bandit for patch %s: %s", patch.target.value, exc)

        logger.info("Activated PromptProfile %s", profile_id)
        return profile

    async def rollback_profile(self, profile_id: str) -> None:
        """Deactivate a specific profile (one-click rollback).

        After rollback the system falls back to baseline prompts immediately
        (all feature-flag-gated paths return BASELINE mode).

        Raises:
            ValueError: If the profile does not exist.
        """
        profile = await self._profile_repo.get_profile(profile_id)
        if profile is None:
            raise ValueError(f"PromptProfile not found: {profile_id}")
        await self._profile_repo.deactivate_profile(profile_id)
        logger.info("Rolled back (deactivated) PromptProfile %s", profile_id)

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    async def load_artifact(self, artifact_id: str) -> bytes | None:
        return await self._artifact_repo.load_artifact(artifact_id)

    async def delete_artifact(self, artifact_id: str) -> None:
        await self._artifact_repo.delete_artifact(artifact_id)
