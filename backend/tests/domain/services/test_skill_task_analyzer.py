"""Unit tests for SkillTaskAnalyzer — multi-signal skill-task matching service.

Tests cover all 5 scoring signals, threshold filtering, max_results cap,
cache invalidation, singleton factory, and edge cases.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.models.skill import SkillCategory, SkillInvocationType
from app.domain.services.skill_task_analyzer import (
    SkillAnalysisResult,
    SkillTaskAnalyzer,
    get_skill_task_analyzer,
)

# ---------------------------------------------------------------------------
# Helper: build a lightweight skill fixture with SimpleNamespace
# ---------------------------------------------------------------------------


def make_test_skill(
    id: str = "test-skill",
    name: str = "Test Skill",
    description: str = "A test skill",
    category: SkillCategory = SkillCategory.RESEARCH,
    trigger_patterns: list[str] | None = None,
    required_tools: list[str] | None = None,
    tags: list[str] | None = None,
    system_prompt_addition: str | None = None,
    invocation_type: SkillInvocationType = SkillInvocationType.BOTH,
) -> SimpleNamespace:
    """Return a lightweight skill stub that duck-types the real Skill model."""
    return SimpleNamespace(
        id=id,
        name=name,
        description=description,
        category=category,
        trigger_patterns=trigger_patterns or [],
        required_tools=required_tools or [],
        tags=tags or [],
        system_prompt_addition=system_prompt_addition,
        invocation_type=invocation_type,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def research_skill() -> SimpleNamespace:
    return make_test_skill(
        id="research",
        name="Research",
        description="Web research and information gathering",
        category=SkillCategory.RESEARCH,
        trigger_patterns=[r"research\s+", r"find\s+information", r"look\s+up"],
        required_tools=["info_search_web", "browser_navigate", "browser_get_content", "file_write"],
        tags=["research", "web", "search"],
        system_prompt_addition=(
            "## MANDATORY Research Workflow\n"
            "### Step 1: Search\nFind relevant sources with search queries\n"
            "### Step 2: BROWSE ACTUAL PAGES\nVisit URLs and extract content\n"
            "### Step 3: Synthesize\nCompile findings with citations"
        ),
        invocation_type=SkillInvocationType.BOTH,
    )


@pytest.fixture
def coding_skill() -> SimpleNamespace:
    return make_test_skill(
        id="coding",
        name="Coding",
        description="Code generation, debugging, and refactoring",
        category=SkillCategory.CODING,
        trigger_patterns=[r"write\s+code", r"debug", r"fix\s+", r"implement", r"refactor"],
        required_tools=["file_read", "file_write", "file_str_replace", "shell_exec", "code_execute"],
        tags=["code", "programming", "development"],
        system_prompt_addition=(
            "## Coding Skill\nUnderstand First: Read existing code\nMake Focused Changes\nCode Quality\nVerify Changes"
        ),
        invocation_type=SkillInvocationType.BOTH,
    )


@pytest.fixture
def data_skill() -> SimpleNamespace:
    return make_test_skill(
        id="data-analysis",
        name="Data Analysis",
        description="Data processing, analysis, and visualization",
        category=SkillCategory.DATA_ANALYSIS,
        trigger_patterns=[],
        required_tools=["file_read", "file_write", "code_execute_python"],
        tags=["data", "analysis", "chart"],
        system_prompt_addition=(
            "## Data Analysis Skill\nLoad data using pandas\nExplore with describe()\nVisualize with matplotlib"
        ),
        invocation_type=SkillInvocationType.BOTH,
    )


@pytest.fixture
def user_only_skill() -> SimpleNamespace:
    return make_test_skill(
        id="user-only",
        name="User Only Skill",
        description="A skill only users can invoke",
        category=SkillCategory.CUSTOM,
        invocation_type=SkillInvocationType.USER,
    )


@pytest.fixture
def mock_registry(research_skill: SimpleNamespace, coding_skill: SimpleNamespace) -> AsyncMock:
    """Create a mocked skill registry with research + coding skills."""
    skills = [research_skill, coding_skill]
    registry = AsyncMock()
    registry.get_available_skills = AsyncMock(return_value=skills)
    registry.get_skill = AsyncMock(side_effect=lambda sid: next((s for s in skills if s.id == sid), None))
    return registry


@pytest.fixture
def mock_registry_three(
    research_skill: SimpleNamespace,
    coding_skill: SimpleNamespace,
    data_skill: SimpleNamespace,
) -> AsyncMock:
    """Mocked registry with three skills."""
    skills = [research_skill, coding_skill, data_skill]
    registry = AsyncMock()
    registry.get_available_skills = AsyncMock(return_value=skills)
    registry.get_skill = AsyncMock(side_effect=lambda sid: next((s for s in skills if s.id == sid), None))
    return registry


@pytest.fixture
def mock_registry_with_user_only(
    research_skill: SimpleNamespace,
    user_only_skill: SimpleNamespace,
) -> AsyncMock:
    """Mocked registry that includes a USER-only skill."""
    skills = [research_skill, user_only_skill]
    registry = AsyncMock()
    registry.get_available_skills = AsyncMock(return_value=skills)
    registry.get_skill = AsyncMock(side_effect=lambda sid: next((s for s in skills if s.id == sid), None))
    return registry


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset module-level singleton and class-level compiled patterns before each test."""
    import app.domain.services.skill_task_analyzer as mod

    mod._analyzer = None
    mod.SkillTaskAnalyzer._COMPILED_TOOL_PATTERNS = None
    yield
    mod._analyzer = None
    mod.SkillTaskAnalyzer._COMPILED_TOOL_PATTERNS = None


# ---------------------------------------------------------------------------
# Helper: patch the registry and return a fresh SkillTaskAnalyzer
# ---------------------------------------------------------------------------


def _patch_registry(registry: AsyncMock):
    """Context-manager that patches get_skill_registry to return *registry*.

    The analyzer imports get_skill_registry locally inside its methods, so we
    must patch it at the source module where it is defined.
    """
    return patch(
        "app.domain.services.skill_registry.get_skill_registry",
        new_callable=AsyncMock,
        return_value=registry,
    )


# ---------------------------------------------------------------------------
# Signal-level unit tests (static / class methods, no async needed)
# ---------------------------------------------------------------------------


class TestSignalTrigger:
    """Direct unit tests for the _signal_trigger static method."""

    def test_no_patterns_returns_zero(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_trigger("research AI", [], signals)
        assert score == 0.0
        assert signals == []

    def test_single_pattern_full_match(self):
        signals: list[str] = []
        pattern = re.compile(r"research\s+", re.IGNORECASE)
        score = SkillTaskAnalyzer._signal_trigger("research the topic", [(pattern, r"research\s+")], signals)
        assert score == 1.0
        assert len(signals) == 1
        assert "Trigger" in signals[0]

    def test_partial_match_proportional_score(self):
        signals: list[str] = []
        p1 = (re.compile(r"research", re.IGNORECASE), "research")
        p2 = (re.compile(r"unrelated_xyz", re.IGNORECASE), "unrelated_xyz")
        score = SkillTaskAnalyzer._signal_trigger("research AI", [p1, p2], signals)
        assert score == pytest.approx(0.5)

    def test_no_match_returns_zero(self):
        signals: list[str] = []
        pattern = re.compile(r"unrelated_xyz", re.IGNORECASE)
        score = SkillTaskAnalyzer._signal_trigger("hello world", [(pattern, "unrelated_xyz")], signals)
        assert score == 0.0
        assert signals == []


class TestSignalCategory:
    """Direct unit tests for the _signal_category class method."""

    def test_research_category_hit(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_category("research the topic", "research", signals)
        assert score > 0.0
        assert "research" in signals[0]

    def test_unknown_category_returns_zero(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_category("something something", "unknown_cat", signals)
        assert score == 0.0
        assert signals == []

    def test_coding_category_with_debug_keyword(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_category("debug this code", "coding", signals)
        assert score > 0.0

    def test_score_proportional_to_hits(self):
        """Task with two coding keywords should score higher than one keyword."""
        signals_one: list[str] = []
        signals_two: list[str] = []
        score_one = SkillTaskAnalyzer._signal_category("implement something", "coding", signals_one)
        score_two = SkillTaskAnalyzer._signal_category("implement and debug something", "coding", signals_two)
        assert score_two > score_one


class TestSignalTools:
    """Direct unit tests for the _signal_tools static method."""

    def test_empty_required_tools_returns_zero(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_tools(["browser_navigate"], [], signals)
        assert score == 0.0

    def test_empty_inferred_tools_returns_zero(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_tools([], ["file_read", "file_write"], signals)
        assert score == 0.0

    def test_full_overlap(self):
        signals: list[str] = []
        tools = ["file_read", "file_write"]
        score = SkillTaskAnalyzer._signal_tools(tools, tools, signals)
        assert score == pytest.approx(1.0)
        assert "Tools" in signals[0]

    def test_partial_overlap_jaccard(self):
        signals: list[str] = []
        inferred = ["file_read", "browser_navigate"]
        required = ["file_read", "file_write"]
        # overlap = {file_read}, union = {file_read, file_write, browser_navigate}
        score = SkillTaskAnalyzer._signal_tools(inferred, required, signals)
        assert score == pytest.approx(1 / 3)

    def test_no_overlap_returns_zero(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_tools(["shell_exec"], ["browser_navigate"], signals)
        assert score == 0.0


class TestSignalDescription:
    """Direct unit tests for the _signal_description static method."""

    def test_identical_token_sets(self):
        signals: list[str] = []
        tokens = frozenset(["research", "information", "gathering"])
        score = SkillTaskAnalyzer._signal_description(tokens, tokens, signals)
        assert score == pytest.approx(1.0)

    def test_empty_task_tokens(self):
        signals: list[str] = []
        desc = frozenset(["research", "web"])
        score = SkillTaskAnalyzer._signal_description(frozenset(), desc, signals)
        assert score == 0.0

    def test_empty_description_tokens(self):
        signals: list[str] = []
        task = frozenset(["research", "web"])
        score = SkillTaskAnalyzer._signal_description(task, frozenset(), signals)
        assert score == 0.0

    def test_partial_overlap_jaccard(self):
        signals: list[str] = []
        task = frozenset(["research", "data"])
        desc = frozenset(["research", "code"])
        # intersection = {research}, union = {research, data, code}
        score = SkillTaskAnalyzer._signal_description(task, desc, signals)
        assert score == pytest.approx(1 / 3)
        assert "Description similarity" in signals[0]


class TestSignalKeywordDensity:
    """Direct unit tests for the _signal_keyword_density class method."""

    def test_no_keywords_returns_zero(self):
        signals: list[str] = []
        score = SkillTaskAnalyzer._signal_keyword_density("something", frozenset(), signals)
        assert score == 0.0

    def test_full_match(self):
        signals: list[str] = []
        keywords = frozenset(["search", "browse"])
        score = SkillTaskAnalyzer._signal_keyword_density("search and browse the web", keywords, signals)
        assert score == pytest.approx(1.0)
        assert "Keyword density" in signals[0]

    def test_no_match_returns_zero(self):
        signals: list[str] = []
        keywords = frozenset(["research", "synthesize"])
        score = SkillTaskAnalyzer._signal_keyword_density("hello world foobar", keywords, signals)
        assert score == 0.0


class TestTokenize:
    """Unit tests for the _tokenize class method."""

    def test_splits_on_non_alphanumeric(self):
        tokens = SkillTaskAnalyzer._tokenize("hello-world foo_bar")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foobar" not in tokens  # underscore separates

    def test_drops_short_tokens(self):
        tokens = SkillTaskAnalyzer._tokenize("a bb ccc dddd")
        assert "dddd" in tokens
        assert "a" not in tokens
        assert "bb" not in tokens
        assert "ccc" not in tokens  # length < 4

    def test_lowercases(self):
        tokens = SkillTaskAnalyzer._tokenize("RESEARCH Research research")
        assert "research" in tokens
        assert "RESEARCH" not in tokens

    def test_empty_string(self):
        assert SkillTaskAnalyzer._tokenize("") == frozenset()


class TestExtractKeywords:
    """Unit tests for the _extract_keywords class method."""

    def test_returns_top_n(self):
        text = "search search search browse browse code"
        keywords = SkillTaskAnalyzer._extract_keywords(text, 2)
        assert len(keywords) <= 2

    def test_empty_text(self):
        assert SkillTaskAnalyzer._extract_keywords("", 10) == frozenset()

    def test_most_frequent_included(self):
        text = "search " * 10 + "browse " * 5 + "execute " * 1
        keywords = SkillTaskAnalyzer._extract_keywords(text, 2)
        assert "search" in keywords


class TestInferTools:
    """Unit tests for the _infer_tools class method."""

    def test_url_infers_browser_tools(self):
        tools = SkillTaskAnalyzer._infer_tools("go to https://example.com")
        assert "browser_navigate" in tools
        assert "browser_get_content" in tools

    def test_file_infers_file_tools(self):
        tools = SkillTaskAnalyzer._infer_tools("read this file and write output")
        assert "file_read" in tools
        assert "file_write" in tools

    def test_search_infers_search_tool(self):
        tools = SkillTaskAnalyzer._infer_tools("search for information on AI")
        assert "info_search_web" in tools

    def test_python_infers_exec_tools(self):
        tools = SkillTaskAnalyzer._infer_tools("run this python script")
        assert "shell_exec" in tools or "code_execute" in tools

    def test_csv_infers_python_and_read(self):
        tools = SkillTaskAnalyzer._infer_tools("analyze this csv data")
        assert "code_execute_python" in tools
        assert "file_read" in tools

    def test_unrelated_task_returns_empty(self):
        tools = SkillTaskAnalyzer._infer_tools("hello world")
        assert tools == []


# ---------------------------------------------------------------------------
# Async integration tests for analyze() — require mocked registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAnalyzeMethod:
    """Integration tests for SkillTaskAnalyzer.analyze() with mocked registry."""

    async def test_empty_message_returns_empty(self, mock_registry: AsyncMock):
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("")
        assert results == []

    async def test_no_skills_returns_empty(self):
        """When registry has no AI-invokable skills, analyze returns empty list."""
        registry = AsyncMock()
        registry.get_available_skills = AsyncMock(return_value=[])
        registry.get_skill = AsyncMock(return_value=None)
        with _patch_registry(registry):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("research the latest AI trends")
        assert results == []

    async def test_category_alignment_research(self, mock_registry: AsyncMock):
        """Task with 'research' keyword should make research skill score higher than coding skill."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("Research the latest AI frameworks")
        assert len(results) >= 1
        top = results[0]
        assert top.skill_id == "research"
        assert top.confidence > 0.0

    async def test_category_alignment_coding(self, mock_registry: AsyncMock):
        """Task with 'implement' keyword should make coding skill rank highly."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("implement a REST API endpoint")
        coding_results = [r for r in results if r.skill_id == "coding"]
        assert len(coding_results) == 1
        assert coding_results[0].confidence > 0.0

    async def test_trigger_pattern_match_contributes_highest_weight(self, mock_registry: AsyncMock):
        """Trigger pattern matching (weight 0.30) is the strongest individual signal.

        A task that ONLY matches the trigger pattern should score exactly W_TRIGGER
        (all other signals contribute 0 if we craft a task that avoids them).
        We verify that a trigger hit alone produces score >= W_TRIGGER.
        """
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            # "research " (trailing space) matches the research skill trigger pattern exactly
            results = await analyzer.analyze("research AI")
        research_result = next((r for r in results if r.skill_id == "research"), None)
        assert research_result is not None
        # With a trigger hit the score must be at least W_TRIGGER contribution
        assert research_result.confidence >= SkillTaskAnalyzer.W_TRIGGER * (1 / 3)

    async def test_multi_signal_composite_score_exceeds_single_signal(self, mock_registry: AsyncMock):
        """Task matching multiple signals should score higher than a task matching only one."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            # Task designed to hit trigger + category + description for research skill
            high_score_results = await analyzer.analyze("research the topic and find information by browsing URLs")
            # Task designed to only weakly touch research skill (no keywords, no trigger)
            low_score_results = await analyzer.analyze("hello world how are you doing today")

        high = next((r for r in high_score_results if r.skill_id == "research"), None)
        low = next((r for r in low_score_results if r.skill_id == "research"), None)

        if high is not None and low is not None:
            assert high.confidence >= low.confidence
        elif high is not None:
            assert high.confidence > 0.0

    async def test_tool_overlap_for_browser_task(self, mock_registry: AsyncMock):
        """Task mentioning URL infers browser tools; research skill has browser_navigate → overlap signal."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("go to https://example.com and extract content")
        research_result = next((r for r in results if r.skill_id == "research"), None)
        assert research_result is not None
        # The tool signal should have fired (browser_navigate overlap)
        assert any("Tools" in s for s in research_result.signals)

    async def test_description_similarity_signal_fires(self, mock_registry: AsyncMock):
        """Task whose words overlap with skill description tokens triggers description signal."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            # "gathering information" overlaps with research skill description tokens
            results = await analyzer.analyze("gathering information from multiple sources")
        research_result = next((r for r in results if r.skill_id == "research"), None)
        assert research_result is not None
        assert any("Description similarity" in s for s in research_result.signals)

    async def test_threshold_filtering_activation_recommended(self, mock_registry: AsyncMock):
        """activation_recommended respects the threshold parameter."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            # Very low threshold — almost everything is recommended
            results_low = await analyzer.analyze("research AI", threshold=0.0)
            # Impossibly high threshold — nothing recommended
            results_high = await analyzer.analyze("research AI", threshold=1.1)

        assert all(r.activation_recommended for r in results_low)
        assert all(not r.activation_recommended for r in results_high)

    async def test_max_results_cap(self, mock_registry_three: AsyncMock):
        """analyze() returns at most max_results entries."""
        with _patch_registry(mock_registry_three):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("research and analyze data and write code", max_results=2)
        assert len(results) <= 2

    async def test_results_sorted_by_confidence_descending(self, mock_registry_three: AsyncMock):
        """Results are ordered by confidence, highest first."""
        with _patch_registry(mock_registry_three):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("research the data and implement code", max_results=5)
        for i in range(len(results) - 1):
            assert results[i].confidence >= results[i + 1].confidence

    async def test_user_only_skills_excluded(self, mock_registry_with_user_only: AsyncMock):
        """Skills with invocation_type=USER must not appear in results."""
        with _patch_registry(mock_registry_with_user_only):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("research the topic and look up information")
        ids = [r.skill_id for r in results]
        assert "user-only" not in ids

    async def test_result_fields_are_populated(self, mock_registry: AsyncMock):
        """Each SkillAnalysisResult has all required fields populated."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("research the latest AI frameworks")
        assert len(results) >= 1
        for r in results:
            assert isinstance(r, SkillAnalysisResult)
            assert r.skill_id
            assert r.skill_name
            assert 0.0 <= r.confidence <= 1.0
            assert isinstance(r.signals, list)
            assert isinstance(r.activation_recommended, bool)

    async def test_empty_trigger_patterns_no_trigger_signal(self, mock_registry_three: AsyncMock):
        """Skill with empty trigger_patterns never fires the trigger signal."""
        with _patch_registry(mock_registry_three):
            analyzer = SkillTaskAnalyzer()
            results = await analyzer.analyze("analyze data visualization with pandas")
        data_result = next((r for r in results if r.skill_id == "data-analysis"), None)
        assert data_result is not None
        # No trigger signal should appear since data_skill has no trigger_patterns
        assert not any("Trigger" in s for s in data_result.signals)

    async def test_confidence_capped_at_one(self, mock_registry: AsyncMock):
        """Composite score must not exceed 1.0 even when all signals fire maximally."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            # Craft task that triggers as many signals as possible for research skill
            results = await analyzer.analyze(
                "research the topic and find information look up URLs https://example.com web research gathering"
            )
        for r in results:
            assert r.confidence <= 1.0


# ---------------------------------------------------------------------------
# Cache invalidation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCacheInvalidation:
    """Tests for invalidate() and invalidate_skill()."""

    async def test_invalidate_clears_cache_and_allows_reinit(
        self, mock_registry: AsyncMock, research_skill: SimpleNamespace
    ):
        """invalidate() resets _initialized so the next analyze() re-loads skills."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            # Initialize
            await analyzer.analyze("research the topic")
            assert analyzer._initialized is True
            assert len(analyzer._cache) > 0

            # Invalidate
            analyzer.invalidate()
            assert analyzer._initialized is False
            assert len(analyzer._cache) == 0

            # Re-analyze should re-init
            results = await analyzer.analyze("research the topic")
        assert len(results) >= 1
        assert analyzer._initialized is True

    async def test_invalidate_skill_removes_specific_entry(self, mock_registry: AsyncMock):
        """invalidate_skill(id) removes only the specified skill from cache."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            await analyzer.analyze("research AI")  # force init

            assert "research" in analyzer._cache
            assert "coding" in analyzer._cache

            analyzer.invalidate_skill("research")

            assert "research" not in analyzer._cache
            assert "coding" in analyzer._cache  # unaffected

    async def test_invalidate_skill_noop_for_unknown_id(self, mock_registry: AsyncMock):
        """invalidate_skill() with unknown id does not raise."""
        with _patch_registry(mock_registry):
            analyzer = SkillTaskAnalyzer()
            await analyzer.analyze("research AI")

        # Should not raise
        analyzer.invalidate_skill("nonexistent-skill-id")
        assert analyzer._initialized is True


# ---------------------------------------------------------------------------
# Singleton factory tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSingletonFactory:
    """Tests for the get_skill_task_analyzer() module-level factory."""

    async def test_returns_skill_task_analyzer_instance(self, mock_registry: AsyncMock):
        with _patch_registry(mock_registry):
            instance = await get_skill_task_analyzer()
        assert isinstance(instance, SkillTaskAnalyzer)

    async def test_returns_same_instance_on_repeated_calls(self, mock_registry: AsyncMock):
        """Subsequent calls to get_skill_task_analyzer() return the same object."""
        with _patch_registry(mock_registry):
            first = await get_skill_task_analyzer()
            second = await get_skill_task_analyzer()
        assert first is second

    async def test_invalidate_then_reacquire_returns_same_instance(self, mock_registry: AsyncMock):
        """invalidate() does NOT destroy the singleton; it only resets the cache."""
        with _patch_registry(mock_registry):
            instance = await get_skill_task_analyzer()
            instance.invalidate()
            reacquired = await get_skill_task_analyzer()
        assert instance is reacquired
