from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base import BaseAgent


def _build_base_agent(*, json_parser: object, llm: object, tool: object) -> BaseAgent:
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )
    repo.save_memory = AsyncMock()

    return BaseAgent(
        agent_id="agent-tool-args-test",
        agent_repository=repo,
        llm=llm,
        json_parser=json_parser,  # type: ignore[arg-type]
        tools=[tool],  # type: ignore[list-item]
    )


@pytest.mark.asyncio
async def test_execute_parses_tool_arguments_without_llm_json_parser() -> None:
    """Tool arguments must be parsed from strict JSON, not LLMJsonParser repair heuristics."""
    llm = MagicMock()
    llm.model_name = "gpt-4"

    parser = AsyncMock()
    parser.parse = AsyncMock(side_effect=AssertionError("json_parser.parse must not be used for tool args"))

    tool = MagicMock()
    tool.name = "test_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name == "file_read")
    tool.invoke_function = AsyncMock(return_value=ToolResult.ok(message="ok", data={"content": "hello"}))

    agent = _build_base_agent(json_parser=parser, llm=llm, tool=tool)
    agent._cancel_token.check_cancelled = AsyncMock()
    agent._add_to_memory = AsyncMock()
    agent.ask = AsyncMock(
        return_value={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "file_read",
                        "arguments": '{"path": "/workspace/report.md"}',
                    },
                }
            ],
        }
    )
    agent.ask_with_messages = AsyncMock(return_value={"role": "assistant", "content": "done"})

    [event async for event in agent.execute("read report")]

    tool.invoke_function.assert_awaited_once_with("file_read", path="/workspace/report.md")
    parser.parse.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_with_messages_retries_on_malformed_tool_args() -> None:
    """Malformed tool args should be treated as truncation and trigger a retry prompt."""
    llm = MagicMock()
    llm.model_name = "gpt-4"
    llm.ask = AsyncMock(
        side_effect=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_bad",
                        "type": "function",
                        "function": {
                            "name": "file_read",
                            "arguments": '{"path": "/workspace/report.md"',
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "wrapped up",
            },
        ]
    )

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
                    "description": "Read file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name == "file_read")
    tool.invoke_function = AsyncMock(return_value=ToolResult.ok(message="ok"))

    agent = _build_base_agent(json_parser=parser, llm=llm, tool=tool)
    agent._cancel_token.check_cancelled = AsyncMock()
    agent._add_to_memory = AsyncMock(wraps=agent._add_to_memory)

    response = await agent.ask_with_messages([{"role": "user", "content": "read report"}])

    assert response["content"] == "wrapped up"
    assert llm.ask.await_count == 2
