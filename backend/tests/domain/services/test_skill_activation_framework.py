from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.services.skill_activation_framework import (
    SkillActivationFramework,
    SkillActivationSource,
)


@pytest.mark.asyncio
async def test_chat_selection_only_activation():
    framework = SkillActivationFramework()

    result = await framework.resolve(
        message="Please help me with architecture",
        selected_skills=["writing-plans", "brainstorming"],
        auto_trigger_enabled=False,
    )

    assert sorted(result.skill_ids) == ["brainstorming", "writing-plans"]
    assert result.command_skill_id is None
    assert result.auto_trigger_enabled is False
    assert result.auto_triggered_skill_ids == []
    assert result.activation_sources["brainstorming"] == [SkillActivationSource.CHAT_SELECTION.value]
    assert result.activation_sources["writing-plans"] == [SkillActivationSource.CHAT_SELECTION.value]


@pytest.mark.asyncio
async def test_command_activation():
    framework = SkillActivationFramework()

    result = await framework.resolve(
        message="/brainstorm shape this feature",
        selected_skills=[],
        auto_trigger_enabled=False,
    )

    assert result.command_skill_id == "brainstorming"
    assert result.skill_ids == ["brainstorming"]
    assert result.activation_sources["brainstorming"] == [SkillActivationSource.COMMAND.value]


@pytest.mark.asyncio
async def test_command_and_chat_selection_merge_sources():
    framework = SkillActivationFramework()

    result = await framework.resolve(
        message="/brainstorm shape this feature",
        selected_skills=["brainstorming"],
        auto_trigger_enabled=False,
    )

    assert result.command_skill_id == "brainstorming"
    assert result.skill_ids == ["brainstorming"]
    assert result.activation_sources["brainstorming"] == sorted(
        [SkillActivationSource.CHAT_SELECTION.value, SkillActivationSource.COMMAND.value]
    )


@pytest.mark.asyncio
async def test_embedded_skill_creator_fallback():
    framework = SkillActivationFramework()

    result = await framework.resolve(
        message="Build with Pythinker /skill-creator and scaffold it",
        selected_skills=[],
        auto_trigger_enabled=False,
    )

    assert result.command_skill_id is None
    assert result.skill_ids == ["skill-creator"]
    assert result.activation_sources["skill-creator"] == [SkillActivationSource.EMBEDDED_COMMAND.value]


@pytest.mark.asyncio
async def test_auto_trigger_disabled_skips_trigger_matcher():
    framework = SkillActivationFramework()

    with patch("app.domain.services.skill_trigger_matcher.get_skill_trigger_matcher") as mock_get_matcher:
        result = await framework.resolve(
            message="research AI safety",
            selected_skills=[],
            auto_trigger_enabled=False,
        )

    assert result.skill_ids == []
    mock_get_matcher.assert_not_called()


@pytest.mark.asyncio
async def test_auto_trigger_enabled_adds_matches():
    framework = SkillActivationFramework()
    fake_matcher = AsyncMock()
    fake_matcher.find_matching_skills = AsyncMock(
        return_value=[SimpleNamespace(skill_id="research"), SimpleNamespace(skill_id="citation")]
    )

    with patch(
        "app.domain.services.skill_trigger_matcher.get_skill_trigger_matcher",
        new=AsyncMock(return_value=fake_matcher),
    ):
        result = await framework.resolve(
            message="research AI safety and cite sources",
            selected_skills=["research"],
            auto_trigger_enabled=True,
        )

    # "research" already selected by chat, so only "citation" is newly auto-triggered.
    assert sorted(result.skill_ids) == ["citation", "research"]
    assert result.auto_triggered_skill_ids == ["citation"]
    assert result.activation_sources["citation"] == [SkillActivationSource.AUTO_TRIGGER.value]
    assert result.activation_sources["research"] == [SkillActivationSource.CHAT_SELECTION.value]
