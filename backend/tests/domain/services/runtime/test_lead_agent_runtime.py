"""Tests for LeadAgentRuntime facade and build_runtime_pipeline factory."""

from __future__ import annotations

import pytest

from app.domain.services.runtime.clarification_middleware import ClarificationMiddleware
from app.domain.services.runtime.dangling_tool_middleware import DanglingToolCallMiddleware
from app.domain.services.runtime.lead_agent_runtime import (
    LeadAgentRuntime,
    build_runtime_pipeline,
)
from app.domain.services.runtime.workspace_middleware import WorkspaceMiddleware


@pytest.mark.asyncio
async def test_build_pipeline_returns_ordered_middlewares() -> None:
    """Factory produces a pipeline with at least 3 middlewares in the correct order.

    The prescribed order is:
        WorkspaceMiddleware → DanglingToolCallMiddleware → ClarificationMiddleware
    """
    pipeline = build_runtime_pipeline(
        session_id="sess-order",
        agent_id="agent-order",
        workspace_base="/home/ubuntu",
    )

    # Access internal middleware list via the private attribute (white-box check).
    middlewares = pipeline._middlewares

    assert len(middlewares) >= 3, "Pipeline must contain at least 3 middlewares"

    # Find positional indices for the three required types.
    type_index: dict[type, int] = {}
    for idx, mw in enumerate(middlewares):
        type_index[type(mw)] = idx

    assert WorkspaceMiddleware in type_index, "WorkspaceMiddleware must be present"
    assert DanglingToolCallMiddleware in type_index, "DanglingToolCallMiddleware must be present"
    assert ClarificationMiddleware in type_index, "ClarificationMiddleware must be present"

    ws_idx = type_index[WorkspaceMiddleware]
    dangling_idx = type_index[DanglingToolCallMiddleware]
    clarif_idx = type_index[ClarificationMiddleware]

    assert ws_idx < dangling_idx, "WorkspaceMiddleware must come before DanglingToolCallMiddleware"
    assert dangling_idx < clarif_idx, "DanglingToolCallMiddleware must come before ClarificationMiddleware"


@pytest.mark.asyncio
async def test_runtime_init_populates_workspace() -> None:
    """initialize() runs BEFORE_RUN: ctx.workspace has 'workspace' key and
    task_state ends with 'task_state.md'.
    """
    runtime = LeadAgentRuntime(
        session_id="sess-workspace",
        agent_id="agent-ws",
        workspace_base="/home/ubuntu",
    )

    ctx = await runtime.initialize()

    assert "workspace" in ctx.workspace, "ctx.workspace must contain 'workspace' key"
    assert ctx.workspace["task_state"].endswith("task_state.md"), "task_state path must end with 'task_state.md'"
    # Sanity-check the stored context is the same object returned.
    assert runtime.context is ctx


@pytest.mark.asyncio
async def test_runtime_before_step_sanitizes_history() -> None:
    """before_step() runs DanglingToolCallMiddleware: a dangling tool call in
    message_history receives a synthetic placeholder response.
    """
    runtime = LeadAgentRuntime(
        session_id="sess-dangling",
        agent_id="agent-dangling",
        workspace_base="/home/ubuntu",
    )
    ctx = await runtime.initialize()

    # Inject a dangling tool call (assistant message with no matching tool response).
    dangling_call_id = "call_abc123"
    ctx.metadata["message_history"] = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": dangling_call_id,
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        }
    ]

    ctx = await runtime.before_step()

    sanitized: list[dict] = ctx.metadata["message_history"]
    tool_responses = [m for m in sanitized if m.get("role") == "tool"]

    assert len(tool_responses) == 1, "Exactly one placeholder tool response should be injected"
    assert tool_responses[0]["tool_call_id"] == dangling_call_id
    assert "Interrupted" in tool_responses[0]["content"]


@pytest.mark.asyncio
async def test_runtime_exposes_workspace_contract() -> None:
    """initialize() stores a WorkspaceContract in ctx.metadata with the correct
    session_id and a functional to_prompt_block() method.
    """
    session_id = "sess-contract"
    runtime = LeadAgentRuntime(
        session_id=session_id,
        agent_id="agent-contract",
        workspace_base="/tmp/test_runtime",
    )

    ctx = await runtime.initialize()

    assert "workspace_contract" in ctx.metadata, "ctx.metadata must contain 'workspace_contract' key"
    contract = ctx.metadata["workspace_contract"]

    assert contract.session_id == session_id, "WorkspaceContract must carry the runtime's session_id"

    prompt_block = contract.to_prompt_block()
    assert "<workspace_paths>" in prompt_block, "to_prompt_block() must return an XML block with <workspace_paths>"
    assert session_id in prompt_block, "to_prompt_block() output must include the session_id in derived paths"
