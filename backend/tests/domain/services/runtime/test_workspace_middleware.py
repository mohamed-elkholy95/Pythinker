"""Tests for the WorkspaceContract and WorkspaceMiddleware."""

from __future__ import annotations

import pytest

from app.domain.services.runtime.middleware import RuntimeContext
from app.domain.services.runtime.workspace_middleware import (
    WorkspaceContract,
    WorkspaceMiddleware,
)


@pytest.mark.asyncio
async def test_before_run_populates_workspace_paths() -> None:
    """WorkspaceMiddleware.before_run sets all 5 expected keys in ctx.workspace."""
    session_id = "abc123"
    middleware = WorkspaceMiddleware(base_dir="/home/ubuntu")
    ctx = RuntimeContext(session_id=session_id, agent_id="agent-1")

    result = await middleware.before_run(ctx)

    root = f"/home/ubuntu/{session_id}"
    assert result.workspace["workspace"] == root
    assert result.workspace["uploads"] == f"{root}/uploads"
    assert result.workspace["outputs"] == f"{root}/outputs"
    assert result.workspace["task_state"] == f"{root}/task_state.md"
    assert result.workspace["scratchpad"] == f"{root}/scratchpad.md"


@pytest.mark.asyncio
async def test_contract_is_serializable() -> None:
    """WorkspaceContract survives a model_dump + model_validate roundtrip."""
    contract = WorkspaceContract(
        session_id="sess-42",
        workspace="/home/ubuntu/sess-42",
        uploads="/home/ubuntu/sess-42/uploads",
        outputs="/home/ubuntu/sess-42/outputs",
    )

    dumped = contract.model_dump()
    restored = WorkspaceContract.model_validate(dumped)

    assert restored.task_state_path == "/home/ubuntu/sess-42/task_state.md"
    assert restored.scratchpad_path == "/home/ubuntu/sess-42/scratchpad.md"
    assert restored.workspace == contract.workspace
    assert restored.uploads == contract.uploads
    assert restored.outputs == contract.outputs


@pytest.mark.asyncio
async def test_contract_prompt_block() -> None:
    """to_prompt_block returns an XML block containing all path values."""
    contract = WorkspaceContract(
        session_id="sess-99",
        workspace="/home/ubuntu/sess-99",
        uploads="/home/ubuntu/sess-99/uploads",
        outputs="/home/ubuntu/sess-99/outputs",
    )

    block = contract.to_prompt_block()

    assert "<workspace_paths>" in block
    assert "</workspace_paths>" in block
    assert f"<workspace>{contract.workspace}</workspace>" in block
    assert f"<uploads>{contract.uploads}</uploads>" in block
    assert f"<outputs>{contract.outputs}</outputs>" in block
    assert f"<task_state>{contract.task_state_path}</task_state>" in block
    assert f"<scratchpad>{contract.scratchpad_path}</scratchpad>" in block


@pytest.mark.asyncio
async def test_metadata_includes_contract() -> None:
    """ctx.metadata contains a WorkspaceContract instance after before_run."""
    middleware = WorkspaceMiddleware(base_dir="/data")
    ctx = RuntimeContext(session_id="session-xyz", agent_id="agent-2")

    result = await middleware.before_run(ctx)

    assert "workspace_contract" in result.metadata
    contract = result.metadata["workspace_contract"]
    assert isinstance(contract, WorkspaceContract)
    assert contract.session_id == "session-xyz"
    assert contract.workspace == "/data/session-xyz"
