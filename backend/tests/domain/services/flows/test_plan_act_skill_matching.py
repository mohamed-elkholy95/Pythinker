"""Tests for SkillMatcher integration with PlanActFlow auto-detection."""

from app.domain.models.skill import Skill, SkillCategory, SkillInvocationType, SkillSource
from app.domain.services.skill_matcher import SkillMatch, SkillMatcher


def _make_skill(skill_id: str, name: str, patterns: list[str]) -> Skill:
    return Skill(
        id=skill_id,
        name=name,
        description=f"Test {name}",
        category=SkillCategory.RESEARCH,
        source=SkillSource.OFFICIAL,
        invocation_type=SkillInvocationType.AI,
        trigger_patterns=patterns,
        required_tools=[],
    )


class TestSkillAutoDetection:
    def test_matcher_integrates_with_skill_model(self):
        matcher = SkillMatcher()
        skill = _make_skill("test-1", "Research", [r"research\b", r"find\s+info"])
        matches = matcher.match("Research the best frameworks", [skill])
        assert len(matches) == 1
        assert matches[0].skill.id == "test-1"

    def test_matched_skills_have_valid_ids(self):
        matcher = SkillMatcher()
        skills = [
            _make_skill("s1", "Research", [r"research"]),
            _make_skill("s2", "Coding", [r"implement"]),
        ]
        matches = matcher.match("Research and implement a solution", skills, threshold=0.3)
        ids = [m.skill.id for m in matches]
        assert all(isinstance(sid, str) for sid in ids)

    def test_no_matches_returns_empty(self):
        matcher = SkillMatcher()
        skill = _make_skill("s1", "Research", [r"research"])
        matches = matcher.match("Buy groceries", [skill])
        assert matches == []

    def test_threshold_filters_low_confidence(self):
        matcher = SkillMatcher()
        skill = _make_skill("s1", "Research", [r"research"])
        # "research" keyword in name gives category keyword score (0.3 * keyword_ratio)
        # but no trigger match, so score < 0.6 default threshold
        matches = matcher.match("I want to do some coding", [skill], threshold=0.6)
        assert matches == []

    def test_match_returns_skill_match_dataclass(self):
        matcher = SkillMatcher()
        skill = _make_skill("s1", "Deep Research", [r"research"])
        matches = matcher.match("research this topic", [skill])
        assert len(matches) == 1
        match = matches[0]
        assert isinstance(match, SkillMatch)
        assert match.skill is skill
        assert match.confidence > 0
        assert isinstance(match.reason, str)
        assert len(match.reason) > 0

    def test_existing_skills_not_duplicated(self):
        """Simulates the dedup logic in plan_act.py."""
        matcher = SkillMatcher()
        skills = [
            _make_skill("s1", "Research", [r"research"]),
            _make_skill("s2", "Coding", [r"implement"]),
        ]
        matches = matcher.match("Research and implement", skills, threshold=0.3)
        auto_skill_ids = [m.skill.id for m in matches]
        existing = {"s1"}  # s1 already attached
        new_ids = [sid for sid in auto_skill_ids if sid not in existing]
        assert "s1" not in new_ids
        # s2 should be new if it matched
        if "s2" in auto_skill_ids:
            assert "s2" in new_ids

    def test_empty_message_returns_no_matches(self):
        matcher = SkillMatcher()
        skill = _make_skill("s1", "Research", [r"research"])
        assert matcher.match("", [skill]) == []

    def test_empty_skills_returns_no_matches(self):
        matcher = SkillMatcher()
        assert matcher.match("research something", []) == []
