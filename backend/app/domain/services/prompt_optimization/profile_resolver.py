"""Runtime prompt profile resolver.

Resolves which ``PromptProfile`` (if any) should be applied to a request,
based on feature flags and canary policy.

Selection flow:
  1. If ``feature_prompt_profile_runtime`` is disabled → BASELINE (no patch).
  2. If ``prompt_profile_active_id`` is set → use that specific profile.
  3. Otherwise fetch the DB-active profile.
  4. Within the selected profile, canary gating:
     - ``prompt_profile_canary_percent == 0`` → apply to all sessions.
     - Otherwise → hash(session_id) mod 100 < canary_percent → apply.
  5. If ``feature_prompt_profile_shadow`` is enabled and runtime is disabled →
     SHADOW mode (compute but do not apply the patch).

Any error in this path → immediately falls back to BASELINE and emits a
warning log — optimization never breaks the user-facing flow.
"""

from __future__ import annotations

import hashlib
import logging

from app.domain.models.prompt_profile import (
    ProfileSelectionContext,
    ProfileSelectionMode,
    PromptProfile,
    PromptTarget,
)
from app.domain.repositories.prompt_profile_repository import PromptProfileRepository

logger = logging.getLogger(__name__)


def _session_hash(session_id: str) -> int:
    """Deterministic integer 0..99 from session_id."""
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    return int(digest[:8], 16) % 100


class PromptProfileResolver:
    """Resolves the active PromptProfile for a given session at runtime.

    Designed to be injected into agent services or prompt builders.
    Stateless once constructed (repository is async-capable).
    """

    def __init__(
        self,
        repository: PromptProfileRepository,
        *,
        feature_runtime: bool = False,
        feature_shadow: bool = True,
        canary_percent: int = 0,
        active_profile_id: str | None = None,
    ) -> None:
        self._repo = repository
        self._feature_runtime = feature_runtime
        self._feature_shadow = feature_shadow
        self._canary_percent = canary_percent
        self._active_profile_id = active_profile_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve(
        self,
        session_id: str,
        *,
        target: PromptTarget | None = None,
    ) -> ProfileSelectionContext:
        """Resolve the profile selection context for this request.

        Args:
            session_id: The current session ID (used for canary hashing).
            target:     If set, also checks that the resolved profile covers
                        this target; returns BASELINE if not.

        Returns:
            ``ProfileSelectionContext`` — always returns something, never raises.
        """
        try:
            return await self._resolve_internal(session_id, target=target)
        except Exception as exc:
            logger.warning("PromptProfileResolver error (falling back to baseline): %s", exc)
            return ProfileSelectionContext(
                mode=ProfileSelectionMode.BASELINE,
                reason=f"Resolver error: {exc}",
                session_id=session_id,
            )

    def apply_patch(
        self,
        prompt: str,
        ctx: ProfileSelectionContext,
        target: PromptTarget,
    ) -> str:
        """Apply a profile patch to a prompt string.

        In SHADOW mode the patch is NOT applied (but the context carries the
        would-be patch for delta measurement).

        Args:
            prompt: Baseline prompt string.
            ctx:    Selection context from ``resolve()``.
            target: Which surface this prompt is for.

        Returns:
            Patched prompt (or original prompt on any error / non-active mode).
        """
        if ctx.mode not in (ProfileSelectionMode.ACTIVE, ProfileSelectionMode.CANARY):
            return prompt
        if ctx.profile is None:
            return prompt

        patch = ctx.profile.get_patch(target)
        if patch is None:
            return prompt

        try:
            patched = self._apply_patch_text(prompt, patch.patch_text)
            logger.debug(
                "Applied profile patch %s/%s to %s prompt",
                ctx.profile_id,
                patch.variant_id,
                target.value,
            )
            return patched
        except Exception as exc:
            logger.warning("Failed to apply profile patch (using baseline): %s", exc)
            return prompt

    def should_use_profile(self, *, session_id: str, canary_percent: int) -> bool:
        """Return True if this session should receive a profile patch.

        Implements the deterministic session-hash gating from the plan contract.
        """
        if canary_percent == 0:
            return True
        return _session_hash(session_id) < canary_percent

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_internal(
        self,
        session_id: str,
        target: PromptTarget | None,
    ) -> ProfileSelectionContext:
        # Shadow-only mode (compute delta, don't apply)
        if not self._feature_runtime and self._feature_shadow:
            profile = await self._fetch_profile()
            if profile and (target is None or profile.has_patch(target)):
                return ProfileSelectionContext(
                    mode=ProfileSelectionMode.SHADOW,
                    profile=profile,
                    profile_id=profile.id,
                    reason="shadow_mode",
                    session_id=session_id,
                )
            return ProfileSelectionContext(
                mode=ProfileSelectionMode.BASELINE,
                reason="no_active_profile",
                session_id=session_id,
            )

        # Runtime disabled
        if not self._feature_runtime:
            return ProfileSelectionContext(
                mode=ProfileSelectionMode.BASELINE,
                reason="runtime_disabled",
                session_id=session_id,
            )

        # Fetch profile
        profile = await self._fetch_profile()
        if profile is None:
            return ProfileSelectionContext(
                mode=ProfileSelectionMode.BASELINE,
                reason="no_active_profile",
                session_id=session_id,
            )

        # Target check
        if target is not None and not profile.has_patch(target):
            return ProfileSelectionContext(
                mode=ProfileSelectionMode.BASELINE,
                reason=f"profile_missing_target_{target.value}",
                session_id=session_id,
            )

        # Canary gating
        if self._canary_percent > 0:
            bucket = _session_hash(session_id)
            if bucket < self._canary_percent:
                return ProfileSelectionContext(
                    mode=ProfileSelectionMode.CANARY,
                    profile=profile,
                    profile_id=profile.id,
                    reason=f"canary_bucket_{bucket}_{self._canary_percent}pct",
                    session_id=session_id,
                )
            return ProfileSelectionContext(
                mode=ProfileSelectionMode.BASELINE,
                reason=f"canary_excluded_bucket_{bucket}",
                session_id=session_id,
            )

        # Full active rollout
        return ProfileSelectionContext(
            mode=ProfileSelectionMode.ACTIVE,
            profile=profile,
            profile_id=profile.id,
            reason="active_profile",
            session_id=session_id,
        )

    async def _fetch_profile(self) -> PromptProfile | None:
        """Fetch profile by explicit ID or the DB-active profile."""
        if self._active_profile_id:
            return await self._repo.get_profile(self._active_profile_id)
        return await self._repo.get_active_profile()

    @staticmethod
    def _apply_patch_text(prompt: str, patch_text: str) -> str:
        """Append the patch text block to the prompt.

        The patch is appended as a clearly delimited block so it can be
        tracked in logs without contaminating the original prompt structure.
        """
        return f"{prompt}\n\n<!-- profile_patch -->\n{patch_text}\n<!-- /profile_patch -->"


# ---------------------------------------------------------------------------
# Factory — built from settings at runtime
# Note: This factory imports app.core.config (infrastructure).  It is called
# from the interfaces/application layer (agent_task_runner.py), not from
# domain business logic, so the DDD boundary is maintained at the call site.
# ---------------------------------------------------------------------------


def build_profile_resolver_from_settings(
    repository: PromptProfileRepository,
) -> PromptProfileResolver:
    """Construct a PromptProfileResolver wired to current app settings.

    This factory is intended to be called from the interfaces or application
    layer where config access is permitted — not from domain business logic.
    """
    from app.core.config import get_settings

    settings = get_settings()
    return PromptProfileResolver(
        repository=repository,
        feature_runtime=getattr(settings, "feature_prompt_profile_runtime", False),
        feature_shadow=getattr(settings, "feature_prompt_profile_shadow", True),
        canary_percent=getattr(settings, "prompt_profile_canary_percent", 0),
        active_profile_id=getattr(settings, "prompt_profile_active_id", None),
    )
