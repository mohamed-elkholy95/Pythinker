"""Tests for fast draft plan routing in PlanActFlow.

These tests exercise ``_route_after_planning`` in isolation — the method is
pure (no I/O, no async) so we can test all routing branches without spinning
up the full async flow.
"""

from unittest.mock import MagicMock

import pytest

from app.domain.models.state_model import AgentStatus
from app.domain.services.flows.plan_act import PlanActFlow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(
    *,
    feature_fast_draft_plan: bool = True,
    fast_draft_plan_max_steps: int = 5,
) -> MagicMock:
    settings = MagicMock()
    settings.feature_fast_draft_plan = feature_fast_draft_plan
    settings.fast_draft_plan_max_steps = fast_draft_plan_max_steps
    return settings


def _make_flow(
    *,
    research_mode: str | None = "deep_research",
    has_verifier: bool = True,
    plan_steps: int = 3,
) -> PlanActFlow:
    """Create a minimal PlanActFlow instance for routing tests.

    Uses ``__new__`` to skip the heavyweight ``__init__`` — only the
    attributes read by ``_route_after_planning`` are set.
    """
    flow = PlanActFlow.__new__(PlanActFlow)
    flow._research_mode = research_mode
    flow.verifier = MagicMock() if has_verifier else None

    if plan_steps > 0:
        flow.plan = MagicMock()
        flow.plan.steps = [MagicMock() for _ in range(plan_steps)]
    else:
        flow.plan = None

    return flow


def _use_draft(flow: PlanActFlow, settings: MagicMock) -> bool:
    """Replicate the use_draft expression from _run_with_trace."""
    return settings.feature_fast_draft_plan and flow._research_mode is not None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_research_mode_with_draft_flag_skips_verification() -> None:
    """feature on + research mode + small plan → EXECUTING (skip verification)."""
    settings = _make_settings(feature_fast_draft_plan=True, fast_draft_plan_max_steps=5)
    flow = _make_flow(research_mode="deep_research", has_verifier=True, plan_steps=3)

    status, reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.EXECUTING
    assert "fast draft" in reason
    assert "3" in reason  # step count mentioned in reason


def test_non_research_mode_still_verifies() -> None:
    """feature on + NO research mode → research_mode is None → use_draft=False → VERIFYING."""
    settings = _make_settings(feature_fast_draft_plan=True, fast_draft_plan_max_steps=5)
    flow = _make_flow(research_mode=None, has_verifier=True, plan_steps=3)

    status, reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.VERIFYING
    assert "verifier" in reason


def test_draft_flag_off_still_verifies() -> None:
    """feature off + research mode → use_draft=False → normal VERIFYING path."""
    settings = _make_settings(feature_fast_draft_plan=False, fast_draft_plan_max_steps=5)
    flow = _make_flow(research_mode="deep_research", has_verifier=True, plan_steps=3)

    status, reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.VERIFYING
    assert "verifier" in reason


def test_large_draft_plan_still_verifies() -> None:
    """feature on + research mode + plan > max_steps → VERIFYING (not skipped)."""
    settings = _make_settings(feature_fast_draft_plan=True, fast_draft_plan_max_steps=5)
    flow = _make_flow(research_mode="deep_research", has_verifier=True, plan_steps=6)

    status, reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.VERIFYING
    assert "verifier" in reason


def test_no_plan_routes_to_completed() -> None:
    """Empty plan → COMPLETED regardless of flags."""
    settings = _make_settings(feature_fast_draft_plan=True)
    flow = _make_flow(research_mode="deep_research", has_verifier=True, plan_steps=0)

    status, reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.COMPLETED
    assert "no steps" in reason


def test_no_verifier_routes_to_executing() -> None:
    """No verifier + feature off → EXECUTING (unchanged from original behaviour)."""
    settings = _make_settings(feature_fast_draft_plan=False)
    flow = _make_flow(research_mode=None, has_verifier=False, plan_steps=4)

    status, reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.EXECUTING
    assert "no verifier" in reason


def test_draft_exactly_at_max_steps_skips_verification() -> None:
    """Plan step count exactly equal to max_steps → boundary is inclusive → skip."""
    settings = _make_settings(feature_fast_draft_plan=True, fast_draft_plan_max_steps=5)
    flow = _make_flow(research_mode="wide_research", has_verifier=True, plan_steps=5)

    status, reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.EXECUTING
    assert "fast draft" in reason


def test_draft_one_over_max_steps_verifies() -> None:
    """Plan step count exactly one over max_steps → NOT skipped → VERIFYING."""
    settings = _make_settings(feature_fast_draft_plan=True, fast_draft_plan_max_steps=5)
    flow = _make_flow(research_mode="wide_research", has_verifier=True, plan_steps=6)

    status, _reason = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.VERIFYING


@pytest.mark.parametrize("mode", ["deep_research", "wide_research", "simple"])
def test_any_research_mode_triggers_draft(mode: str) -> None:
    """Any non-None research_mode activates the draft path when the flag is on."""
    settings = _make_settings(feature_fast_draft_plan=True, fast_draft_plan_max_steps=5)
    flow = _make_flow(research_mode=mode, has_verifier=True, plan_steps=3)

    status, _ = flow._route_after_planning(use_draft=_use_draft(flow, settings), settings=settings)

    assert status == AgentStatus.EXECUTING
