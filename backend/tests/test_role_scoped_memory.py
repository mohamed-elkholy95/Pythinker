"""Tests for role-scoped memory access."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.long_term_memory import MemoryType
from app.domain.services.role_scoped_memory import (
    ROLE_MEMORY_TYPES,
    RoleScopedMemory,
)


class TestRoleMemoryTypes:
    """Test role-to-memory-type mapping."""

    def test_planner_includes_task_outcomes(self):
        assert MemoryType.TASK_OUTCOME in ROLE_MEMORY_TYPES["planner"]

    def test_planner_includes_error_patterns(self):
        assert MemoryType.ERROR_PATTERN in ROLE_MEMORY_TYPES["planner"]

    def test_planner_includes_procedures(self):
        assert MemoryType.PROCEDURE in ROLE_MEMORY_TYPES["planner"]

    def test_planner_includes_project_context(self):
        assert MemoryType.PROJECT_CONTEXT in ROLE_MEMORY_TYPES["planner"]

    def test_executor_includes_procedures(self):
        assert MemoryType.PROCEDURE in ROLE_MEMORY_TYPES["executor"]

    def test_executor_includes_facts(self):
        assert MemoryType.FACT in ROLE_MEMORY_TYPES["executor"]

    def test_executor_includes_project_context(self):
        assert MemoryType.PROJECT_CONTEXT in ROLE_MEMORY_TYPES["executor"]

    def test_executor_includes_error_patterns(self):
        assert MemoryType.ERROR_PATTERN in ROLE_MEMORY_TYPES["executor"]

    def test_researcher_includes_entities(self):
        assert MemoryType.ENTITY in ROLE_MEMORY_TYPES["researcher"]

    def test_researcher_includes_facts(self):
        assert MemoryType.FACT in ROLE_MEMORY_TYPES["researcher"]

    def test_researcher_includes_project_context(self):
        assert MemoryType.PROJECT_CONTEXT in ROLE_MEMORY_TYPES["researcher"]

    def test_reflector_includes_preferences(self):
        assert MemoryType.PREFERENCE in ROLE_MEMORY_TYPES["reflector"]

    def test_reflector_includes_task_outcomes(self):
        assert MemoryType.TASK_OUTCOME in ROLE_MEMORY_TYPES["reflector"]

    def test_reflector_includes_error_patterns(self):
        assert MemoryType.ERROR_PATTERN in ROLE_MEMORY_TYPES["reflector"]

    def test_all_roles_defined(self):
        assert set(ROLE_MEMORY_TYPES.keys()) == {"planner", "executor", "researcher", "reflector"}

    def test_each_role_has_at_least_two_types(self):
        """Each role should have at least two memory types for meaningful filtering."""
        for role, types in ROLE_MEMORY_TYPES.items():
            assert len(types) >= 2, f"Role {role} should have at least 2 memory types"


class TestRoleScopedMemory:
    """Test RoleScopedMemory class."""

    def _make_scoped(self, role: str = "planner", user_id: str = "user-1") -> RoleScopedMemory:
        """Create a RoleScopedMemory with a mock MemoryService."""
        mock_service = MagicMock()
        mock_service.retrieve_relevant = AsyncMock(return_value=[])
        mock_service.format_memories_for_context = AsyncMock(return_value="formatted")
        return RoleScopedMemory(mock_service, role, user_id)

    @pytest.mark.asyncio
    async def test_get_context_calls_retrieve_with_role_types(self):
        """get_context should filter by the role's allowed memory types."""
        scoped = self._make_scoped("planner")
        await scoped.get_context("build a website")

        call_kwargs = scoped._service.retrieve_relevant.call_args.kwargs
        assert call_kwargs["memory_types"] == ROLE_MEMORY_TYPES["planner"]
        assert call_kwargs["user_id"] == "user-1"
        assert call_kwargs["context"] == "build a website"

    @pytest.mark.asyncio
    async def test_get_context_passes_limit(self):
        """get_context should pass the limit parameter."""
        scoped = self._make_scoped("executor")
        await scoped.get_context("run tests", limit=5)

        call_kwargs = scoped._service.retrieve_relevant.call_args.kwargs
        assert call_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_get_context_returns_empty_on_no_memories(self):
        """get_context should return empty string when no memories found."""
        scoped = self._make_scoped("executor")
        result = await scoped.get_context("run tests")
        assert result == ""

    @pytest.mark.asyncio
    async def test_get_context_formats_when_memories_found(self):
        """get_context should format memories when retrieve returns results."""
        scoped = self._make_scoped("planner")
        mock_memory = MagicMock()
        scoped._service.retrieve_relevant = AsyncMock(return_value=[mock_memory])

        result = await scoped.get_context("deploy app")
        assert result == "formatted"
        scoped._service.format_memories_for_context.assert_called_once_with([mock_memory])

    @pytest.mark.asyncio
    async def test_get_context_handles_errors_gracefully(self):
        """get_context should return empty string on exceptions."""
        scoped = self._make_scoped("planner")
        scoped._service.retrieve_relevant = AsyncMock(side_effect=RuntimeError("db down"))

        result = await scoped.get_context("task")
        assert result == ""

    @pytest.mark.asyncio
    async def test_get_error_patterns_returns_formatted(self):
        """get_error_patterns should format ERROR_PATTERN memories."""
        scoped = self._make_scoped("executor")
        mock_mem = MagicMock()
        mock_mem.memory.content = "Timeout when running npm install"
        scoped._service.retrieve_relevant = AsyncMock(return_value=[mock_mem])

        result = await scoped.get_error_patterns("npm install")
        assert "Timeout" in result
        assert "Known issues" in result

    @pytest.mark.asyncio
    async def test_get_error_patterns_filters_by_error_pattern_type(self):
        """get_error_patterns should only request ERROR_PATTERN memory type."""
        scoped = self._make_scoped("executor")
        await scoped.get_error_patterns("npm install")

        call_kwargs = scoped._service.retrieve_relevant.call_args.kwargs
        assert call_kwargs["memory_types"] == [MemoryType.ERROR_PATTERN]

    @pytest.mark.asyncio
    async def test_get_error_patterns_returns_empty_on_no_results(self):
        """get_error_patterns should return empty string when no patterns found."""
        scoped = self._make_scoped("executor")
        scoped._service.retrieve_relevant = AsyncMock(return_value=[])

        result = await scoped.get_error_patterns("npm install")
        assert result == ""

    @pytest.mark.asyncio
    async def test_get_error_patterns_handles_errors_gracefully(self):
        """get_error_patterns should return empty string on exceptions."""
        scoped = self._make_scoped("executor")
        scoped._service.retrieve_relevant = AsyncMock(side_effect=RuntimeError("fail"))

        result = await scoped.get_error_patterns("npm install")
        assert result == ""

    @pytest.mark.asyncio
    async def test_get_user_preferences(self):
        """get_user_preferences should format PREFERENCE memories."""
        scoped = self._make_scoped("planner")
        mock_mem = MagicMock()
        mock_mem.memory.content = "User prefers TypeScript"
        scoped._service.retrieve_relevant = AsyncMock(return_value=[mock_mem])

        result = await scoped.get_user_preferences()
        assert "TypeScript" in result
        assert "preferences" in result.lower()

    @pytest.mark.asyncio
    async def test_get_user_preferences_filters_by_preference_type(self):
        """get_user_preferences should only request PREFERENCE memory type."""
        scoped = self._make_scoped("planner")
        await scoped.get_user_preferences()

        call_kwargs = scoped._service.retrieve_relevant.call_args.kwargs
        assert call_kwargs["memory_types"] == [MemoryType.PREFERENCE]

    @pytest.mark.asyncio
    async def test_get_user_preferences_returns_empty_on_no_results(self):
        """get_user_preferences should return empty string when no preferences found."""
        scoped = self._make_scoped("planner")
        scoped._service.retrieve_relevant = AsyncMock(return_value=[])

        result = await scoped.get_user_preferences()
        assert result == ""

    @pytest.mark.asyncio
    async def test_get_user_preferences_handles_errors_gracefully(self):
        """get_user_preferences should return empty string on exceptions."""
        scoped = self._make_scoped("planner")
        scoped._service.retrieve_relevant = AsyncMock(side_effect=RuntimeError("fail"))

        result = await scoped.get_user_preferences()
        assert result == ""

    def test_role_property(self):
        """role property should return the configured role."""
        scoped = self._make_scoped("researcher")
        assert scoped.role == "researcher"

    def test_user_id_property(self):
        """user_id property should return the configured user ID."""
        scoped = self._make_scoped(user_id="user-42")
        assert scoped.user_id == "user-42"

    @pytest.mark.asyncio
    async def test_unknown_role_falls_back_to_all_types(self):
        """An unknown role should fall back to all MemoryType values."""
        scoped = self._make_scoped("unknown_role")
        await scoped.get_context("some task")

        call_kwargs = scoped._service.retrieve_relevant.call_args.kwargs
        # Fallback: ROLE_MEMORY_TYPES.get("unknown_role", list(MemoryType)) produces all types
        assert len(call_kwargs["memory_types"]) == len(list(MemoryType))

    @pytest.mark.asyncio
    async def test_get_error_patterns_multiple_memories(self):
        """get_error_patterns should list all returned error patterns."""
        scoped = self._make_scoped("executor")
        mock_mem1 = MagicMock()
        mock_mem1.memory.content = "npm EACCES error"
        mock_mem2 = MagicMock()
        mock_mem2.memory.content = "Docker build timeout"
        scoped._service.retrieve_relevant = AsyncMock(return_value=[mock_mem1, mock_mem2])

        result = await scoped.get_error_patterns("deployment")
        assert "npm EACCES error" in result
        assert "Docker build timeout" in result

    @pytest.mark.asyncio
    async def test_get_user_preferences_multiple_memories(self):
        """get_user_preferences should list all returned preferences."""
        scoped = self._make_scoped("planner")
        mock_mem1 = MagicMock()
        mock_mem1.memory.content = "User prefers TypeScript"
        mock_mem2 = MagicMock()
        mock_mem2.memory.content = "User likes dark themes"
        scoped._service.retrieve_relevant = AsyncMock(return_value=[mock_mem1, mock_mem2])

        result = await scoped.get_user_preferences()
        assert "TypeScript" in result
        assert "dark themes" in result
