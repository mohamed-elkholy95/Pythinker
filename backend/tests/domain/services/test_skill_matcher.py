from app.domain.models.skill import Skill, SkillCategory, SkillInvocationType, SkillSource
from app.domain.services.skill_matcher import SkillMatcher


def _make_skill(
    skill_id: str,
    name: str,
    category: SkillCategory,
    trigger_patterns: list[str] | None = None,
    required_tools: list[str] | None = None,
) -> Skill:
    return Skill(
        id=skill_id,
        name=name,
        description=f"Test {name} skill",
        category=category,
        source=SkillSource.OFFICIAL,
        invocation_type=SkillInvocationType.AI,
        trigger_patterns=trigger_patterns or [],
        required_tools=required_tools or [],
    )


RESEARCH_SKILL = _make_skill(
    "research-v1",
    "Research",
    SkillCategory.RESEARCH,
    trigger_patterns=[r"research\b", r"find\s+information", r"look\s+up", r"search\s+for"],
    required_tools=["search", "browser_navigate"],
)

CODING_SKILL = _make_skill(
    "coding-v1",
    "Coding",
    SkillCategory.CODING,
    trigger_patterns=[r"write\s+(a\s+)?code", r"implement", r"build\s+a", r"create\s+a\s+(script|program)"],
    required_tools=["shell_exec", "code_execute", "file_write"],
)

BROWSER_SKILL = _make_skill(
    "browser-v1",
    "Browser Automation",
    SkillCategory.BROWSER,
    trigger_patterns=[r"browse\s+to", r"open\s+(the\s+)?website", r"navigate\s+to", r"go\s+to\s+https?://"],
    required_tools=["browser_navigate", "browser_click"],
)

ALL_SKILLS = [RESEARCH_SKILL, CODING_SKILL, BROWSER_SKILL]


class TestSkillMatcher:
    def setup_method(self):
        self.matcher = SkillMatcher()

    def test_match_research_query(self):
        matches = self.matcher.match("Research the latest AI trends", ALL_SKILLS)
        assert len(matches) >= 1
        assert matches[0].skill.id == "research-v1"
        assert matches[0].confidence >= 0.6

    def test_match_coding_query(self):
        matches = self.matcher.match("Implement a REST API endpoint", ALL_SKILLS)
        assert len(matches) >= 1
        assert any(m.skill.id == "coding-v1" for m in matches)

    def test_match_browser_query(self):
        matches = self.matcher.match("Navigate to https://example.com", ALL_SKILLS)
        assert len(matches) >= 1
        assert any(m.skill.id == "browser-v1" for m in matches)

    def test_no_match_irrelevant_query(self):
        matches = self.matcher.match("Hello, how are you?", ALL_SKILLS, threshold=0.6)
        assert len(matches) == 0

    def test_threshold_filtering(self):
        matches_low = self.matcher.match("Research AI", ALL_SKILLS, threshold=0.3)
        matches_high = self.matcher.match("Research AI", ALL_SKILLS, threshold=0.9)
        assert len(matches_low) >= len(matches_high)

    def test_matches_sorted_by_confidence(self):
        matches = self.matcher.match("Research and implement a web scraper", ALL_SKILLS, threshold=0.1)
        if len(matches) >= 2:
            assert matches[0].confidence >= matches[1].confidence

    def test_empty_skills_list(self):
        matches = self.matcher.match("Research AI", [])
        assert matches == []

    def test_empty_message(self):
        matches = self.matcher.match("", ALL_SKILLS)
        assert matches == []

    def test_skill_match_has_reason(self):
        matches = self.matcher.match("Research the latest AI trends", ALL_SKILLS)
        assert len(matches) >= 1
        assert matches[0].reason  # non-empty reason string
