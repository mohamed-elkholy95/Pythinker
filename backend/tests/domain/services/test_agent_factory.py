"""Tests for PythinkerAgentFactory.

These tests verify the factory creates agents with shared dependencies
and properly manages per-session state.
"""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_deps() -> dict:
    """Create mock dependencies for the factory."""
    return {
        "llm": AsyncMock(),
        "sandbox": AsyncMock(),
        "search_tool": AsyncMock(),
        "skill_loader": AsyncMock(),
    }


class TestPythinkerAgentFactory:
    """Test suite for PythinkerAgentFactory."""

    def test_factory_initialization(self, mock_deps: dict) -> None:
        """Test factory initializes with provided dependencies."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)

        assert factory.llm is mock_deps["llm"]
        assert factory.sandbox is mock_deps["sandbox"]
        assert factory.search_tool is mock_deps["search_tool"]
        assert factory.skill_loader is mock_deps["skill_loader"]
        assert factory._manifests == {}
        assert factory._context_managers == {}

    def test_factory_creates_critic(self, mock_deps: dict) -> None:
        """Test factory creates CriticAgent with correct dependencies."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        critic = factory.create_critic(session_id="test")

        assert critic is not None
        assert hasattr(critic, "review")
        assert critic.session_id == "test"
        assert critic.llm is mock_deps["llm"]

    def test_factory_creates_research_orchestrator(self, mock_deps: dict) -> None:
        """Test factory creates WideResearchOrchestrator with correct dependencies."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        orchestrator = factory.create_research_orchestrator(session_id="test")

        assert orchestrator is not None
        assert hasattr(orchestrator, "execute_parallel")
        assert orchestrator.session_id == "test"
        assert orchestrator.search_tool is mock_deps["search_tool"]
        assert orchestrator.llm is mock_deps["llm"]

    def test_factory_creates_research_orchestrator_with_max_concurrency(self, mock_deps: dict) -> None:
        """Test factory creates research orchestrator with custom max_concurrency."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        orchestrator = factory.create_research_orchestrator(session_id="test", max_concurrency=20)

        assert orchestrator.max_concurrency == 20

    def test_research_orchestrator_has_critic(self, mock_deps: dict) -> None:
        """Test that research orchestrator is created with a critic."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        orchestrator = factory.create_research_orchestrator(session_id="test")

        assert orchestrator.critic is not None
        assert hasattr(orchestrator.critic, "review")

    def test_factory_creates_with_shared_state(self, mock_deps: dict) -> None:
        """Test that factory reuses the same manifest for the same session."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        manifest1 = factory._get_manifest(session_id="test")
        manifest2 = factory._get_manifest(session_id="test")

        assert manifest1 is manifest2  # Same instance

    def test_different_sessions_have_different_manifests(self, mock_deps: dict) -> None:
        """Test that different sessions get different manifests."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        manifest1 = factory._get_manifest(session_id="session-1")
        manifest2 = factory._get_manifest(session_id="session-2")

        assert manifest1 is not manifest2
        assert manifest1.session_id == "session-1"
        assert manifest2.session_id == "session-2"

    def test_context_manager_caching(self, mock_deps: dict) -> None:
        """Test that context managers are cached per session."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        cm1 = factory._get_context_manager(session_id="test")
        cm2 = factory._get_context_manager(session_id="test")

        assert cm1 is cm2  # Same instance

    def test_different_sessions_have_different_context_managers(self, mock_deps: dict) -> None:
        """Test that different sessions get different context managers."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        cm1 = factory._get_context_manager(session_id="session-1")
        cm2 = factory._get_context_manager(session_id="session-2")

        assert cm1 is not cm2
        assert cm1.session_id == "session-1"
        assert cm2.session_id == "session-2"

    def test_factory_cleanup_session(self, mock_deps: dict) -> None:
        """Test that cleanup_session removes all session state."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        factory._get_manifest("test")
        factory._get_context_manager("test")

        # Verify state exists
        assert "test" in factory._manifests
        assert "test" in factory._context_managers

        # Cleanup
        factory.cleanup_session("test")

        # Verify state is removed
        assert "test" not in factory._manifests
        assert "test" not in factory._context_managers

    def test_factory_cleanup_nonexistent_session(self, mock_deps: dict) -> None:
        """Test that cleanup_session handles nonexistent sessions gracefully."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)

        # Should not raise an error
        factory.cleanup_session("nonexistent")

    def test_factory_without_skill_loader(self) -> None:
        """Test factory can be created without skill_loader."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(
            llm=AsyncMock(),
            sandbox=AsyncMock(),
            search_tool=AsyncMock(),
            skill_loader=None,
        )

        assert factory.skill_loader is None

    def test_factory_get_attention_injector(self, mock_deps: dict) -> None:
        """Test that factory creates attention injector."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        injector = factory.get_attention_injector()

        assert injector is not None
        assert hasattr(injector, "inject")

    def test_attention_injector_caching(self, mock_deps: dict) -> None:
        """Test that attention injector is cached."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        injector1 = factory.get_attention_injector()
        injector2 = factory.get_attention_injector()

        assert injector1 is injector2

    def test_factory_get_all_components(self, mock_deps: dict) -> None:
        """Test getting all factory components for a session."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        components = factory.get_session_components(session_id="test")

        assert "manifest" in components
        assert "context_manager" in components
        assert "attention_injector" in components
        assert components["manifest"].session_id == "test"
        assert components["context_manager"].session_id == "test"


class TestPythinkerAgentFactoryIntegration:
    """Integration tests for PythinkerAgentFactory with real components."""

    def test_manifest_tracks_session(self, mock_deps: dict) -> None:
        """Test that manifest properly tracks the session ID."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        manifest = factory._get_manifest(session_id="integration-test")

        assert manifest.session_id == "integration-test"
        assert len(manifest.entries) == 0

    def test_context_manager_uses_sandbox(self, mock_deps: dict) -> None:
        """Test that context manager is initialized with the factory's sandbox."""
        from app.domain.services.agent_factory import PythinkerAgentFactory

        factory = PythinkerAgentFactory(**mock_deps)
        cm = factory._get_context_manager(session_id="test")

        assert cm.sandbox is mock_deps["sandbox"]
