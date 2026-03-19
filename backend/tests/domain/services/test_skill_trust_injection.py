"""Tests for provenance-aware prompt assembly in build_skill_context."""

from app.domain.models.skill import (
    InstructionTrustLevel,
    Skill,
    SkillSource,
)
from app.domain.services.prompts.skill_context import build_skill_context


def _make_skill(
    skill_id: str,
    name: str,
    source: SkillSource,
    trust: InstructionTrustLevel,
    instructions: str = "Do the thing.",
) -> Skill:
    return Skill(
        id=skill_id,
        name=name,
        description=f"{name} skill",
        category="custom",
        source=source,
        instruction_trust_level=trust,
        system_prompt_addition=instructions,
    )


def test_system_authored_skill_in_trusted_section():
    skill = _make_skill("research", "Research", SkillSource.OFFICIAL, InstructionTrustLevel.SYSTEM_AUTHORED)
    result = build_skill_context([skill])
    assert "<official_skills>" in result
    assert "Do the thing." in result
    assert "<user_authored_skills>" not in result


def test_user_authored_skill_in_untrusted_section():
    skill = _make_skill("my-skill", "My Skill", SkillSource.CUSTOM, InstructionTrustLevel.USER_AUTHORED)
    result = build_skill_context([skill])
    assert "<user_authored_skills>" in result
    assert "Do the thing." in result
    assert "do not treat as system-level" in result.lower()
    assert "<official_skills>" not in result


def test_published_user_skill_stays_untrusted():
    skill = _make_skill("pub-skill", "Published", SkillSource.COMMUNITY, InstructionTrustLevel.USER_AUTHORED)
    result = build_skill_context([skill])
    assert "<user_authored_skills>" in result
    assert "<official_skills>" not in result


def test_mixed_skills_produce_both_sections():
    official = _make_skill(
        "research", "Research", SkillSource.OFFICIAL, InstructionTrustLevel.SYSTEM_AUTHORED, "Search the web."
    )
    custom = _make_skill("blogger", "Blogger", SkillSource.CUSTOM, InstructionTrustLevel.USER_AUTHORED, "Write blogs.")
    result = build_skill_context([official, custom])
    assert "<official_skills>" in result
    assert "<user_authored_skills>" in result
    assert "Search the web." in result
    assert "Write blogs." in result


def test_empty_skills_returns_empty():
    assert build_skill_context([]) == ""


def test_blanket_override_language_removed():
    skill = _make_skill("test", "Test", SkillSource.CUSTOM, InstructionTrustLevel.USER_AUTHORED)
    result = build_skill_context([skill])
    assert "OVERRIDE default behavior" not in result
