"""Tests for ListSkillsTool and ReadSkillTool."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.services.tools.skill_tools import ListSkillsTool, ReadSkillTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_skill_loader(
    skills: list[dict] | None = None,
    skill_content: dict[str, str | None] | None = None,
) -> MagicMock:
    """Create a mock SkillLoaderProtocol.

    Args:
        skills: Return value for list_skills(). Defaults to empty list.
        skill_content: Mapping of skill_name -> content for load_skill().
    """
    loader = MagicMock()
    loader.list_skills.return_value = skills or []
    loader.load_skill.side_effect = lambda name: (skill_content or {}).get(name)
    return loader


SAMPLE_SKILLS = [
    {"name": "research", "path": "/skills/research/SKILL.md", "source": "builtin"},
    {"name": "coding", "path": "/workspace/skills/coding/SKILL.md", "source": "workspace"},
]

SAMPLE_CONTENT = {
    "research": "# Research Skill\n\nDo thorough research using multiple sources.",
    "coding": "# Coding Skill\n\nWrite clean, tested code.",
}


# ---------------------------------------------------------------------------
# ListSkillsTool
# ---------------------------------------------------------------------------


class TestListSkillsTool:
    """Tests for ListSkillsTool."""

    @pytest.mark.asyncio
    async def test_list_skills_with_available_skills(self) -> None:
        """list_skills returns formatted list when skills exist."""
        loader = _make_skill_loader(skills=SAMPLE_SKILLS)
        tool = ListSkillsTool(skill_loader=loader)

        result = await tool.list_skills()

        assert result.success is True
        assert result.data is not None
        assert result.data["skills"] == SAMPLE_SKILLS
        assert "Found 2 available skill(s)" in (result.message or "")
        assert "**research**" in (result.message or "")
        assert "**coding**" in (result.message or "")
        loader.list_skills.assert_called_once_with(filter_unavailable=True)

    @pytest.mark.asyncio
    async def test_list_skills_with_no_skills(self) -> None:
        """list_skills returns informative message when no skills exist."""
        loader = _make_skill_loader(skills=[])
        tool = ListSkillsTool(skill_loader=loader)

        result = await tool.list_skills()

        assert result.success is True
        assert result.data is not None
        assert result.data["skills"] == []
        assert "No skills are currently available" in (result.message or "")

    @pytest.mark.asyncio
    async def test_list_skills_loader_exception(self) -> None:
        """list_skills returns error when loader raises."""
        loader = MagicMock()
        loader.list_skills.side_effect = RuntimeError("disk error")
        tool = ListSkillsTool(skill_loader=loader)

        result = await tool.list_skills()

        assert result.success is False
        assert "Failed to list skills" in (result.message or "")
        assert "disk error" in (result.message or "")


# ---------------------------------------------------------------------------
# ReadSkillTool
# ---------------------------------------------------------------------------


class TestReadSkillTool:
    """Tests for ReadSkillTool."""

    @pytest.mark.asyncio
    async def test_read_skill_valid_name(self) -> None:
        """read_skill returns content for a known skill."""
        loader = _make_skill_loader(skill_content=SAMPLE_CONTENT)
        tool = ReadSkillTool(skill_loader=loader)

        result = await tool.read_skill(skill_name="research")

        assert result.success is True
        assert result.message == SAMPLE_CONTENT["research"]
        assert result.data is not None
        assert result.data["skill_name"] == "research"
        assert result.data["content_length"] == len(SAMPLE_CONTENT["research"])
        loader.load_skill.assert_called_once_with("research")

    @pytest.mark.asyncio
    async def test_read_skill_unknown_name(self) -> None:
        """read_skill returns error with available skills hint for unknown name."""
        loader = _make_skill_loader(
            skills=SAMPLE_SKILLS,
            skill_content={},
        )
        tool = ReadSkillTool(skill_loader=loader)

        result = await tool.read_skill(skill_name="nonexistent")

        assert result.success is False
        assert "not found" in (result.message or "")
        assert "nonexistent" in (result.message or "")
        # Should list available skills as a hint
        assert "research" in (result.message or "")
        assert "coding" in (result.message or "")

    @pytest.mark.asyncio
    async def test_read_skill_empty_name(self) -> None:
        """read_skill returns error for empty skill name."""
        loader = _make_skill_loader()
        tool = ReadSkillTool(skill_loader=loader)

        result = await tool.read_skill(skill_name="")

        assert result.success is False
        assert "required" in (result.message or "").lower()
        # Should not call load_skill at all
        loader.load_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_skill_whitespace_only_name(self) -> None:
        """read_skill returns error for whitespace-only skill name."""
        loader = _make_skill_loader()
        tool = ReadSkillTool(skill_loader=loader)

        result = await tool.read_skill(skill_name="   ")

        assert result.success is False
        assert "required" in (result.message or "").lower()
        loader.load_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_skill_strips_whitespace(self) -> None:
        """read_skill strips leading/trailing whitespace from skill name."""
        loader = _make_skill_loader(skill_content=SAMPLE_CONTENT)
        tool = ReadSkillTool(skill_loader=loader)

        result = await tool.read_skill(skill_name="  research  ")

        assert result.success is True
        loader.load_skill.assert_called_once_with("research")

    @pytest.mark.asyncio
    async def test_read_skill_loader_exception(self) -> None:
        """read_skill returns error when loader raises."""
        loader = MagicMock()
        loader.load_skill.side_effect = OSError("permission denied")
        tool = ReadSkillTool(skill_loader=loader)

        result = await tool.read_skill(skill_name="research")

        assert result.success is False
        assert "Failed to load skill" in (result.message or "")
        assert "permission denied" in (result.message or "")

    @pytest.mark.asyncio
    async def test_read_skill_unknown_name_no_available_skills(self) -> None:
        """read_skill gracefully handles when listing available skills also fails."""
        loader = MagicMock()
        loader.load_skill.return_value = None
        loader.list_skills.side_effect = RuntimeError("cannot list")
        tool = ReadSkillTool(skill_loader=loader)

        result = await tool.read_skill(skill_name="ghost")

        assert result.success is False
        assert "not found" in (result.message or "")
        # Should not crash even though list_skills failed
        assert "ghost" in (result.message or "")
