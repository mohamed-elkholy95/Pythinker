"""Abstract repository protocol for PromptProfile and OptimizationRun persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.prompt_optimization import OptimizationRun
from app.domain.models.prompt_profile import PromptProfile


@runtime_checkable
class PromptProfileRepository(Protocol):
    """Persistence contract for prompt profiles."""

    async def save_profile(self, profile: PromptProfile) -> None:
        """Persist a new or updated profile."""
        ...

    async def get_profile(self, profile_id: str) -> PromptProfile | None:
        """Return profile by ID, or None if not found."""
        ...

    async def get_active_profile(self) -> PromptProfile | None:
        """Return the currently active profile, or None if none is active."""
        ...

    async def activate_profile(self, profile_id: str) -> None:
        """Mark profile as active, deactivating any previous active profile."""
        ...

    async def deactivate_profile(self, profile_id: str) -> None:
        """Deactivate a specific profile without activating another."""
        ...

    async def list_profiles(self, limit: int = 20) -> list[PromptProfile]:
        """Return the most recent profiles, ordered by created_at desc."""
        ...

    async def delete_profile(self, profile_id: str) -> None:
        """Hard-delete a profile (admin rollback only)."""
        ...


@runtime_checkable
class OptimizationRunRepository(Protocol):
    """Persistence contract for optimization run records."""

    async def save_run(self, run: OptimizationRun) -> None:
        """Persist a new or updated run record."""
        ...

    async def get_run(self, run_id: str) -> OptimizationRun | None:
        """Return run by ID, or None if not found."""
        ...

    async def list_runs(self, limit: int = 20) -> list[OptimizationRun]:
        """Return most recent runs, ordered by created_at desc."""
        ...

    async def update_run_status(self, run: OptimizationRun) -> None:
        """Persist status/metric updates for an in-flight run."""
        ...


@runtime_checkable
class PromptArtifactRepository(Protocol):
    """Persistence contract for binary optimization artifacts (DSPy .json dumps)."""

    async def save_artifact(self, run_id: str, data: bytes) -> str:
        """Store artifact bytes, return artifact ID."""
        ...

    async def load_artifact(self, artifact_id: str) -> bytes | None:
        """Load artifact bytes by artifact ID."""
        ...

    async def delete_artifact(self, artifact_id: str) -> None:
        """Remove artifact (cleanup old runs)."""
        ...
