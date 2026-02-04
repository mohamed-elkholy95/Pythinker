# backend/tests/domain/services/test_context_manager.py
"""Tests for SandboxContextManager service.

Tests the file-system-as-context pattern implementation for externalized memory.
"""

from unittest.mock import AsyncMock

import pytest

from app.domain.services.context_manager import SandboxContextManager


@pytest.fixture
def mock_sandbox():
    sandbox = AsyncMock()
    sandbox.write_file = AsyncMock(return_value=True)
    sandbox.read_file = AsyncMock(return_value="- [ ] Task 1\n- [x] Task 2")
    return sandbox


@pytest.mark.asyncio
async def test_set_goal(mock_sandbox):
    manager = SandboxContextManager(session_id="sess_123", sandbox=mock_sandbox)
    await manager.set_goal("Complete the data analysis")

    mock_sandbox.write_file.assert_called_once()
    call_args = mock_sandbox.write_file.call_args
    assert "goal.md" in call_args[0][0]
    assert "Complete the data analysis" in call_args[0][1]


@pytest.mark.asyncio
async def test_update_todo(mock_sandbox):
    manager = SandboxContextManager(session_id="sess_123", sandbox=mock_sandbox)
    tasks = ["Gather data", "Analyze results", "Generate report"]
    await manager.update_todo(tasks)

    mock_sandbox.write_file.assert_called_once()
    call_args = mock_sandbox.write_file.call_args
    assert "todo.md" in call_args[0][0]


@pytest.mark.asyncio
async def test_get_attention_context(mock_sandbox):
    manager = SandboxContextManager(session_id="sess_123", sandbox=mock_sandbox)
    await manager.set_goal("Test goal")

    context = await manager.get_attention_context()
    assert "Test goal" in context or "goal" in context.lower()
