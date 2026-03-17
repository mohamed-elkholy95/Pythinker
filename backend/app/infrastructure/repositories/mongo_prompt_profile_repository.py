"""MongoDB implementation of PromptProfileRepository and OptimizationRunRepository."""

from __future__ import annotations

import logging

from app.domain.models.prompt_optimization import OptimizationRun
from app.domain.models.prompt_profile import PromptProfile
from app.infrastructure.models.prompt_optimization_documents import (
    OptimizationRunDocument,
    PromptProfileDocument,
)

logger = logging.getLogger(__name__)


class MongoPromptProfileRepository:
    """MongoDB-backed PromptProfileRepository.

    Satisfies both the PromptProfileRepository and OptimizationRunRepository
    protocols — combined implementation since both share the same Beanie
    client and are always deployed together.
    """

    # ------------------------------------------------------------------
    # PromptProfileRepository
    # ------------------------------------------------------------------

    async def save_profile(self, profile: PromptProfile) -> None:
        existing = await PromptProfileDocument.find_one(PromptProfileDocument.profile_id == profile.id)
        if existing:
            existing.update_from_domain(profile)
            await existing.save()
        else:
            doc = PromptProfileDocument.from_domain(profile)
            await doc.insert()
        logger.debug("Saved PromptProfile %s (active=%s)", profile.id, profile.is_active)

    async def get_profile(self, profile_id: str) -> PromptProfile | None:
        doc = await PromptProfileDocument.find_one(PromptProfileDocument.profile_id == profile_id)
        return doc.to_domain() if doc else None

    async def get_active_profile(self) -> PromptProfile | None:
        doc = await PromptProfileDocument.find_one(
            PromptProfileDocument.is_active == True  # noqa: E712
        )
        return doc.to_domain() if doc else None

    async def activate_profile(self, profile_id: str) -> None:
        # Verify target exists before any state changes
        result = await PromptProfileDocument.find_one(PromptProfileDocument.profile_id == profile_id)
        if result is None:
            raise ValueError(f"PromptProfile not found: {profile_id}")

        # Atomically deactivate all, then activate target (minimizes race window)
        await PromptProfileDocument.find(
            PromptProfileDocument.is_active == True  # noqa: E712
        ).update({"$set": {"is_active": False}})
        await PromptProfileDocument.find_one(PromptProfileDocument.profile_id == profile_id).update(
            {"$set": {"is_active": True}}
        )
        logger.info("Activated PromptProfile %s", profile_id)

    async def deactivate_profile(self, profile_id: str) -> None:
        result = await PromptProfileDocument.find_one(PromptProfileDocument.profile_id == profile_id)
        if result:
            result.is_active = False
            await result.save()

    async def list_profiles(self, limit: int = 20) -> list[PromptProfile]:
        docs = await PromptProfileDocument.find().sort(-PromptProfileDocument.created_at).limit(limit).to_list()
        return [d.to_domain() for d in docs]

    async def delete_profile(self, profile_id: str) -> None:
        await PromptProfileDocument.find(PromptProfileDocument.profile_id == profile_id).delete()

    # ------------------------------------------------------------------
    # OptimizationRunRepository
    # ------------------------------------------------------------------

    async def save_run(self, run: OptimizationRun) -> None:
        existing = await OptimizationRunDocument.find_one(OptimizationRunDocument.run_id == run.id)
        if existing:
            existing.update_from_domain(run)
            await existing.save()
        else:
            doc = OptimizationRunDocument.from_domain(run)
            await doc.insert()

    async def get_run(self, run_id: str) -> OptimizationRun | None:
        doc = await OptimizationRunDocument.find_one(OptimizationRunDocument.run_id == run_id)
        return doc.to_domain() if doc else None

    async def list_runs(self, limit: int = 20) -> list[OptimizationRun]:
        docs = await OptimizationRunDocument.find().sort(-OptimizationRunDocument.created_at).limit(limit).to_list()
        return [d.to_domain() for d in docs]

    async def update_run_status(self, run: OptimizationRun) -> None:
        await self.save_run(run)
