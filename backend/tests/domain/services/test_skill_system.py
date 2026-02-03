"""Tests for the enhanced skill system components.

Tests the SkillRegistry, SkillTriggerMatcher, and skill integration
with agent execution and planning.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.domain.models.skill import Skill, SkillCategory, SkillInvocationType, SkillSource


class TestSkillRegistry:
    """Tests for SkillRegistry caching and context building."""

    @pytest.fixture
    def sample_skills(self) -> list[Skill]:
        """Create sample skills for testing."""
        return [
            Skill(
                id="research",
                name="Research Assistant",
                description="Expert researcher for information gathering",
                category=SkillCategory.RESEARCH,
                source=SkillSource.OFFICIAL,
                invocation_type=SkillInvocationType.BOTH,
                required_tools=["web_search", "browser_read_page"],
                optional_tools=["search_academic"],
                system_prompt_addition="You are an expert researcher. Use web_search for queries.",
                trigger_patterns=[r"research\s+", r"find\s+information"],
            ),
            Skill(
                id="coding",
                name="Code Assistant",
                description="Expert coder for development tasks",
                category=SkillCategory.CODING,
                source=SkillSource.OFFICIAL,
                invocation_type=SkillInvocationType.AI,
                required_tools=["file_read", "file_write"],
                allowed_tools=["file_read", "file_write", "shell_execute", "code_analyze"],
                system_prompt_addition="You are an expert coder. Follow best practices.",
            ),
            Skill(
                id="user-only-skill",
                name="User Only Skill",
                description="Can only be invoked by user",
                category=SkillCategory.CUSTOM,
                source=SkillSource.CUSTOM,
                invocation_type=SkillInvocationType.USER,
                system_prompt_addition="User-only instructions.",
            ),
        ]

    @pytest.mark.asyncio
    async def test_registry_singleton(self):
        """Test that registry returns singleton instance."""
        from app.domain.services.skill_registry import SkillRegistry

        # Reset for clean test
        SkillRegistry.reset_instance()

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=[]))

            registry1 = await SkillRegistry.get_instance()
            registry2 = await SkillRegistry.get_instance()

            assert registry1 is registry2

        # Clean up
        SkillRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_build_context_with_skills(self, sample_skills):
        """Test context building from skills."""
        from app.domain.services.skill_registry import SkillRegistry

        SkillRegistry.reset_instance()

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=sample_skills))

            registry = await SkillRegistry.get_instance()
            context = await registry.build_context(["research", "coding"])

            # Check prompt addition
            assert "expert researcher" in context.prompt_addition.lower()
            assert "expert coder" in context.prompt_addition.lower()

            # Check required tools
            assert "web_search" in context.required_tools
            assert "file_read" in context.required_tools

            # Check skill IDs
            assert "research" in context.skill_ids
            assert "coding" in context.skill_ids

        SkillRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_get_ai_invokable_skills(self, sample_skills):
        """Test filtering to AI-invokable skills."""
        from app.domain.services.skill_registry import SkillRegistry

        SkillRegistry.reset_instance()

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=sample_skills))

            registry = await SkillRegistry.get_instance()
            ai_skills = await registry.get_ai_invokable_skills()

            # Should include BOTH and AI, not USER
            skill_ids = [s.id for s in ai_skills]
            assert "research" in skill_ids
            assert "coding" in skill_ids
            assert "user-only-skill" not in skill_ids

        SkillRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_tool_restrictions(self, sample_skills):
        """Test that tool restrictions are computed correctly."""
        from app.domain.services.skill_registry import SkillRegistry

        SkillRegistry.reset_instance()

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=sample_skills))

            registry = await SkillRegistry.get_instance()

            # Coding skill has allowed_tools restriction
            context = await registry.build_context(["coding"])
            assert context.allowed_tools is not None
            assert "file_read" in context.allowed_tools
            assert "web_search" not in context.allowed_tools

            # Research skill has no restriction
            context2 = await registry.build_context(["research"])
            assert context2.allowed_tools is None  # No restriction

        SkillRegistry.reset_instance()


class TestSkillTriggerMatcher:
    """Tests for SkillTriggerMatcher pattern matching."""

    @pytest.fixture
    def skill_with_triggers(self) -> Skill:
        """Create a skill with trigger patterns."""
        return Skill(
            id="research",
            name="Research Assistant",
            description="Expert researcher",
            category=SkillCategory.RESEARCH,
            source=SkillSource.OFFICIAL,
            invocation_type=SkillInvocationType.BOTH,
            required_tools=["web_search"],
            system_prompt_addition="Research instructions",
            trigger_patterns=[
                r"research\s+",
                r"find\s+information\s+about",
                r"look\s+up\s+",
            ],
        )

    @pytest.mark.asyncio
    async def test_pattern_matching(self, skill_with_triggers):
        """Test that patterns match correctly."""
        from app.domain.services.skill_registry import SkillRegistry
        from app.domain.services.skill_trigger_matcher import SkillTriggerMatcher

        SkillRegistry.reset_instance()

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=[skill_with_triggers]))

            matcher = SkillTriggerMatcher()
            matches = await matcher.find_matching_skills("research the latest AI trends")

            assert len(matches) == 1
            assert matches[0].skill_id == "research"
            assert matches[0].confidence > 0.0

        SkillRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_no_match_for_unrelated_message(self, skill_with_triggers):
        """Test that unrelated messages don't match."""
        from app.domain.services.skill_registry import SkillRegistry
        from app.domain.services.skill_trigger_matcher import SkillTriggerMatcher

        SkillRegistry.reset_instance()

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=[skill_with_triggers]))

            matcher = SkillTriggerMatcher()
            matches = await matcher.find_matching_skills("write a hello world program")

            assert len(matches) == 0

        SkillRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_user_only_skills_excluded(self):
        """Test that USER-only skills are not matched for AI invocation."""
        from app.domain.services.skill_registry import SkillRegistry
        from app.domain.services.skill_trigger_matcher import SkillTriggerMatcher

        user_only_skill = Skill(
            id="user-only",
            name="User Only",
            description="User only skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.CUSTOM,
            invocation_type=SkillInvocationType.USER,
            system_prompt_addition="Instructions",
            trigger_patterns=[r"test\s+pattern"],
        )

        SkillRegistry.reset_instance()

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=[user_only_skill]))

            matcher = SkillTriggerMatcher()
            matches = await matcher.find_matching_skills("test pattern message")

            # Should not match USER-only skills
            assert len(matches) == 0

        SkillRegistry.reset_instance()


class TestSkillContextResult:
    """Tests for SkillContextResult dataclass."""

    def test_has_tool_restrictions(self):
        """Test tool restriction detection."""
        from app.domain.services.skill_registry import SkillContextResult

        # With restrictions
        result_with = SkillContextResult(
            prompt_addition="test",
            allowed_tools={"tool1", "tool2"},
            required_tools={"tool1"},
            skill_ids=["skill1"],
        )
        assert result_with.has_tool_restrictions() is True

        # Without restrictions
        result_without = SkillContextResult(
            prompt_addition="test",
            allowed_tools=None,
            required_tools={"tool1"},
            skill_ids=["skill1"],
        )
        assert result_without.has_tool_restrictions() is False


class TestSkillIntegration:
    """Integration tests for skill system with agents."""

    @pytest.mark.asyncio
    async def test_skill_invoke_tool_creation(self):
        """Test that skill_invoke tool is created correctly."""
        from app.domain.services.tools.skill_invoke import create_skill_invoke_tool

        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.CUSTOM,
            invocation_type=SkillInvocationType.AI,
            system_prompt_addition="Test instructions",
        )

        tool = create_skill_invoke_tool(
            available_skills=[skill],
            session_id="test-session",
        )

        assert tool.name == "skill_invoke"
        assert "test-skill" in tool.description

    @pytest.mark.asyncio
    async def test_skill_invoke_execution(self):
        """Test skill invocation returns correct instructions."""
        from app.domain.services.tools.skill_invoke import create_skill_invoke_tool

        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.CUSTOM,
            invocation_type=SkillInvocationType.AI,
            system_prompt_addition="Follow these test instructions carefully.",
        )

        tool = create_skill_invoke_tool(
            available_skills=[skill],
            session_id="test-session",
        )

        result = await tool.execute(skill_name="test-skill")

        assert result["success"] is True
        assert "test instructions" in result["instructions"].lower()
        assert result["skill_id"] == "test-skill"

    @pytest.mark.asyncio
    async def test_skill_invoke_unknown_skill(self):
        """Test skill invocation with unknown skill returns error."""
        from app.domain.services.tools.skill_invoke import create_skill_invoke_tool

        tool = create_skill_invoke_tool(
            available_skills=[],
            session_id="test-session",
        )

        result = await tool.execute(skill_name="nonexistent-skill")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestSkillInvokeToolDescriptionTemplate:
    """Tests for SkillInvokeTool description template fix."""

    @pytest.mark.asyncio
    async def test_description_rerendering_on_skill_update(self):
        """Test that description can be re-rendered after set_available_skills()."""
        from app.domain.services.tools.skill_invoke import SkillInvokeTool

        skill1 = Skill(
            id="skill-1",
            name="Skill One",
            description="First skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            invocation_type=SkillInvocationType.AI,
            system_prompt_addition="Instructions 1",
        )
        skill2 = Skill(
            id="skill-2",
            name="Skill Two",
            description="Second skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            invocation_type=SkillInvocationType.AI,
            system_prompt_addition="Instructions 2",
        )

        # Create with first skill
        tool = SkillInvokeTool(available_skills=[skill1], session_id="test")
        assert "skill-1" in tool.description
        assert "skill-2" not in tool.description

        # Update with second skill
        tool.set_available_skills([skill2])
        assert "skill-2" in tool.description
        # Should NOT have the old skill or broken template
        assert "{available_skills}" not in tool.description

        # Update again with both skills
        tool.set_available_skills([skill1, skill2])
        assert "skill-1" in tool.description
        assert "skill-2" in tool.description

    @pytest.mark.asyncio
    async def test_description_empty_skills(self):
        """Test description with no skills."""
        from app.domain.services.tools.skill_invoke import SkillInvokeTool

        tool = SkillInvokeTool(available_skills=[], session_id="test")
        assert "No skills currently available" in tool.description

        # Update to empty again
        tool.set_available_skills([])
        assert "No skills currently available" in tool.description
        assert "{available_skills}" not in tool.description


class TestToolRestrictionIntersection:
    """Tests for tool restriction intersection handling."""

    def test_empty_intersection_fallback(self):
        """Test that empty intersection falls back to union."""
        from app.domain.services.prompts.skill_context import get_allowed_tools_from_skills

        # Two skills with non-overlapping allowed_tools
        skill1 = Skill(
            id="skill-1",
            name="Skill One",
            description="First skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            allowed_tools=["tool_a", "tool_b"],
            system_prompt_addition="Instructions",
        )
        skill2 = Skill(
            id="skill-2",
            name="Skill Two",
            description="Second skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            allowed_tools=["tool_c", "tool_d"],
            system_prompt_addition="Instructions",
        )

        # Intersection would be empty, should fall back to union
        result = get_allowed_tools_from_skills([skill1, skill2])

        # Should contain union of all tools
        assert result is not None
        assert "tool_a" in result
        assert "tool_b" in result
        assert "tool_c" in result
        assert "tool_d" in result

    def test_normal_intersection(self):
        """Test that overlapping allowed_tools produce intersection."""
        from app.domain.services.prompts.skill_context import get_allowed_tools_from_skills

        skill1 = Skill(
            id="skill-1",
            name="Skill One",
            description="First skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            allowed_tools=["tool_a", "tool_b", "tool_shared"],
            system_prompt_addition="Instructions",
        )
        skill2 = Skill(
            id="skill-2",
            name="Skill Two",
            description="Second skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            allowed_tools=["tool_c", "tool_shared"],
            system_prompt_addition="Instructions",
        )

        result = get_allowed_tools_from_skills([skill1, skill2])

        # Should be intersection (only shared tool)
        assert result is not None
        assert "tool_shared" in result
        assert len(result) == 1

    def test_no_restrictions(self):
        """Test that skills without allowed_tools return None."""
        from app.domain.services.prompts.skill_context import get_allowed_tools_from_skills

        skill = Skill(
            id="skill-1",
            name="Skill One",
            description="No restrictions",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            allowed_tools=None,
            system_prompt_addition="Instructions",
        )

        result = get_allowed_tools_from_skills([skill])
        assert result is None


class TestCacheInvalidation:
    """Tests for cache invalidation functions."""

    @pytest.mark.asyncio
    async def test_skill_registry_invalidation(self):
        """Test SkillRegistry.invalidate_skill() clears cache."""
        from app.domain.services.skill_registry import SkillRegistry

        SkillRegistry.reset_instance()

        skill = Skill(
            id="cached-skill",
            name="Cached Skill",
            description="Test",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            system_prompt_addition="Instructions",
        )

        with patch("app.application.services.skill_service.get_skill_service") as mock_service:
            mock_service.return_value = AsyncMock(get_available_skills=AsyncMock(return_value=[skill]))

            registry = await SkillRegistry.get_instance()

            # Skill should be in cache
            cached = await registry.get_skill("cached-skill")
            assert cached is not None

            # Invalidate
            registry.invalidate_skill("cached-skill")

            # Should be removed from cache (direct cache check)
            assert "cached-skill" not in registry._skills

        SkillRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_trigger_matcher_invalidation(self):
        """Test SkillTriggerMatcher cache invalidation."""
        from app.domain.services.skill_trigger_matcher import SkillTriggerMatcher

        skill = Skill(
            id="triggered-skill",
            name="Triggered Skill",
            description="Test",
            category=SkillCategory.CUSTOM,
            source=SkillSource.OFFICIAL,
            invocation_type=SkillInvocationType.AI,
            trigger_patterns=[r"test\s+pattern"],
            system_prompt_addition="Instructions",
        )

        with patch("app.domain.services.skill_registry.SkillRegistry.get_instance") as mock_registry:
            mock_instance = AsyncMock()
            mock_instance.get_available_skills = AsyncMock(return_value=[skill])
            mock_registry.return_value = mock_instance

            matcher = SkillTriggerMatcher()
            await matcher._ensure_initialized()

            # Should have compiled patterns
            assert "triggered-skill" in matcher._compiled_patterns

            # Reset should clear
            matcher.reset()
            assert "triggered-skill" not in matcher._compiled_patterns
            assert matcher._initialized is False


class TestCustomSkillFields:
    """Tests for custom skill advanced field handling."""

    def test_skill_response_includes_all_fields(self):
        """Test that SkillResponse schema includes Claude-style fields."""
        from app.interfaces.schemas.skill import SkillResponse

        # Check fields exist in schema
        fields = SkillResponse.model_fields
        assert "invocation_type" in fields
        assert "allowed_tools" in fields
        assert "supports_dynamic_context" in fields
        assert "trigger_patterns" in fields

    def test_create_skill_request_includes_all_fields(self):
        """Test that CreateCustomSkillRequest schema includes Claude-style fields."""
        from app.interfaces.schemas.skill import CreateCustomSkillRequest

        fields = CreateCustomSkillRequest.model_fields
        assert "invocation_type" in fields
        assert "allowed_tools" in fields
        assert "supports_dynamic_context" in fields
        assert "trigger_patterns" in fields

    def test_update_skill_request_includes_all_fields(self):
        """Test that UpdateCustomSkillRequest schema includes Claude-style fields."""
        from app.interfaces.schemas.skill import UpdateCustomSkillRequest

        fields = UpdateCustomSkillRequest.model_fields
        assert "invocation_type" in fields
        assert "allowed_tools" in fields
        assert "supports_dynamic_context" in fields
        assert "trigger_patterns" in fields
