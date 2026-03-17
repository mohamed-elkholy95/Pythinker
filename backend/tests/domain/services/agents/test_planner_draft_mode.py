"""Tests for PlannerAgent draft=True mode (Task 2.2).

Verifies that:
- create_plan() accepts draft=True without error
- draft=False does not change model behaviour
- The method signature includes the draft parameter
"""

import inspect
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.agent_response import PlanResponse, StepResponse
from app.domain.models.message import Message
from app.domain.services.agents.planner import PlannerAgent

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_plan_response() -> PlanResponse:
    """Minimal valid PlanResponse for LLM mock return."""
    return PlanResponse(
        goal="Test goal",
        title="Test Plan",
        language="en",
        steps=[StepResponse(id="1", description="Do the thing")],
    )


def _make_planner(fast_model: str = "") -> PlannerAgent:
    """Build a minimal PlannerAgent with all external deps mocked."""
    llm = MagicMock()
    llm.model_name = "test-model"
    llm.ask = AsyncMock(return_value={"content": "{}"})
    # ask_structured returns a PlanResponse so _create_plan_inner succeeds
    llm.ask_structured = AsyncMock(return_value=_make_plan_response())

    agent_repo = MagicMock()
    json_parser = MagicMock()

    return PlannerAgent(
        agent_id="test-agent",
        agent_repository=agent_repo,
        llm=llm,
        tools=[],
        json_parser=json_parser,
    )


def _make_message(text: str = "Write a hello world script") -> Message:
    return Message(message=text)


async def _collect(gen: AsyncGenerator) -> list:
    """Drain an async generator into a list."""
    return [item async for item in gen]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_draft_mode_exists():
    """create_plan() signature must include a 'draft' keyword parameter."""
    sig = inspect.signature(PlannerAgent.create_plan)
    assert "draft" in sig.parameters, "create_plan() is missing the 'draft' parameter"
    param = sig.parameters["draft"]
    assert param.default is False, "draft should default to False"


@pytest.mark.asyncio
async def test_draft_plan_parameter_accepted():
    """create_plan(draft=True) is accepted without raising TypeError."""
    planner = _make_planner()

    with (
        patch("app.domain.services.agents.planner.PlannerAgent._add_to_memory", new_callable=AsyncMock),
        patch("app.domain.services.agents.planner.PlannerAgent._ensure_within_token_limit", new_callable=AsyncMock),
        patch("app.core.config.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.fast_model = "fast-model-x"
        mock_settings.return_value = settings

        events = await _collect(planner.create_plan(_make_message(), draft=True))

    # We expect at least one event (RECEIVED) to have been emitted
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_non_draft_uses_default_model():
    """draft=False must not inject a model override into _ask_structured_tiered."""
    planner = _make_planner()
    captured_kwargs: dict = {}

    async def fake_ask_structured_tiered(**kwargs):
        captured_kwargs.update(kwargs)
        return _make_plan_response()

    planner._ask_structured_tiered = fake_ask_structured_tiered  # type: ignore[method-assign]

    with (
        patch("app.domain.services.agents.planner.PlannerAgent._add_to_memory", new_callable=AsyncMock),
        patch("app.domain.services.agents.planner.PlannerAgent._ensure_within_token_limit", new_callable=AsyncMock),
        patch("app.domain.services.agents.planner.PlannerAgent._stream_thinking") as mock_think,
        patch("app.core.config.get_settings") as mock_settings,
    ):
        # _stream_thinking is an async generator; mock it to yield nothing
        async def _empty_gen(*_a, **_kw):
            return
            yield

        mock_think.side_effect = _empty_gen
        settings = MagicMock()
        settings.fast_model = "fast-model-x"
        mock_settings.return_value = settings

        await _collect(planner.create_plan(_make_message(), draft=False))

    # With draft=False the model kwarg should be None (no override)
    assert captured_kwargs.get("model") is None, (
        f"draft=False should not set model override, got model={captured_kwargs.get('model')!r}"
    )
