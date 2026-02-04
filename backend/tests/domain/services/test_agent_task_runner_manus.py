"""Tests for ManusAgentFactory integration in AgentTaskRunner.

These tests verify that AgentTaskRunner correctly integrates with ManusAgentFactory
for Manus AI-style context management and attention manipulation.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.session import AgentMode


@pytest.fixture
def mock_llm() -> MagicMock:
    """Create mock LLM."""
    return MagicMock()


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    """Create mock sandbox."""
    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.file_read = AsyncMock(return_value=MagicMock(success=True, data={"content": ""}))
    return sandbox


@pytest.fixture
def mock_browser() -> AsyncMock:
    """Create mock browser."""
    return AsyncMock()


@pytest.fixture
def mock_agent_repository() -> AsyncMock:
    """Create mock agent repository."""
    return AsyncMock()


@pytest.fixture
def mock_session_repository() -> AsyncMock:
    """Create mock session repository."""
    repo = AsyncMock()
    repo.add_event = AsyncMock()
    repo.update_status = AsyncMock()
    return repo


@pytest.fixture
def mock_json_parser() -> MagicMock:
    """Create mock JSON parser."""
    return MagicMock()


@pytest.fixture
def mock_file_storage() -> AsyncMock:
    """Create mock file storage."""
    return AsyncMock()


@pytest.fixture
def mock_mcp_repository() -> AsyncMock:
    """Create mock MCP repository."""
    repo = AsyncMock()
    repo.get_mcp_config = AsyncMock(return_value={})
    return repo


@pytest.fixture
def mock_search_engine() -> AsyncMock:
    """Create mock search engine."""
    return AsyncMock()


@pytest.fixture
def runner_deps(
    mock_llm: MagicMock,
    mock_sandbox: AsyncMock,
    mock_browser: AsyncMock,
    mock_agent_repository: AsyncMock,
    mock_session_repository: AsyncMock,
    mock_json_parser: MagicMock,
    mock_file_storage: AsyncMock,
    mock_mcp_repository: AsyncMock,
    mock_search_engine: AsyncMock,
) -> dict:
    """Create all dependencies for AgentTaskRunner."""
    return {
        "session_id": "test-session-123",
        "agent_id": "test-agent-456",
        "user_id": "test-user-789",
        "llm": mock_llm,
        "sandbox": mock_sandbox,
        "browser": mock_browser,
        "agent_repository": mock_agent_repository,
        "session_repository": mock_session_repository,
        "json_parser": mock_json_parser,
        "file_storage": mock_file_storage,
        "mcp_repository": mock_mcp_repository,
        "search_engine": mock_search_engine,
        "mode": AgentMode.DISCUSS,  # Use DISCUSS mode to avoid complex flow initialization
    }


@pytest.fixture
def mock_agent_factory() -> MagicMock:
    """Create mock ManusAgentFactory."""
    factory = MagicMock()

    # Mock context manager with async set_goal
    mock_context_manager = MagicMock()
    mock_context_manager.set_goal = AsyncMock()

    # Mock get_session_components to return proper components
    factory.get_session_components = MagicMock(return_value={
        "manifest": MagicMock(),
        "context_manager": mock_context_manager,
        "attention_injector": MagicMock(),
    })

    factory.cleanup_session = MagicMock()

    return factory


class TestAgentTaskRunnerManusIntegration:
    """Test suite for ManusAgentFactory integration in AgentTaskRunner."""

    def test_init_accepts_agent_factory(self, runner_deps: dict, mock_agent_factory: MagicMock) -> None:
        """Test that AgentTaskRunner accepts agent_factory parameter."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps, agent_factory=mock_agent_factory)

        assert runner._agent_factory is mock_agent_factory

    def test_init_works_without_factory(self, runner_deps: dict) -> None:
        """Test backward compatibility - AgentTaskRunner works without factory."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps)

        assert runner._agent_factory is None

    def test_current_task_default_is_none(self, runner_deps: dict) -> None:
        """Test that current_task attribute defaults to None."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps)

        assert runner.current_task is None

    @pytest.mark.asyncio
    async def test_initialize_gets_session_components(
        self, runner_deps: dict, mock_agent_factory: MagicMock
    ) -> None:
        """Test that initialize() calls get_session_components() on factory."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps, agent_factory=mock_agent_factory)

        await runner.initialize()

        mock_agent_factory.get_session_components.assert_called_once_with(runner_deps["session_id"])
        # Verify components are stored
        assert runner._manifest is not None
        assert runner._context_manager is not None
        assert runner._attention_injector is not None

    @pytest.mark.asyncio
    async def test_initialize_without_factory_is_noop(self, runner_deps: dict) -> None:
        """Test that initialize() is a no-op when factory is None."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps)

        # Should not raise any error
        await runner.initialize()

        # Attributes should remain None
        assert runner._manifest is None
        assert runner._context_manager is None
        assert runner._attention_injector is None

    @pytest.mark.asyncio
    async def test_set_current_task_sets_attribute(self, runner_deps: dict) -> None:
        """Test that _set_current_task sets the current_task attribute."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps)

        await runner._set_current_task("Build a web scraper")

        assert runner.current_task == "Build a web scraper"

    @pytest.mark.asyncio
    async def test_set_current_task_sets_goal_in_context_manager(
        self, runner_deps: dict, mock_agent_factory: MagicMock
    ) -> None:
        """Test that _set_current_task sets goal in context_manager for attention manipulation."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps, agent_factory=mock_agent_factory)

        # First initialize to set up components
        await runner.initialize()

        # Then set the task
        await runner._set_current_task("Build a REST API")

        # Verify goal was set in context manager
        mock_context_manager = mock_agent_factory.get_session_components.return_value["context_manager"]
        mock_context_manager.set_goal.assert_called_once_with("Build a REST API")

    @pytest.mark.asyncio
    async def test_set_current_task_without_context_manager_only_sets_attribute(
        self, runner_deps: dict
    ) -> None:
        """Test that _set_current_task only sets attribute when context_manager is None."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps)

        # Without initialize(), no context_manager
        await runner._set_current_task("Write tests")

        assert runner.current_task == "Write tests"
        # No error should occur

    @pytest.mark.asyncio
    async def test_destroy_cleans_up_factory_session(
        self, runner_deps: dict, mock_agent_factory: MagicMock
    ) -> None:
        """Test that destroy() calls factory.cleanup_session()."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps, agent_factory=mock_agent_factory)

        await runner.destroy()

        mock_agent_factory.cleanup_session.assert_called_once_with(runner_deps["session_id"])

    @pytest.mark.asyncio
    async def test_destroy_without_factory_succeeds(self, runner_deps: dict) -> None:
        """Test that destroy() works without factory (backward compatible)."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps)

        # Should not raise any error
        await runner.destroy()


class TestAgentTaskRunnerManusState:
    """Test suite for Manus component state management."""

    def test_manus_component_attributes_default_to_none(self, runner_deps: dict) -> None:
        """Test that Manus component attributes default to None."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps)

        assert runner._manifest is None
        assert runner._context_manager is None
        assert runner._attention_injector is None

    @pytest.mark.asyncio
    async def test_initialize_multiple_times_only_calls_factory_once(
        self, runner_deps: dict, mock_agent_factory: MagicMock
    ) -> None:
        """Test that initialize() is idempotent - only calls factory once."""
        from app.domain.services.agent_task_runner import AgentTaskRunner

        runner = AgentTaskRunner(**runner_deps, agent_factory=mock_agent_factory)

        await runner.initialize()
        await runner.initialize()  # Second call
        await runner.initialize()  # Third call

        # Factory should only be called once
        mock_agent_factory.get_session_components.assert_called_once()
