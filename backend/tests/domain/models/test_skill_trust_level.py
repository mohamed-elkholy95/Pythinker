from app.domain.models.skill import InstructionTrustLevel, Skill, SkillCategory, SkillSource


def test_instruction_trust_level_enum_values():
    assert InstructionTrustLevel.SYSTEM_AUTHORED == "system_authored"
    assert InstructionTrustLevel.USER_AUTHORED == "user_authored"


def test_skill_defaults_to_user_authored():
    skill = Skill(
        id="test",
        name="Test",
        description="Test skill",
        category=SkillCategory.CUSTOM,
        source=SkillSource.CUSTOM,
    )
    assert skill.instruction_trust_level == InstructionTrustLevel.USER_AUTHORED


def test_official_seed_can_set_system_authored():
    skill = Skill(
        id="research",
        name="Research",
        description="Research skill",
        category=SkillCategory.RESEARCH,
        source=SkillSource.OFFICIAL,
        instruction_trust_level=InstructionTrustLevel.SYSTEM_AUTHORED,
    )
    assert skill.instruction_trust_level == InstructionTrustLevel.SYSTEM_AUTHORED


def test_publishing_does_not_upgrade_trust():
    """Trust level stays USER_AUTHORED even when a custom skill is published to community."""
    skill = Skill(
        id="my-skill",
        name="My Skill",
        description="User skill",
        category=SkillCategory.CUSTOM,
        source=SkillSource.CUSTOM,
        instruction_trust_level=InstructionTrustLevel.USER_AUTHORED,
    )
    # Simulate publishing: change source to COMMUNITY and mark public
    skill.source = SkillSource.COMMUNITY
    skill.is_public = True
    assert skill.instruction_trust_level == InstructionTrustLevel.USER_AUTHORED
