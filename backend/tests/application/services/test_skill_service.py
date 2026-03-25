"""Unit tests for SkillService application service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.skill_service import SkillService
from app.domain.models.skill import Skill, SkillCategory, UserSkillConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    skill_id: str,
    required_tools: list[str] | None = None,
    optional_tools: list[str] | None = None,
    system_prompt_addition: str | None = None,
) -> MagicMock:
    """Return a MagicMock shaped like a Skill domain object."""
    skill = MagicMock(spec=Skill)
    skill.id = skill_id
    skill.required_tools = required_tools or []
    skill.optional_tools = optional_tools or []
    skill.system_prompt_addition = system_prompt_addition
    return skill


def _make_repo() -> MagicMock:
    """Return a MagicMock SkillRepository with all async methods as AsyncMock."""
    repo = MagicMock()
    repo.get_all = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_category = AsyncMock(return_value=[])
    repo.get_by_ids = AsyncMock(return_value=[])
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.upsert = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    repo.get_by_owner = AsyncMock(return_value=[])
    repo.get_public_skills = AsyncMock(return_value=[])
    return repo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo() -> MagicMock:
    return _make_repo()


@pytest.fixture
def service(repo: MagicMock) -> SkillService:
    return SkillService(skill_repo=repo)


# ---------------------------------------------------------------------------
# get_available_skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_available_skills_delegates_to_repo(service: SkillService, repo: MagicMock) -> None:
    skill = _make_skill("research")
    repo.get_all.return_value = [skill]

    result = await service.get_available_skills()

    repo.get_all.assert_awaited_once()
    assert result == [skill]


@pytest.mark.asyncio
async def test_get_available_skills_returns_empty_list_when_none(service: SkillService, repo: MagicMock) -> None:
    repo.get_all.return_value = []
    result = await service.get_available_skills()
    assert result == []


# ---------------------------------------------------------------------------
# get_skill_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skill_by_id_found(service: SkillService, repo: MagicMock) -> None:
    skill = _make_skill("coding")
    repo.get_by_id.return_value = skill

    result = await service.get_skill_by_id("coding")

    repo.get_by_id.assert_awaited_once_with("coding")
    assert result is skill


@pytest.mark.asyncio
async def test_get_skill_by_id_not_found_returns_none(service: SkillService, repo: MagicMock) -> None:
    repo.get_by_id.return_value = None
    result = await service.get_skill_by_id("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# get_skills_by_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skills_by_ids_empty_list_returns_empty_without_repo_call(
    service: SkillService, repo: MagicMock
) -> None:
    result = await service.get_skills_by_ids([])

    assert result == []
    repo.get_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_skills_by_ids_delegates_to_repo(service: SkillService, repo: MagicMock) -> None:
    skills = [_make_skill("a"), _make_skill("b")]
    repo.get_by_ids.return_value = skills

    result = await service.get_skills_by_ids(["a", "b"])

    repo.get_by_ids.assert_awaited_once_with(["a", "b"])
    assert result == skills


@pytest.mark.asyncio
async def test_get_skills_by_ids_single_id(service: SkillService, repo: MagicMock) -> None:
    skill = _make_skill("single")
    repo.get_by_ids.return_value = [skill]

    result = await service.get_skills_by_ids(["single"])

    assert result == [skill]


# ---------------------------------------------------------------------------
# get_tools_for_skill_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tools_for_skill_ids_empty_returns_empty_set(service: SkillService, repo: MagicMock) -> None:
    result = await service.get_tools_for_skill_ids([])

    assert result == set()
    repo.get_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_tools_for_skill_ids_aggregates_tools(service: SkillService, repo: MagicMock) -> None:
    skill_a = _make_skill("a", required_tools=["browser"], optional_tools=["search"])
    skill_b = _make_skill("b", required_tools=["terminal"], optional_tools=[])
    repo.get_by_ids.return_value = [skill_a, skill_b]

    result = await service.get_tools_for_skill_ids(["a", "b"])

    assert result == {"browser", "search", "terminal"}


@pytest.mark.asyncio
async def test_get_tools_for_skill_ids_deduplicates_shared_tools(service: SkillService, repo: MagicMock) -> None:
    skill_a = _make_skill("a", required_tools=["browser"])
    skill_b = _make_skill("b", required_tools=["browser"])
    repo.get_by_ids.return_value = [skill_a, skill_b]

    result = await service.get_tools_for_skill_ids(["a", "b"])

    assert result == {"browser"}


def test_get_skill_tools_collects_required_and_optional(service: SkillService) -> None:
    skill = _make_skill("s", required_tools=["terminal", "file"], optional_tools=["search"])

    result = service.get_skill_tools([skill])

    assert result == {"terminal", "file", "search"}


def test_get_skill_tools_empty_list_returns_empty_set(service: SkillService) -> None:
    assert service.get_skill_tools([]) == set()


def test_get_skill_tools_merges_across_multiple_skills(service: SkillService) -> None:
    skill_a = _make_skill("a", required_tools=["x"], optional_tools=["y"])
    skill_b = _make_skill("b", required_tools=["z"], optional_tools=["x"])

    result = service.get_skill_tools([skill_a, skill_b])

    assert result == {"x", "y", "z"}


def test_get_skill_tools_skill_with_no_tools(service: SkillService) -> None:
    skill = _make_skill("empty")
    assert service.get_skill_tools([skill]) == set()


def test_get_skill_prompt_additions_filters_none(service: SkillService) -> None:
    skills = [
        _make_skill("a", system_prompt_addition="Be concise."),
        _make_skill("b", system_prompt_addition=None),
        _make_skill("c", system_prompt_addition="Focus on data."),
    ]

    result = service.get_skill_prompt_additions(skills)

    assert result == ["Be concise.", "Focus on data."]


def test_get_skill_prompt_additions_filters_empty_string(service: SkillService) -> None:
    skills = [
        _make_skill("a", system_prompt_addition=""),
        _make_skill("b", system_prompt_addition="Valid prompt."),
    ]

    result = service.get_skill_prompt_additions(skills)

    assert result == ["Valid prompt."]


def test_get_skill_prompt_additions_all_none_returns_empty(service: SkillService) -> None:
    skills = [_make_skill("a", system_prompt_addition=None)]
    assert service.get_skill_prompt_additions(skills) == []


def test_get_skill_prompt_additions_empty_skills_returns_empty(service: SkillService) -> None:
    assert service.get_skill_prompt_additions([]) == []


def test_get_skill_prompt_additions_all_valid(service: SkillService) -> None:
    skills = [
        _make_skill("a", system_prompt_addition="Prompt A."),
        _make_skill("b", system_prompt_addition="Prompt B."),
    ]
    result = service.get_skill_prompt_additions(skills)
    assert result == ["Prompt A.", "Prompt B."]


def test_build_user_skill_configs_marks_enabled_correctly(service: SkillService) -> None:
    skill_a = _make_skill("skill-a")
    skill_b = _make_skill("skill-b")

    configs = service.build_user_skill_configs(
        skills=[skill_a, skill_b],
        enabled_skill_ids=["skill-a"],
        user_configs={},
    )

    assert len(configs) == 2
    enabled_map = {c.skill_id: c.enabled for c in configs}
    assert enabled_map["skill-a"] is True
    assert enabled_map["skill-b"] is False


def test_build_user_skill_configs_marks_disabled_correctly(service: SkillService) -> None:
    skill_a = _make_skill("skill-a")
    skill_b = _make_skill("skill-b")

    configs = service.build_user_skill_configs(
        skills=[skill_a, skill_b],
        enabled_skill_ids=[],
        user_configs={},
    )

    assert all(not c.enabled for c in configs)


def test_build_user_skill_configs_all_enabled(service: SkillService) -> None:
    skills = [_make_skill("x"), _make_skill("y")]

    configs = service.build_user_skill_configs(
        skills=skills,
        enabled_skill_ids=["x", "y"],
        user_configs={},
    )

    assert all(c.enabled for c in configs)


def test_build_user_skill_configs_applies_user_configs(service: SkillService) -> None:
    skill = _make_skill("configurable")

    configs = service.build_user_skill_configs(
        skills=[skill],
        enabled_skill_ids=["configurable"],
        user_configs={"configurable": {"depth": "deep", "lang": "en"}},
    )

    assert configs[0].config == {"depth": "deep", "lang": "en"}


def test_build_user_skill_configs_defaults_config_when_missing(service: SkillService) -> None:
    skill = _make_skill("no-config")

    configs = service.build_user_skill_configs(
        skills=[skill],
        enabled_skill_ids=[],
        user_configs={},
    )

    assert configs[0].config == {}


def test_build_user_skill_configs_assigns_order_by_position(service: SkillService) -> None:
    skills = [_make_skill("first"), _make_skill("second"), _make_skill("third")]

    configs = service.build_user_skill_configs(
        skills=skills,
        enabled_skill_ids=[],
        user_configs={},
    )

    assert [c.order for c in configs] == [0, 1, 2]


def test_build_user_skill_configs_empty_skills_returns_empty(service: SkillService) -> None:
    configs = service.build_user_skill_configs(skills=[], enabled_skill_ids=[], user_configs={})
    assert configs == []


def test_build_user_skill_configs_returns_user_skill_config_instances(service: SkillService) -> None:
    skill = _make_skill("s")

    configs = service.build_user_skill_configs(
        skills=[skill],
        enabled_skill_ids=["s"],
        user_configs={},
    )

    assert all(isinstance(c, UserSkillConfig) for c in configs)


# ---------------------------------------------------------------------------
# generate_skill_draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_skill_draft_returns_instructions_from_llm(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": "## Do this workflow\n1. Step one."})

    result = await service.generate_skill_draft(
        name="research-skill",
        description="Research topics online.",
        required_tools=["browser"],
        optional_tools=["search"],
        llm=llm,
    )

    assert result["instructions"] == "## Do this workflow\n1. Step one."


@pytest.mark.asyncio
async def test_generate_skill_draft_falls_back_to_empty_on_llm_error(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(side_effect=RuntimeError("API unavailable"))

    result = await service.generate_skill_draft(
        name="coding-skill",
        description="Write Python code.",
        required_tools=["terminal"],
        optional_tools=[],
        llm=llm,
    )

    assert result["instructions"] == ""


@pytest.mark.asyncio
async def test_generate_skill_draft_always_includes_resource_plan(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": "Instructions."})

    result = await service.generate_skill_draft(
        name="s", description="desc.", required_tools=[], optional_tools=[], llm=llm
    )

    assert "resource_plan" in result
    assert result["resource_plan"] == {"references": [], "scripts": [], "templates": []}


@pytest.mark.asyncio
async def test_generate_skill_draft_expands_short_description(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": "Body."})

    result = await service.generate_skill_draft(
        name="my-skill",
        description="Short desc.",
        required_tools=[],
        optional_tools=[],
        llm=llm,
    )

    assert "my skill" in result["description_suggestion"]
    assert result["description_suggestion"].startswith("Short desc.")


@pytest.mark.asyncio
async def test_generate_skill_draft_keeps_long_description_unchanged(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": "Body."})
    long_desc = "A" * 81

    result = await service.generate_skill_draft(
        name="verbose-skill",
        description=long_desc,
        required_tools=[],
        optional_tools=[],
        llm=llm,
    )

    assert result["description_suggestion"] == long_desc


@pytest.mark.asyncio
async def test_generate_skill_draft_passes_tools_to_llm(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": "Body."})

    await service.generate_skill_draft(
        name="s",
        description="desc.",
        required_tools=["browser", "search"],
        optional_tools=["terminal"],
        llm=llm,
    )

    call_args = llm.ask.call_args[0][0]
    user_message = next(m["content"] for m in call_args if m["role"] == "user")
    assert "browser" in user_message
    assert "search" in user_message
    assert "terminal" in user_message


@pytest.mark.asyncio
async def test_generate_skill_draft_no_tools_skips_tools_section(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": "Body."})

    await service.generate_skill_draft(
        name="s",
        description="desc.",
        required_tools=[],
        optional_tools=[],
        llm=llm,
    )

    call_args = llm.ask.call_args[0][0]
    user_message = next(m["content"] for m in call_args if m["role"] == "user")
    assert "Available tools:" not in user_message


@pytest.mark.asyncio
async def test_generate_skill_draft_strips_whitespace_from_llm_response(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": "  \n  Body with spaces.  \n  "})

    result = await service.generate_skill_draft(
        name="s", description="d.", required_tools=[], optional_tools=[], llm=llm
    )

    assert result["instructions"] == "Body with spaces."


@pytest.mark.asyncio
async def test_generate_skill_draft_handles_none_content_from_llm(service: SkillService) -> None:
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": None})

    result = await service.generate_skill_draft(
        name="s", description="d.", required_tools=[], optional_tools=[], llm=llm
    )

    assert result["instructions"] == ""


# ---------------------------------------------------------------------------
# seed_official_skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_official_skills_upserts_each_skill(service: SkillService, repo: MagicMock) -> None:
    skill_a = _make_skill("skill-a")
    skill_b = _make_skill("skill-b")
    skill_c = _make_skill("skill-c")
    repo.upsert.return_value = MagicMock()

    count = await service.seed_official_skills([skill_a, skill_b, skill_c])

    assert count == 3
    assert repo.upsert.await_count == 3


@pytest.mark.asyncio
async def test_seed_official_skills_returns_zero_for_empty_list(service: SkillService, repo: MagicMock) -> None:
    count = await service.seed_official_skills([])
    assert count == 0
    repo.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_official_skills_calls_upsert_with_each_skill(service: SkillService, repo: MagicMock) -> None:
    skill = _make_skill("single-skill")
    repo.upsert.return_value = skill

    await service.seed_official_skills([skill])

    repo.upsert.assert_awaited_once_with(skill)


@pytest.mark.asyncio
async def test_seed_official_skills_returns_correct_count_for_one(service: SkillService, repo: MagicMock) -> None:
    repo.upsert.return_value = MagicMock()
    count = await service.seed_official_skills([_make_skill("only-one")])
    assert count == 1


# ---------------------------------------------------------------------------
# Delegation tests (upsert, delete, create, update, etc.)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_delegates_to_repo(service: SkillService, repo: MagicMock) -> None:
    skill = _make_skill("new")
    repo.create.return_value = skill

    result = await service.create_skill(skill)

    repo.create.assert_awaited_once_with(skill)
    assert result is skill


@pytest.mark.asyncio
async def test_delete_skill_delegates_to_repo(service: SkillService, repo: MagicMock) -> None:
    repo.delete.return_value = True
    result = await service.delete_skill("to-delete")
    repo.delete.assert_awaited_once_with("to-delete")
    assert result is True


@pytest.mark.asyncio
async def test_get_skills_by_category_delegates_to_repo(service: SkillService, repo: MagicMock) -> None:
    skills = [_make_skill("research-skill")]
    repo.get_by_category.return_value = skills

    result = await service.get_skills_by_category(SkillCategory.RESEARCH)

    repo.get_by_category.assert_awaited_once_with(SkillCategory.RESEARCH)
    assert result == skills


@pytest.mark.asyncio
async def test_get_skills_by_owner_delegates_to_repo(service: SkillService, repo: MagicMock) -> None:
    skills = [_make_skill("owner-skill")]
    repo.get_by_owner.return_value = skills

    result = await service.get_skills_by_owner("user-123")

    repo.get_by_owner.assert_awaited_once_with("user-123")
    assert result == skills


@pytest.mark.asyncio
async def test_get_public_skills_delegates_to_repo(service: SkillService, repo: MagicMock) -> None:
    skills = [_make_skill("public")]
    repo.get_public_skills.return_value = skills

    result = await service.get_public_skills()

    repo.get_public_skills.assert_awaited_once()
    assert result == skills
