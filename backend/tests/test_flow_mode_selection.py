"""Tests for runtime flow mode selection."""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.config import FlowMode, Settings
from app.domain.models.session import AgentMode
from app.domain.services.agent_task_runner import AgentTaskRunner


def _build_runner(monkeypatch, **kwargs):
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_plan_act_flow",
        lambda self: setattr(self, "_plan_act_flow", MagicMock()),
    )
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_coordinator_flow",
        lambda self: setattr(self, "_coordinator_flow", MagicMock()),
    )
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_discuss_flow",
        lambda self: setattr(self, "_discuss_flow", MagicMock()),
    )

    return AgentTaskRunner(
        session_id="session-1",
        agent_id="agent-1",
        user_id="user-1",
        llm=MagicMock(),
        sandbox=MagicMock(),
        browser=MagicMock(),
        agent_repository=MagicMock(),
        session_repository=MagicMock(),
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=MagicMock(),
        mode=AgentMode.AGENT,
        **kwargs,
    )


def test_resolved_flow_mode_defaults_to_plan_act():
    settings = Settings()
    assert settings.resolved_flow_mode == FlowMode.PLAN_ACT


def test_resolved_flow_mode_supports_coordinator_via_flow_mode():
    settings = Settings(flow_mode=FlowMode.COORDINATOR)
    assert settings.resolved_flow_mode == FlowMode.COORDINATOR


def test_resolved_flow_mode_supports_legacy_enable_coordinator():
    settings = Settings(enable_coordinator=True)
    assert settings.resolved_flow_mode == FlowMode.COORDINATOR


def test_skill_auto_trigger_defaults_to_disabled():
    settings = Settings()
    assert settings.skill_auto_trigger_enabled is False


def test_skill_auto_trigger_can_be_enabled():
    settings = Settings(skill_auto_trigger_enabled=True)
    assert settings.skill_auto_trigger_enabled is True


def test_unsupported_flow_mode_is_rejected():
    with pytest.raises(ValidationError):
        Settings(flow_mode="unsupported_mode")


def test_agent_task_runner_defaults_to_plan_act(monkeypatch):
    runner = _build_runner(monkeypatch)
    assert runner._flow_mode == FlowMode.PLAN_ACT
    assert runner._flow_selection_reason is None


def test_agent_task_runner_supports_coordinator(monkeypatch):
    runner = _build_runner(monkeypatch, flow_mode=FlowMode.COORDINATOR)
    assert runner._flow_mode == FlowMode.COORDINATOR
    assert runner._flow_selection_reason is None


def test_agent_task_runner_marks_legacy_enable_coordinator_reason(monkeypatch):
    runner = _build_runner(monkeypatch, enable_coordinator=True)
    assert runner._flow_mode == FlowMode.COORDINATOR
    assert runner._flow_selection_reason == "legacy_enable_coordinator"
