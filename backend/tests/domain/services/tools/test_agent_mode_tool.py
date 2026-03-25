"""Tests for AgentModeTool mode switching logic."""

import pytest

from app.domain.services.tools.agent_mode import AgentModeTool


@pytest.fixture()
def tool() -> AgentModeTool:
    return AgentModeTool()


class TestAgentModeTool:
    def test_initial_state(self, tool: AgentModeTool) -> None:
        assert tool.mode_switch_requested is False
        assert tool.task_description is None
        assert tool.name == "agent_mode"

    @pytest.mark.asyncio()
    async def test_agent_start_task(self, tool: AgentModeTool) -> None:
        result = await tool.agent_start_task(task="Research Python 3.12 features")
        assert result.success is True
        assert tool.mode_switch_requested is True
        assert tool.task_description == "Research Python 3.12 features"
        assert "agent" in result.data["mode"]

    @pytest.mark.asyncio()
    async def test_agent_start_task_with_reason(self, tool: AgentModeTool) -> None:
        result = await tool.agent_start_task(task="Write code", reason="Complex task")
        assert result.data["reason"] == "Complex task"

    def test_reset(self, tool: AgentModeTool) -> None:
        tool._mode_switch_requested = True
        tool._task_description = "some task"
        tool.reset()
        assert tool.mode_switch_requested is False
        assert tool.task_description is None
