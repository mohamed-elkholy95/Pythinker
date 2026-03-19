"""Tests for AI-assisted skill draft generation."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_generate_skill_draft_returns_structured_response():
    from app.application.services.skill_service import SkillService

    mock_llm = AsyncMock()
    mock_llm.ask.return_value = {
        "content": "# Blog Writer\n\n## Workflow\n1. Research topic\n2. Write draft\n3. Polish"
    }

    service = SkillService()
    result = await service.generate_skill_draft(
        name="blog-writer",
        description="Write natural blog posts that avoid AI tropes",
        required_tools=["file_write", "info_search_web"],
        optional_tools=[],
        llm=mock_llm,
    )

    assert "instructions" in result
    assert len(result["instructions"]) > 0
    assert "description_suggestion" in result
    assert "resource_plan" in result
    mock_llm.ask.assert_called_once()


@pytest.mark.asyncio
async def test_generate_skill_draft_includes_tools_in_prompt():
    from app.application.services.skill_service import SkillService

    mock_llm = AsyncMock()
    mock_llm.ask.return_value = {"content": "# Test\n\nInstructions here."}

    service = SkillService()
    await service.generate_skill_draft(
        name="test",
        description="A test skill",
        required_tools=["shell_exec", "file_read"],
        optional_tools=["code_execute_python"],
        llm=mock_llm,
    )

    call_args = mock_llm.ask.call_args[0][0]  # first positional arg (messages)
    user_msg = next(m for m in call_args if m["role"] == "user")
    assert "shell_exec" in user_msg["content"]
    assert "file_read" in user_msg["content"]
    assert "code_execute_python" in user_msg["content"]


@pytest.mark.asyncio
async def test_generate_skill_draft_short_description_gets_suggestion():
    from app.application.services.skill_service import SkillService

    mock_llm = AsyncMock()
    mock_llm.ask.return_value = {"content": "# Short\n\nDo things."}

    service = SkillService()
    result = await service.generate_skill_draft(
        name="my-skill",
        description="A short desc",
        required_tools=[],
        optional_tools=[],
        llm=mock_llm,
    )

    # Short descriptions should be expanded
    assert len(result["description_suggestion"]) > len("A short desc")
    assert "my skill" in result["description_suggestion"]


@pytest.mark.asyncio
async def test_generate_skill_draft_long_description_kept_as_is():
    from app.application.services.skill_service import SkillService

    mock_llm = AsyncMock()
    mock_llm.ask.return_value = {"content": "# Long\n\nInstructions."}

    long_desc = "This is a sufficiently long description that exceeds eighty characters and should be kept unchanged by the service"
    service = SkillService()
    result = await service.generate_skill_draft(
        name="my-skill",
        description=long_desc,
        required_tools=[],
        optional_tools=[],
        llm=mock_llm,
    )

    assert result["description_suggestion"] == long_desc


@pytest.mark.asyncio
async def test_generate_skill_draft_resource_plan_structure():
    from app.application.services.skill_service import SkillService

    mock_llm = AsyncMock()
    mock_llm.ask.return_value = {"content": "# Skill\n\nContent."}

    service = SkillService()
    result = await service.generate_skill_draft(
        name="test",
        description="A test skill for checking structure",
        required_tools=[],
        optional_tools=[],
        llm=mock_llm,
    )

    plan = result["resource_plan"]
    assert "references" in plan
    assert "scripts" in plan
    assert "templates" in plan
    assert isinstance(plan["references"], list)
    assert isinstance(plan["scripts"], list)
    assert isinstance(plan["templates"], list)


@pytest.mark.asyncio
async def test_generate_skill_draft_handles_empty_content():
    from app.application.services.skill_service import SkillService

    mock_llm = AsyncMock()
    mock_llm.ask.return_value = {"content": ""}

    service = SkillService()
    result = await service.generate_skill_draft(
        name="empty",
        description="A skill that returns empty content",
        required_tools=[],
        optional_tools=[],
        llm=mock_llm,
    )

    assert result["instructions"] == ""


@pytest.mark.asyncio
async def test_generate_skill_draft_handles_none_content():
    from app.application.services.skill_service import SkillService

    mock_llm = AsyncMock()
    mock_llm.ask.return_value = {"content": None}

    service = SkillService()
    result = await service.generate_skill_draft(
        name="none",
        description="A skill where LLM returns None content",
        required_tools=[],
        optional_tools=[],
        llm=mock_llm,
    )

    assert result["instructions"] == ""
