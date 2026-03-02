"""Tests for SpawnTool — background subtask spawning with concurrency limits."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.services.tools.spawn_tool import SpawnTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeSubagentManager:
    """In-memory fake satisfying SubagentManagerProtocol."""

    def __init__(self, running_count: int = 0) -> None:
        self._running_count = running_count
        self.spawn = AsyncMock(return_value="Subagent [my-task] started (id: abc123).")

    def get_running_count(self) -> int:
        return self._running_count

    def set_running_count(self, n: int) -> None:
        self._running_count = n


@pytest.fixture
def manager() -> FakeSubagentManager:
    return FakeSubagentManager(running_count=0)


@pytest.fixture
def spawn_tool(manager: FakeSubagentManager) -> SpawnTool:
    return SpawnTool(subagent_manager=manager, max_concurrent=3)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_returns_confirmation(spawn_tool: SpawnTool, manager: FakeSubagentManager) -> None:
    """Spawning a valid task returns a successful ToolResult with the confirmation."""
    result = await spawn_tool.spawn_background_task(task="Research Python 3.13 changes")

    assert result.success is True
    assert "abc123" in (result.message or "")
    manager.spawn.assert_awaited_once_with(task="Research Python 3.13 changes", label=None)


@pytest.mark.asyncio
async def test_spawn_with_label(spawn_tool: SpawnTool, manager: FakeSubagentManager) -> None:
    """Label is forwarded to the manager."""
    await spawn_tool.spawn_background_task(task="Look up pricing", label="pricing-check")

    manager.spawn.assert_awaited_once_with(task="Look up pricing", label="pricing-check")


@pytest.mark.asyncio
async def test_spawn_returns_running_count_in_data(spawn_tool: SpawnTool) -> None:
    """Data payload includes running_count and max_concurrent."""
    result = await spawn_tool.spawn_background_task(task="Do something useful")

    assert result.success is True
    assert result.data is not None
    assert result.data["running_count"] == 1
    assert result.data["max_concurrent"] == 3


@pytest.mark.asyncio
async def test_spawn_strips_whitespace(spawn_tool: SpawnTool, manager: FakeSubagentManager) -> None:
    """Leading/trailing whitespace is stripped from task and label."""
    await spawn_tool.spawn_background_task(task="  trim me  ", label="  trimmed  ")

    manager.spawn.assert_awaited_once_with(task="trim me", label="trimmed")


# ---------------------------------------------------------------------------
# Concurrency-limit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_when_at_concurrency_limit(manager: FakeSubagentManager) -> None:
    """When running count equals max_concurrent, spawning is rejected."""
    manager.set_running_count(3)
    tool = SpawnTool(subagent_manager=manager, max_concurrent=3)

    result = await tool.spawn_background_task(task="One too many")

    assert result.success is False
    assert "Concurrency limit reached" in (result.message or "")
    assert "3/3" in (result.message or "")
    manager.spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_when_above_concurrency_limit(manager: FakeSubagentManager) -> None:
    """Edge case: running count exceeds max_concurrent (shouldn't happen, but guard anyway)."""
    manager.set_running_count(5)
    tool = SpawnTool(subagent_manager=manager, max_concurrent=3)

    result = await tool.spawn_background_task(task="Way over limit")

    assert result.success is False
    assert "Concurrency limit reached" in (result.message or "")
    manager.spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_allow_spawn_below_limit(manager: FakeSubagentManager) -> None:
    """When running count is below max_concurrent, spawning succeeds."""
    manager.set_running_count(2)
    tool = SpawnTool(subagent_manager=manager, max_concurrent=3)

    result = await tool.spawn_background_task(task="Still room")

    assert result.success is True
    manager.spawn.assert_awaited_once()


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_task_returns_error(spawn_tool: SpawnTool, manager: FakeSubagentManager) -> None:
    """An empty task description is rejected immediately."""
    result = await spawn_tool.spawn_background_task(task="")

    assert result.success is False
    assert "empty" in (result.message or "").lower()
    manager.spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_whitespace_only_task_returns_error(spawn_tool: SpawnTool, manager: FakeSubagentManager) -> None:
    """A whitespace-only task description is rejected."""
    result = await spawn_tool.spawn_background_task(task="   ")

    assert result.success is False
    assert "empty" in (result.message or "").lower()
    manager.spawn.assert_not_awaited()


# ---------------------------------------------------------------------------
# Error-handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_exception_returns_error(spawn_tool: SpawnTool, manager: FakeSubagentManager) -> None:
    """If the manager raises, the tool returns a ToolResult.error (does not propagate)."""
    manager.spawn.side_effect = RuntimeError("Boom")

    result = await spawn_tool.spawn_background_task(task="Explode")

    assert result.success is False
    assert "Failed to spawn" in (result.message or "")
    assert "Boom" in (result.message or "")


# ---------------------------------------------------------------------------
# Tool schema / registration tests
# ---------------------------------------------------------------------------


def test_get_tools_returns_spawn_schema(spawn_tool: SpawnTool) -> None:
    """BaseTool.get_tools() picks up the @tool-decorated method."""
    schemas = spawn_tool.get_tools()
    assert len(schemas) == 1
    func_def = schemas[0]["function"]
    assert func_def["name"] == "spawn_background_task"
    assert "task" in func_def["parameters"]["properties"]
    assert "label" in func_def["parameters"]["properties"]
    assert func_def["parameters"]["required"] == ["task"]


def test_tool_name(spawn_tool: SpawnTool) -> None:
    """The tool category name is 'spawn'."""
    assert spawn_tool.name == "spawn"
