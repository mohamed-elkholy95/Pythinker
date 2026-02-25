"""Smoke tests for Phase 2: CoordinatorFlow meta-cognition complexity inference.

_analyze_task() now calls meta.assess_capabilities() after keyword/length heuristics
and upgrades to COMPLEX when capability_match_score < 0.6 or can_accomplish is False.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.message import Message
from app.domain.services.orchestration.coordinator_flow import CoordinatorFlow, TaskComplexity


def _make_coordinator(session_id: str = "test-s") -> CoordinatorFlow:
    """Create a minimal CoordinatorFlow for testing _analyze_task."""
    flow = CoordinatorFlow.__new__(CoordinatorFlow)
    flow._session_id = session_id
    flow._agent_id = "agent-test"
    flow._mode = MagicMock()
    flow._swarm = None
    flow._plan_act_flow = None
    return flow


def _msg(text: str) -> Message:
    return Message(message=text, session_id="s1", role="user")


@pytest.mark.asyncio
async def test_simple_message_returns_simple():
    """Short, plain messages without complexity indicators → SIMPLE."""
    flow = _make_coordinator()
    # Patch meta-cognition to succeed with high match score (no upgrade)
    capability = MagicMock()
    capability.can_accomplish = True
    capability.capability_match_score = 0.9
    capability.missing_capabilities = []

    with patch(
        "app.domain.services.agents.reasoning.meta_cognition.get_meta_cognition",
        return_value=MagicMock(assess_capabilities=MagicMock(return_value=capability)),
    ):
        result = await flow._analyze_task(_msg("Hello, what time is it?"))

    assert result == TaskComplexity.SIMPLE


@pytest.mark.asyncio
async def test_complex_keyword_returns_complex():
    """Messages containing COMPLEX indicators are classified immediately."""
    flow = _make_coordinator()
    result = await flow._analyze_task(_msg("Please compare and contrast these two papers"))
    assert result == TaskComplexity.COMPLEX


@pytest.mark.asyncio
async def test_moderate_keyword_returns_moderate():
    """Messages containing MODERATE indicators are classified correctly."""
    flow = _make_coordinator()
    result = await flow._analyze_task(_msg("Research the latest Python 3.12 features"))
    assert result == TaskComplexity.MODERATE


@pytest.mark.asyncio
async def test_meta_cognition_upgrades_to_complex_when_cannot_accomplish():
    """Meta-cognition can_accomplish=False causes upgrade to COMPLEX."""
    flow = _make_coordinator()

    capability = MagicMock()
    capability.can_accomplish = False
    capability.capability_match_score = 0.3
    capability.missing_capabilities = ["web_browsing"]

    with patch(
        "app.domain.services.agents.reasoning.meta_cognition.get_meta_cognition",
        return_value=MagicMock(assess_capabilities=MagicMock(return_value=capability)),
    ):
        result = await flow._analyze_task(_msg("Short simple message"))

    assert result == TaskComplexity.COMPLEX


@pytest.mark.asyncio
async def test_meta_cognition_upgrades_to_moderate_on_low_match_score():
    """Low capability_match_score (< 0.6) upgrades to MODERATE."""
    flow = _make_coordinator()

    capability = MagicMock()
    capability.can_accomplish = True
    capability.capability_match_score = 0.4
    capability.missing_capabilities = []

    with patch(
        "app.domain.services.agents.reasoning.meta_cognition.get_meta_cognition",
        return_value=MagicMock(assess_capabilities=MagicMock(return_value=capability)),
    ):
        result = await flow._analyze_task(_msg("Short simple message"))

    assert result == TaskComplexity.MODERATE


@pytest.mark.asyncio
async def test_meta_cognition_failure_is_non_fatal():
    """If meta-cognition raises, _analyze_task() falls back to SIMPLE without crashing."""
    flow = _make_coordinator()

    with patch(
        "app.domain.services.agents.reasoning.meta_cognition.get_meta_cognition",
        return_value=MagicMock(assess_capabilities=MagicMock(side_effect=RuntimeError("meta unavailable"))),
    ):
        result = await flow._analyze_task(_msg("A short message"))

    assert result == TaskComplexity.SIMPLE


@pytest.mark.asyncio
async def test_long_message_returns_at_least_moderate():
    """Messages > 500 characters are MODERATE or higher."""
    flow = _make_coordinator()

    long_message = "Please do the following task: " + ("detailed step. " * 40)
    assert len(long_message) > 500

    capability = MagicMock()
    capability.can_accomplish = True
    capability.capability_match_score = 0.9

    with patch(
        "app.domain.services.agents.reasoning.meta_cognition.get_meta_cognition",
        return_value=MagicMock(assess_capabilities=MagicMock(return_value=capability)),
    ):
        result = await flow._analyze_task(_msg(long_message))

    assert result in (TaskComplexity.MODERATE, TaskComplexity.COMPLEX)
