"""Tests for wall-clock pressure in BaseAgent.execute().

These tests verify that graduated wall-clock pressure (ADVISORY/URGENT/CRITICAL)
correctly blocks read-only tools and requests graceful completion when the step
time budget is being exhausted.
"""

import itertools
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import MessageEvent
from app.domain.services.agents.base import BaseAgent


@pytest.fixture
def _patch_settings(monkeypatch: pytest.MonkeyPatch):
    """Patch get_settings and get_feature_flags to avoid MagicMock comparison issues.

    MagicMock auto-creates attributes that break numeric comparisons (e.g. ``value > 0``).
    We patch get_feature_flags separately to return safe defaults, and use a controlled
    MagicMock for settings with only the needed numeric attributes.
    """
    mock_settings = MagicMock()
    mock_settings.max_step_wall_clock_seconds = 100.0
    mock_settings.max_session_wall_clock_seconds = 3600
    # Numeric attrs accessed by base.py that participate in comparisons
    mock_settings.hallucination_escalation_min_samples = 10
    mock_settings.hallucination_escalation_threshold = 0.15
    mock_settings.context_compression_trigger_pct = 0.80
    # Feature flags accessed as settings.feature_xxx in get_feature_flags()
    for attr in [
        "feature_tree_of_thoughts", "feature_self_consistency",
        "feature_plan_validation_v2", "feature_reflection_advanced",
        "feature_context_optimization", "feature_tool_tracing",
        "feature_reward_hacking_detection", "feature_failure_prediction",
        "feature_circuit_breaker_adaptive", "feature_workflow_checkpointing",
        "feature_hitl_enabled", "feature_taskgroup_enabled",
        "feature_sse_v2", "feature_structured_outputs",
        "feature_parallel_memory", "feature_enhanced_research",
        "feature_phased_research", "feature_shadow_mode",
        "feature_hallucination_prevention", "feature_hallucination_validation",
        "feature_hallucination_learning", "feature_hallucination_preemptive",
        "feature_hallucination_collaborative", "feature_hallucination_metacognitive",
        "feature_hallucination_escalation_enabled",
        "feature_runtime_clarification_gate", "feature_runtime_dangling_recovery",
        "feature_runtime_quality_gates", "feature_runtime_insight_promotion",
        "feature_runtime_capability_manifest", "feature_runtime_skill_discovery",
        "feature_runtime_research_trace", "feature_runtime_delegate_tool",
        "feature_runtime_channel_overlay",
    ]:
        setattr(mock_settings, attr, False)

    monkeypatch.setattr("app.core.config.get_settings", lambda: mock_settings)
    return mock_settings


@pytest.mark.asyncio
async def test_wall_clock_warning_skips_current_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
    _patch_settings,
) -> None:
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )

    llm = MagicMock()
    llm.model_name = "gpt-4"

    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})

    tool = MagicMock()
    tool.name = "test_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name == "file_read")
    tool.invoke_function = AsyncMock(return_value=MagicMock(success=True, message="ok", data={}))

    agent = BaseAgent(
        agent_id="agent-wall-clock",
        agent_repository=repo,
        llm=llm,
        json_parser=parser,
        tools=[tool],
    )

    # First model turn asks for a tool call; second turn is the final answer.
    agent.ask = AsyncMock(
        return_value={
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "file_read", "arguments": "{}"},
                }
            ]
        }
    )
    agent.ask_with_messages = AsyncMock(return_value={"content": "wrapped up"})
    agent._add_to_memory = AsyncMock()
    agent._cancel_token.check_cancelled = AsyncMock()

    # Start at t=0, then first loop check sees t=76 => 76% of 100s wall limit.
    # 76% triggers URGENT (>=75%) which blocks read-only tools and requests graceful completion.
    monotonic_values = itertools.chain([0.0, 76.0], itertools.repeat(76.0))
    monkeypatch.setattr("app.domain.services.agents.base.time.monotonic", lambda: next(monotonic_values))

    events = [event async for event in agent.execute("do work")]

    # Pending tool call is skipped when wall-clock threshold is reached.
    tool.invoke_function.assert_not_awaited()
    assert agent._add_to_memory.await_count >= 1
    warning_messages = agent._add_to_memory.await_args.args[0]
    assert warning_messages[0]["role"] == "user"
    assert "STEP TIME URGENT" in warning_messages[0]["content"]

    # The cycle should request completion guidance instead of executing tools.
    ask_payload = agent.ask_with_messages.await_args.args[0]
    assert any(
        msg.get("role") == "system" and "Approaching execution limit" in msg.get("content", "") for msg in ask_payload
    )

    final_messages = [e for e in events if isinstance(e, MessageEvent)]
    assert len(final_messages) == 1
    assert final_messages[0].message == "wrapped up"


@pytest.mark.asyncio
async def test_wall_clock_fallback_message_is_structured_json(
    monkeypatch: pytest.MonkeyPatch,
    _patch_settings,
) -> None:
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )

    llm = MagicMock()
    llm.model_name = "gpt-4"

    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})

    tool = MagicMock()
    tool.name = "test_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name == "file_read")
    tool.invoke_function = AsyncMock(return_value=MagicMock(success=True, message="ok", data={}))

    agent = BaseAgent(
        agent_id="agent-wall-clock-json-fallback",
        agent_repository=repo,
        llm=llm,
        json_parser=parser,
        tools=[tool],
    )
    agent.ask = AsyncMock(
        return_value={
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "file_read", "arguments": "{}"},
                }
            ]
        }
    )
    agent.ask_with_messages = AsyncMock(return_value={"content": None})
    agent._add_to_memory = AsyncMock()
    agent._cancel_token.check_cancelled = AsyncMock()

    # 76% triggers URGENT (>=75%) which blocks tools and requests graceful completion.
    monotonic_values = itertools.chain([0.0, 76.0], itertools.repeat(76.0))
    monkeypatch.setattr("app.domain.services.agents.base.time.monotonic", lambda: next(monotonic_values))

    events = [event async for event in agent.execute("do work")]
    final_messages = [event for event in events if isinstance(event, MessageEvent)]
    assert len(final_messages) == 1

    payload = json.loads(final_messages[0].message)
    assert payload["success"] is False
    assert payload["result"] is None
    assert "error" in payload
