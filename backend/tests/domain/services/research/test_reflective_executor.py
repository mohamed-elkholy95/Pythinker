"""Tests for reflective executor."""

from unittest.mock import AsyncMock

import pytest

from app.domain.models.research_phase import ResearchPhase
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.reflective_executor import ReflectiveExecutor, ToolCall


@pytest.mark.asyncio
async def test_execute_with_reflection_parses_llm_output():
    execute_tool = AsyncMock(return_value=ToolResult.ok(message="Search succeeded"))
    llm = AsyncMock()
    llm.ask = AsyncMock(
        return_value={"content": "LEARNED: Found reliable sources for the topic\nNEXT: Compare source consistency"}
    )

    executor = ReflectiveExecutor(execute_tool=execute_tool, llm=llm)
    result = await executor.execute_with_reflection(
        ToolCall(tool_name="search", parameters={"query": "python"}),
        phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
    )

    assert result.action_result is not None
    assert result.action_result.success is True
    assert result.learned == "Found reliable sources for the topic"
    assert result.next_step == "Compare source consistency"
    assert result.phase == ResearchPhase.PHASE_1_FUNDAMENTALS


@pytest.mark.asyncio
async def test_execute_with_reflection_falls_back_when_llm_unavailable():
    execute_tool = AsyncMock(return_value=ToolResult.error(message="rate limit"))
    executor = ReflectiveExecutor(execute_tool=execute_tool, llm=None)

    result = await executor.execute_with_reflection(ToolCall(tool_name="search"))

    assert result.learned == "rate limit"
    assert result.next_step == "Refine the query and run another search."


def test_parse_reflection_accepts_plain_text_fallback():
    learned, next_step = ReflectiveExecutor.parse_reflection("Single line reflection")

    assert learned == "Single line reflection"
    assert next_step is None
