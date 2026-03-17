"""Domain models for prompt profiles produced by offline optimization runs.

A PromptProfile is an immutable, versioned set of prompt patches applied at
runtime on top of the baseline prompt builders.  Profiles are generated
offline by the DSPy/GEPA optimizer and published via the admin API.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PromptTarget(str, Enum):
    """Which prompt surface this profile/patch targets."""

    PLANNER = "planner"
    EXECUTION = "execution"
    SYSTEM = "system"


class PromptPatch(BaseModel):
    """A single patch to inject into a prompt surface.

    Patches are applied by the ProfileResolver as deterministic text blocks
    appended to (or replacing sections of) the baseline prompt output.
    """

    model_config = ConfigDict(frozen=True)

    target: PromptTarget
    profile_id: str
    variant_id: str
    patch_text: str
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class PromptProfile(BaseModel):
    """Immutable, versioned prompt profile produced by an optimization run.

    Profiles are published via the admin API and selected at runtime via the
    PromptProfileResolver based on feature flags and canary policy.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_run_id: str
    patches: list[PromptPatch] = Field(default_factory=list)
    validation_summary: dict[str, float] = Field(default_factory=dict)
    is_active: bool = False

    @model_validator(mode="after")
    def _validate_patch_profile_ids(self) -> PromptProfile:
        """Ensure all patches reference this profile's ID."""
        for patch in self.patches:
            if patch.profile_id and patch.profile_id != self.id:
                raise ValueError(f"Patch profile_id '{patch.profile_id}' does not match profile id '{self.id}'")
        return self

    def get_patch(self, target: PromptTarget) -> PromptPatch | None:
        """Return the patch for a specific target, or None if absent."""
        for patch in self.patches:
            if patch.target == target:
                return patch
        return None

    def has_patch(self, target: PromptTarget) -> bool:
        """Check whether a patch exists for the given target."""
        return self.get_patch(target) is not None

    @property
    def targets(self) -> list[PromptTarget]:
        """List of targets covered by this profile."""
        return [p.target for p in self.patches]


class PromptProfileSummary(BaseModel):
    """Lightweight summary for list endpoints."""

    id: str
    name: str
    version: str
    created_at: datetime
    source_run_id: str
    is_active: bool
    targets: list[PromptTarget]
    validation_summary: dict[str, float] = Field(default_factory=dict)

    @classmethod
    def from_profile(cls, profile: PromptProfile) -> PromptProfileSummary:
        return cls(
            id=profile.id,
            name=profile.name,
            version=profile.version,
            created_at=profile.created_at,
            source_run_id=profile.source_run_id,
            is_active=profile.is_active,
            targets=profile.targets,
            validation_summary=profile.validation_summary,
        )


class ProfileSelectionMode(str, Enum):
    """How the profile was selected for the current request."""

    ACTIVE = "active"  # Feature flag + active profile pointer
    CANARY = "canary"  # Session-hash canary assignment
    SHADOW = "shadow"  # Computed but not applied (shadow/delta mode)
    BASELINE = "baseline"  # No profile; baseline prompts only


class ProfileSelectionContext(BaseModel):
    """Carries the resolved profile and selection metadata for observability."""

    mode: ProfileSelectionMode
    profile: PromptProfile | None = None
    profile_id: str | None = None
    reason: str = ""
    session_id: str = ""
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
