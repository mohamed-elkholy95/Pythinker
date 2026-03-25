"""Tests for PromptOptimizationService application service.

Covers:
- __init__: stores the three injected repositories
- start_run: creates OptimizationRun, persists it, raises ValueError when feature flag disabled
- start_run: merges caller config with min_cases_policy setting
- start_run: defaults to MIPROV2_LIGHT optimizer and empty config dict
- get_run: delegates to run_repo.get_run
- list_runs: delegates to run_repo.list_runs with limit parameter
- get_profile: delegates to profile_repo.get_profile
- get_active_profile: delegates to profile_repo.get_active_profile
- list_profiles: delegates to profile_repo.list_profiles with limit parameter
- activate_profile: raises ValueError when profile not found
- activate_profile: raises ValueError when profile disappears after activation
- activate_profile: activates profile, re-fetches, seeds bandit, returns profile
- activate_profile: seeds bandit for every patch using validation_summary score
- activate_profile: swallows bandit registration errors (logs warning only)
- rollback_profile: raises ValueError when profile not found
- rollback_profile: deactivates profile successfully
- load_artifact: delegates to artifact_repo.load_artifact
- load_artifact: returns None when artifact not found
- delete_artifact: delegates to artifact_repo.delete_artifact
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.prompt_optimization_service import PromptOptimizationService
from app.domain.models.prompt_optimization import OptimizationRun, OptimizationRunStatus, OptimizerType
from app.domain.models.prompt_profile import PromptPatch, PromptProfile, PromptTarget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repos() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Return (profile_repo, run_repo, artifact_repo) as AsyncMocks."""
    return AsyncMock(), AsyncMock(), AsyncMock()


def _make_service(
    profile_repo: AsyncMock | None = None,
    run_repo: AsyncMock | None = None,
    artifact_repo: AsyncMock | None = None,
) -> PromptOptimizationService:
    pr, rr, ar = _make_repos()
    return PromptOptimizationService(
        profile_repo=profile_repo or pr,
        run_repo=run_repo or rr,
        artifact_repo=artifact_repo or ar,
    )


def _make_profile(
    profile_id: str = "prof-1",
    name: str = "Test Profile",
    version: str = "1.0.0",
    source_run_id: str = "run-1",
    patches: list[PromptPatch] | None = None,
    validation_summary: dict[str, float] | None = None,
    is_active: bool = False,
) -> PromptProfile:
    actual_patches = patches or []
    return PromptProfile(
        id=profile_id,
        name=name,
        version=version,
        source_run_id=source_run_id,
        patches=actual_patches,
        validation_summary=validation_summary or {},
        is_active=is_active,
    )


def _make_patch(
    profile_id: str = "prof-1",
    target: PromptTarget = PromptTarget.PLANNER,
    patch_text: str = "Always think step by step.",
    variant_id: str = "v-1",
) -> PromptPatch:
    return PromptPatch(
        profile_id=profile_id,
        target=target,
        patch_text=patch_text,
        variant_id=variant_id,
    )


def _make_settings(
    feature_enabled: bool = True,
    min_cases: int = 100,
) -> MagicMock:
    settings = MagicMock()
    settings.feature_prompt_optimization_pipeline = feature_enabled
    settings.prompt_optimization_min_cases = min_cases
    return settings


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_stores_injected_repositories(self) -> None:
        pr, rr, ar = _make_repos()
        svc = PromptOptimizationService(profile_repo=pr, run_repo=rr, artifact_repo=ar)

        assert svc._profile_repo is pr
        assert svc._run_repo is rr
        assert svc._artifact_repo is ar


# ---------------------------------------------------------------------------
# start_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStartRun:
    async def test_raises_when_feature_flag_disabled(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(feature_enabled=False)
            with pytest.raises(ValueError, match="disabled"):
                await svc.start_run(target=PromptTarget.PLANNER)

        rr.save_run.assert_not_awaited()

    async def test_creates_run_with_correct_target(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings()
            run = await svc.start_run(target=PromptTarget.EXECUTION)

        assert run.target == PromptTarget.EXECUTION

    async def test_defaults_to_miprov2_light_optimizer(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings()
            run = await svc.start_run(target=PromptTarget.PLANNER)

        assert run.optimizer == OptimizerType.MIPROV2_LIGHT

    async def test_explicit_optimizer_is_preserved(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings()
            run = await svc.start_run(target=PromptTarget.SYSTEM, optimizer=OptimizerType.GEPA)

        assert run.optimizer == OptimizerType.GEPA

    async def test_run_starts_in_pending_status(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings()
            run = await svc.start_run(target=PromptTarget.PLANNER)

        assert run.status == OptimizationRunStatus.PENDING

    async def test_persists_run_via_save_run(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings()
            run = await svc.start_run(target=PromptTarget.PLANNER)

        rr.save_run.assert_awaited_once_with(run)

    async def test_injects_min_cases_policy_from_settings(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(min_cases=50)
            run = await svc.start_run(target=PromptTarget.PLANNER)

        assert run.config["min_cases_policy"] == 50

    async def test_merges_caller_config_with_min_cases_policy(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(min_cases=100)
            run = await svc.start_run(target=PromptTarget.PLANNER, config={"batch_size": 32})

        assert run.config["batch_size"] == 32
        assert run.config["min_cases_policy"] == 100

    async def test_empty_config_defaults_to_min_cases_policy_only(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(min_cases=200)
            run = await svc.start_run(target=PromptTarget.PLANNER)

        assert run.config == {"min_cases_policy": 200}

    async def test_returns_optimization_run_instance(self) -> None:
        _, rr, _ = _make_repos()
        svc = _make_service(run_repo=rr)

        with patch("app.application.services.prompt_optimization_service.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings()
            run = await svc.start_run(target=PromptTarget.PLANNER)

        assert isinstance(run, OptimizationRun)


# ---------------------------------------------------------------------------
# get_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetRun:
    async def test_delegates_to_run_repo(self) -> None:
        _, rr, _ = _make_repos()
        expected = MagicMock(spec=OptimizationRun)
        rr.get_run.return_value = expected
        svc = _make_service(run_repo=rr)

        result = await svc.get_run("run-42")

        assert result is expected
        rr.get_run.assert_awaited_once_with("run-42")

    async def test_returns_none_when_not_found(self) -> None:
        _, rr, _ = _make_repos()
        rr.get_run.return_value = None
        svc = _make_service(run_repo=rr)

        result = await svc.get_run("missing")

        assert result is None


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListRuns:
    async def test_delegates_with_default_limit(self) -> None:
        _, rr, _ = _make_repos()
        rr.list_runs.return_value = []
        svc = _make_service(run_repo=rr)

        await svc.list_runs()

        rr.list_runs.assert_awaited_once_with(limit=20)

    async def test_passes_custom_limit(self) -> None:
        _, rr, _ = _make_repos()
        rr.list_runs.return_value = []
        svc = _make_service(run_repo=rr)

        await svc.list_runs(limit=5)

        rr.list_runs.assert_awaited_once_with(limit=5)

    async def test_returns_list_from_repo(self) -> None:
        _, rr, _ = _make_repos()
        runs = [MagicMock(spec=OptimizationRun), MagicMock(spec=OptimizationRun)]
        rr.list_runs.return_value = runs
        svc = _make_service(run_repo=rr)

        result = await svc.list_runs()

        assert result is runs


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetProfile:
    async def test_delegates_to_profile_repo(self) -> None:
        pr, _, _ = _make_repos()
        profile = _make_profile(profile_id="p-7")
        pr.get_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        result = await svc.get_profile("p-7")

        assert result is profile
        pr.get_profile.assert_awaited_once_with("p-7")

    async def test_returns_none_when_not_found(self) -> None:
        pr, _, _ = _make_repos()
        pr.get_profile.return_value = None
        svc = _make_service(profile_repo=pr)

        result = await svc.get_profile("ghost")

        assert result is None


# ---------------------------------------------------------------------------
# get_active_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetActiveProfile:
    async def test_delegates_to_profile_repo(self) -> None:
        pr, _, _ = _make_repos()
        profile = _make_profile(is_active=True)
        pr.get_active_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        result = await svc.get_active_profile()

        assert result is profile
        pr.get_active_profile.assert_awaited_once()

    async def test_returns_none_when_no_active_profile(self) -> None:
        pr, _, _ = _make_repos()
        pr.get_active_profile.return_value = None
        svc = _make_service(profile_repo=pr)

        result = await svc.get_active_profile()

        assert result is None


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListProfiles:
    async def test_delegates_with_default_limit(self) -> None:
        pr, _, _ = _make_repos()
        pr.list_profiles.return_value = []
        svc = _make_service(profile_repo=pr)

        await svc.list_profiles()

        pr.list_profiles.assert_awaited_once_with(limit=20)

    async def test_passes_custom_limit(self) -> None:
        pr, _, _ = _make_repos()
        pr.list_profiles.return_value = []
        svc = _make_service(profile_repo=pr)

        await svc.list_profiles(limit=10)

        pr.list_profiles.assert_awaited_once_with(limit=10)

    async def test_returns_list_from_repo(self) -> None:
        pr, _, _ = _make_repos()
        profiles = [_make_profile("p-1"), _make_profile("p-2")]
        pr.list_profiles.return_value = profiles
        svc = _make_service(profile_repo=pr)

        result = await svc.list_profiles()

        assert result is profiles


# ---------------------------------------------------------------------------
# activate_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestActivateProfile:
    async def test_raises_when_profile_not_found(self) -> None:
        pr, _, _ = _make_repos()
        pr.get_profile.return_value = None
        svc = _make_service(profile_repo=pr)

        with pytest.raises(ValueError, match="PromptProfile not found"):
            await svc.activate_profile("missing-id")

    async def test_raises_when_profile_disappears_after_activation(self) -> None:
        pr, _, _ = _make_repos()
        profile = _make_profile(profile_id="p-1")
        # First call (pre-activation check) returns profile; second call (re-fetch) returns None.
        pr.get_profile.side_effect = [profile, None]
        svc = _make_service(profile_repo=pr)

        with (
            patch("app.application.services.prompt_optimization_service.get_prompt_optimizer"),
            pytest.raises(ValueError, match="disappeared after activation"),
        ):
            await svc.activate_profile("p-1")

    async def test_calls_activate_profile_on_repo(self) -> None:
        pr, _, _ = _make_repos()
        profile_before = _make_profile(profile_id="p-1")
        profile_after = _make_profile(profile_id="p-1", is_active=True)
        pr.get_profile.side_effect = [profile_before, profile_after]
        svc = _make_service(profile_repo=pr)

        mock_optimizer = MagicMock()
        with patch("app.application.services.prompt_optimization_service.get_prompt_optimizer") as mock_go:
            mock_go.return_value = mock_optimizer
            await svc.activate_profile("p-1")

        pr.activate_profile.assert_awaited_once_with("p-1")

    async def test_returns_re_fetched_profile(self) -> None:
        pr, _, _ = _make_repos()
        profile_before = _make_profile(profile_id="p-1", is_active=False)
        profile_after = _make_profile(profile_id="p-1", is_active=True)
        pr.get_profile.side_effect = [profile_before, profile_after]
        svc = _make_service(profile_repo=pr)

        mock_optimizer = MagicMock()
        with patch("app.application.services.prompt_optimization_service.get_prompt_optimizer") as mock_go:
            mock_go.return_value = mock_optimizer
            result = await svc.activate_profile("p-1")

        assert result is profile_after

    async def test_seeds_bandit_for_each_patch(self) -> None:
        pr, _, _ = _make_repos()
        patch_planner = _make_patch(
            profile_id="p-1", target=PromptTarget.PLANNER, patch_text="Think.", variant_id="v-a"
        )
        patch_exec = _make_patch(
            profile_id="p-1", target=PromptTarget.EXECUTION, patch_text="Execute.", variant_id="v-b"
        )
        profile = _make_profile(
            profile_id="p-1",
            patches=[patch_planner, patch_exec],
            validation_summary={"planner_optimized": 0.85, "execution_optimized": 0.75},
        )
        pr.get_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        mock_optimizer = MagicMock()
        with patch("app.application.services.prompt_optimization_service.get_prompt_optimizer") as mock_go:
            mock_go.return_value = mock_optimizer
            await svc.activate_profile("p-1")

        assert mock_optimizer.register_dspy_profile.call_count == 2

    async def test_passes_correct_validation_score_to_bandit(self) -> None:
        pr, _, _ = _make_repos()
        patch_planner = _make_patch(
            profile_id="p-1", target=PromptTarget.PLANNER, patch_text="Think.", variant_id="v-1"
        )
        profile = _make_profile(
            profile_id="p-1",
            patches=[patch_planner],
            validation_summary={"planner_optimized": 0.90},
        )
        pr.get_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        mock_optimizer = MagicMock()
        with patch("app.application.services.prompt_optimization_service.get_prompt_optimizer") as mock_go:
            mock_go.return_value = mock_optimizer
            await svc.activate_profile("p-1")

        mock_optimizer.register_dspy_profile.assert_called_once_with(
            profile_id="p-1",
            target=PromptTarget.PLANNER.value,
            patch_text="Think.",
            validation_score=0.90,
        )

    async def test_defaults_validation_score_to_zero_when_key_absent(self) -> None:
        pr, _, _ = _make_repos()
        patch_planner = _make_patch(
            profile_id="p-1", target=PromptTarget.PLANNER, patch_text="Think.", variant_id="v-1"
        )
        # validation_summary does not contain the key for this patch
        profile = _make_profile(profile_id="p-1", patches=[patch_planner], validation_summary={})
        pr.get_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        mock_optimizer = MagicMock()
        with patch("app.application.services.prompt_optimization_service.get_prompt_optimizer") as mock_go:
            mock_go.return_value = mock_optimizer
            await svc.activate_profile("p-1")

        _, kwargs = mock_optimizer.register_dspy_profile.call_args
        assert kwargs["validation_score"] == 0.0

    async def test_swallows_bandit_registration_error(self) -> None:
        pr, _, _ = _make_repos()
        patch_planner = _make_patch(
            profile_id="p-1", target=PromptTarget.PLANNER, patch_text="Think.", variant_id="v-1"
        )
        profile = _make_profile(profile_id="p-1", patches=[patch_planner])
        pr.get_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        mock_optimizer = MagicMock()
        mock_optimizer.register_dspy_profile.side_effect = RuntimeError("bandit internal error")
        with patch("app.application.services.prompt_optimization_service.get_prompt_optimizer") as mock_go:
            mock_go.return_value = mock_optimizer
            # Must not raise despite the bandit error
            result = await svc.activate_profile("p-1")

        assert result is profile  # still returns the profile


# ---------------------------------------------------------------------------
# rollback_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackProfile:
    async def test_raises_when_profile_not_found(self) -> None:
        pr, _, _ = _make_repos()
        pr.get_profile.return_value = None
        svc = _make_service(profile_repo=pr)

        with pytest.raises(ValueError, match="PromptProfile not found"):
            await svc.rollback_profile("missing-id")

    async def test_deactivates_profile_via_repo(self) -> None:
        pr, _, _ = _make_repos()
        profile = _make_profile(profile_id="p-5", is_active=True)
        pr.get_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        await svc.rollback_profile("p-5")

        pr.deactivate_profile.assert_awaited_once_with("p-5")

    async def test_returns_none_on_success(self) -> None:
        pr, _, _ = _make_repos()
        profile = _make_profile(profile_id="p-5")
        pr.get_profile.return_value = profile
        svc = _make_service(profile_repo=pr)

        result = await svc.rollback_profile("p-5")

        assert result is None


# ---------------------------------------------------------------------------
# load_artifact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoadArtifact:
    async def test_delegates_to_artifact_repo(self) -> None:
        _, _, ar = _make_repos()
        ar.load_artifact.return_value = b"\x00\x01binary"
        svc = _make_service(artifact_repo=ar)

        result = await svc.load_artifact("art-99")

        assert result == b"\x00\x01binary"
        ar.load_artifact.assert_awaited_once_with("art-99")

    async def test_returns_none_when_not_found(self) -> None:
        _, _, ar = _make_repos()
        ar.load_artifact.return_value = None
        svc = _make_service(artifact_repo=ar)

        result = await svc.load_artifact("ghost-art")

        assert result is None


# ---------------------------------------------------------------------------
# delete_artifact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDeleteArtifact:
    async def test_delegates_to_artifact_repo(self) -> None:
        _, _, ar = _make_repos()
        svc = _make_service(artifact_repo=ar)

        await svc.delete_artifact("art-77")

        ar.delete_artifact.assert_awaited_once_with("art-77")

    async def test_returns_none(self) -> None:
        _, _, ar = _make_repos()
        ar.delete_artifact.return_value = None
        svc = _make_service(artifact_repo=ar)

        result = await svc.delete_artifact("art-77")

        assert result is None
