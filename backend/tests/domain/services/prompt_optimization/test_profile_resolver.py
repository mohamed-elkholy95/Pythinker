"""Tests for the runtime prompt profile resolver."""

from __future__ import annotations

import pytest

from app.domain.models.prompt_profile import (
    ProfileSelectionContext,
    ProfileSelectionMode,
    PromptPatch,
    PromptProfile,
    PromptTarget,
)
from app.domain.services.prompt_optimization.profile_resolver import (
    PromptProfileResolver,
    _session_hash,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROFILE_ID = "test-profile-001"


def _make_profile(
    profile_id: str = _PROFILE_ID,
    targets: list[PromptTarget] | None = None,
    is_active: bool = True,
) -> PromptProfile:
    targets = targets or [PromptTarget.PLANNER, PromptTarget.EXECUTION]
    patches = [
        PromptPatch(
            target=t,
            profile_id=profile_id,
            variant_id=f"v1-{t.value}",
            patch_text=f"Optimized instructions for {t.value}",
        )
        for t in targets
    ]
    return PromptProfile(
        id=profile_id,
        name="test-profile",
        version="1.0.0",
        source_run_id="run-abc",
        patches=patches,
        is_active=is_active,
    )


class FakeProfileRepository:
    """In-memory stub satisfying the PromptProfileRepository protocol."""

    def __init__(
        self,
        profiles: list[PromptProfile] | None = None,
        active: PromptProfile | None = None,
    ) -> None:
        self._profiles = {p.id: p for p in (profiles or [])}
        self._active = active

    async def save_profile(self, profile: PromptProfile) -> None:
        self._profiles[profile.id] = profile

    async def get_profile(self, profile_id: str) -> PromptProfile | None:
        return self._profiles.get(profile_id)

    async def get_active_profile(self) -> PromptProfile | None:
        return self._active

    async def activate_profile(self, profile_id: str) -> None:
        self._active = self._profiles.get(profile_id)

    async def deactivate_profile(self, profile_id: str) -> None:
        if self._active and self._active.id == profile_id:
            self._active = None

    async def list_profiles(self, limit: int = 20) -> list[PromptProfile]:
        return list(self._profiles.values())[:limit]

    async def delete_profile(self, profile_id: str) -> None:
        self._profiles.pop(profile_id, None)


class FakeErrorRepository(FakeProfileRepository):
    """Raises on every call to simulate repository failures."""

    async def get_profile(self, profile_id: str) -> PromptProfile | None:
        raise RuntimeError("DB connection lost")

    async def get_active_profile(self) -> PromptProfile | None:
        raise RuntimeError("DB connection lost")


# ---------------------------------------------------------------------------
# _session_hash
# ---------------------------------------------------------------------------


class TestSessionHash:
    """Tests for the deterministic session-hash function."""

    def test_deterministic(self) -> None:
        """Same session_id always produces the same bucket."""
        assert _session_hash("session-abc") == _session_hash("session-abc")

    def test_range_0_to_99(self) -> None:
        """Hash always returns an int in [0, 99]."""
        for i in range(200):
            h = _session_hash(f"session-{i}")
            assert 0 <= h <= 99, f"Out of range: {h}"

    def test_different_ids_differ(self) -> None:
        """Different session IDs should (usually) produce different buckets."""
        hashes = {_session_hash(f"sid-{i}") for i in range(100)}
        # With 100 random IDs mapped to 0-99, we expect reasonable spread
        assert len(hashes) > 30

    def test_empty_string(self) -> None:
        """Empty session_id should not raise."""
        h = _session_hash("")
        assert 0 <= h <= 99


# ---------------------------------------------------------------------------
# resolve() — baseline modes
# ---------------------------------------------------------------------------


class TestResolveBaseline:
    """Tests where the resolver returns BASELINE mode."""

    @pytest.mark.asyncio
    async def test_runtime_disabled_shadow_disabled(self) -> None:
        """Both flags off → BASELINE, reason=runtime_disabled."""
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=False,
            feature_shadow=False,
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.BASELINE
        assert "runtime_disabled" in ctx.reason

    @pytest.mark.asyncio
    async def test_runtime_enabled_no_profile(self) -> None:
        """Runtime on but no active profile → BASELINE."""
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=True,
            feature_shadow=False,
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.BASELINE
        assert "no_active_profile" in ctx.reason

    @pytest.mark.asyncio
    async def test_profile_missing_target(self) -> None:
        """Active profile exists but doesn't cover the requested target."""
        profile = _make_profile(targets=[PromptTarget.PLANNER])
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=True,
            feature_shadow=False,
        )
        ctx = await resolver.resolve("sess-1", target=PromptTarget.EXECUTION)
        assert ctx.mode == ProfileSelectionMode.BASELINE
        assert "missing_target" in ctx.reason


# ---------------------------------------------------------------------------
# resolve() — shadow mode
# ---------------------------------------------------------------------------


class TestResolveShadow:
    """Tests for shadow mode (compute but don't apply)."""

    @pytest.mark.asyncio
    async def test_shadow_with_active_profile(self) -> None:
        """Runtime off + shadow on + active profile → SHADOW."""
        profile = _make_profile()
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=False,
            feature_shadow=True,
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.SHADOW
        assert ctx.profile is not None
        assert ctx.profile_id == _PROFILE_ID

    @pytest.mark.asyncio
    async def test_shadow_no_profile_falls_to_baseline(self) -> None:
        """Shadow on but no profile → BASELINE."""
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=False,
            feature_shadow=True,
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.BASELINE

    @pytest.mark.asyncio
    async def test_shadow_target_mismatch(self) -> None:
        """Shadow mode but profile doesn't cover the requested target."""
        profile = _make_profile(targets=[PromptTarget.PLANNER])
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=False,
            feature_shadow=True,
        )
        ctx = await resolver.resolve("sess-1", target=PromptTarget.SYSTEM)
        assert ctx.mode == ProfileSelectionMode.BASELINE


# ---------------------------------------------------------------------------
# resolve() — active mode (full rollout)
# ---------------------------------------------------------------------------


class TestResolveActive:
    """Tests for ACTIVE mode (runtime enabled, canary 0%)."""

    @pytest.mark.asyncio
    async def test_active_from_db(self) -> None:
        """Runtime on + canary 0 + DB-active profile → ACTIVE."""
        profile = _make_profile()
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=True,
            canary_percent=0,
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.ACTIVE
        assert ctx.profile_id == _PROFILE_ID

    @pytest.mark.asyncio
    async def test_active_from_explicit_id(self) -> None:
        """active_profile_id config overrides the DB-active profile."""
        profile = _make_profile(profile_id="explicit-001")
        repo = FakeProfileRepository(profiles=[profile])
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=True,
            active_profile_id="explicit-001",
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.ACTIVE
        assert ctx.profile_id == "explicit-001"

    @pytest.mark.asyncio
    async def test_active_carries_session_id(self) -> None:
        profile = _make_profile()
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        resolver = PromptProfileResolver(repo, feature_runtime=True)
        ctx = await resolver.resolve("my-session-42")
        assert ctx.session_id == "my-session-42"


# ---------------------------------------------------------------------------
# resolve() — canary mode
# ---------------------------------------------------------------------------


class TestResolveCanary:
    """Tests for canary percentage gating."""

    @pytest.mark.asyncio
    async def test_canary_includes_matching_sessions(self) -> None:
        """Sessions whose hash < canary_percent get CANARY mode."""
        profile = _make_profile()
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=True,
            canary_percent=100,
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.CANARY

    @pytest.mark.asyncio
    async def test_canary_excludes_sessions(self) -> None:
        """canary_percent=0 with runtime on → ACTIVE (not canary)."""
        # canary_percent > 0 but session hash >= percent
        profile = _make_profile()
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        # canary_percent=1 means only hash 0 gets through
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=True,
            canary_percent=1,
        )
        # Most sessions will be excluded; find one
        excluded = False
        for i in range(100):
            ctx = await resolver.resolve(f"sess-{i}")
            if ctx.mode == ProfileSelectionMode.BASELINE:
                excluded = True
                break
        assert excluded, "Expected at least one session to be excluded from canary"

    @pytest.mark.asyncio
    async def test_canary_deterministic(self) -> None:
        """Same session always gets the same canary decision."""
        profile = _make_profile()
        repo = FakeProfileRepository(profiles=[profile], active=profile)
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=True,
            canary_percent=50,
        )
        ctx_a = await resolver.resolve("deterministic-session")
        ctx_b = await resolver.resolve("deterministic-session")
        assert ctx_a.mode == ctx_b.mode


# ---------------------------------------------------------------------------
# resolve() — error fallback
# ---------------------------------------------------------------------------


class TestResolveErrorFallback:
    """Tests that resolver errors never propagate — always return BASELINE."""

    @pytest.mark.asyncio
    async def test_repo_error_returns_baseline(self) -> None:
        """Repository failure → BASELINE with error reason."""
        repo = FakeErrorRepository()
        resolver = PromptProfileResolver(repo, feature_runtime=True)
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.BASELINE
        assert "Resolver error" in ctx.reason

    @pytest.mark.asyncio
    async def test_shadow_repo_error_returns_baseline(self) -> None:
        repo = FakeErrorRepository()
        resolver = PromptProfileResolver(
            repo,
            feature_runtime=False,
            feature_shadow=True,
        )
        ctx = await resolver.resolve("sess-1")
        assert ctx.mode == ProfileSelectionMode.BASELINE


class TestApplyPatch:
    """Tests for the patch application helper."""

    def test_applies_in_active_mode(self) -> None:
        profile = _make_profile()
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo, feature_runtime=True)
        ctx = ProfileSelectionContext(
            mode=ProfileSelectionMode.ACTIVE,
            profile=profile,
            profile_id=profile.id,
            session_id="sess-1",
        )
        patched = resolver.apply_patch("BASE PROMPT", ctx, PromptTarget.PLANNER)
        assert "profile_patch" in patched
        assert "Optimized instructions for planner" in patched

    def test_applies_in_canary_mode(self) -> None:
        profile = _make_profile()
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo, feature_runtime=True)
        ctx = ProfileSelectionContext(
            mode=ProfileSelectionMode.CANARY,
            profile=profile,
            profile_id=profile.id,
            session_id="sess-1",
        )
        patched = resolver.apply_patch("BASE", ctx, PromptTarget.EXECUTION)
        assert "profile_patch" in patched

    def test_no_patch_in_shadow_mode(self) -> None:
        profile = _make_profile()
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo)
        ctx = ProfileSelectionContext(
            mode=ProfileSelectionMode.SHADOW,
            profile=profile,
            profile_id=profile.id,
            session_id="sess-1",
        )
        result = resolver.apply_patch("BASE PROMPT", ctx, PromptTarget.PLANNER)
        assert result == "BASE PROMPT"

    def test_no_patch_in_baseline_mode(self) -> None:
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo)
        ctx = ProfileSelectionContext(
            mode=ProfileSelectionMode.BASELINE,
            session_id="sess-1",
        )
        result = resolver.apply_patch("BASE PROMPT", ctx, PromptTarget.PLANNER)
        assert result == "BASE PROMPT"

    def test_missing_target_returns_original(self) -> None:
        """Profile has PLANNER but we request SYSTEM → no change."""
        profile = _make_profile(targets=[PromptTarget.PLANNER])
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo, feature_runtime=True)
        ctx = ProfileSelectionContext(
            mode=ProfileSelectionMode.ACTIVE,
            profile=profile,
            profile_id=profile.id,
            session_id="sess-1",
        )
        result = resolver.apply_patch("BASE", ctx, PromptTarget.SYSTEM)
        assert result == "BASE"


class TestShouldUseProfile:
    """Tests for the canary helper method."""

    def test_zero_percent_always_true(self) -> None:
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo)
        assert resolver.should_use_profile(session_id="any", canary_percent=0) is True

    def test_hundred_percent_always_true(self) -> None:
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo)
        # All hashes are 0-99, so < 100 is always True
        for i in range(50):
            assert (
                resolver.should_use_profile(
                    session_id=f"sess-{i}",
                    canary_percent=100,
                )
                is True
            )

    def test_partial_percent_deterministic(self) -> None:
        repo = FakeProfileRepository()
        resolver = PromptProfileResolver(repo)
        result_a = resolver.should_use_profile(session_id="test-sess", canary_percent=50)
        result_b = resolver.should_use_profile(session_id="test-sess", canary_percent=50)
        assert result_a == result_b
