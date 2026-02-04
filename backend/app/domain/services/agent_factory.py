"""Manus-style Agent Factory for creating agents with shared dependencies.

This module implements a factory pattern for creating Manus AI-style agents
with shared dependencies and per-session state management.

The factory provides:
- Centralized dependency injection for agents
- Per-session caching of state manifests and context managers
- Consistent agent creation with Manus patterns (blackboard, attention injection)

Usage:
    factory = ManusAgentFactory(
        llm=llm_instance,
        sandbox=sandbox_instance,
        search_tool=search_tool_instance,
        skill_loader=skill_loader_instance
    )

    # Create agents for a session
    critic = factory.create_critic(session_id="session_123")
    orchestrator = factory.create_research_orchestrator(session_id="session_123")

    # Get session components
    components = factory.get_session_components(session_id="session_123")

    # Cleanup when session ends
    factory.cleanup_session(session_id="session_123")
"""

import logging
from typing import Any

from app.domain.models.state_manifest import StateManifest
from app.domain.services.agents.critic_agent import CriticAgent
from app.domain.services.attention_injector import AttentionInjector
from app.domain.services.context_manager import SandboxContextManager
from app.domain.services.research.wide_research import WideResearchOrchestrator
from app.domain.services.skill_loader import SkillLoader

logger = logging.getLogger(__name__)


class ManusAgentFactory:
    """Factory for creating Manus-style agents with shared dependencies.

    The ManusAgentFactory centralizes agent creation and dependency management,
    implementing key Manus AI patterns:

    - **Dependency Injection**: All agents receive properly configured dependencies
    - **State Manifest (Blackboard)**: Per-session shared state for inter-agent communication
    - **Context Manager**: Per-session externalized memory in the sandbox filesystem
    - **Attention Injection**: Shared attention injector to prevent "lost-in-the-middle"

    This factory ensures that all agents within a session share the same state
    infrastructure, enabling the collaborative patterns found in Manus AI.

    Attributes:
        llm: Language model instance for agent operations.
        sandbox: Sandbox instance for file operations and code execution.
        search_tool: Search tool for research operations.
        skill_loader: Optional skill loader for progressive skill disclosure.

    Example:
        >>> factory = ManusAgentFactory(llm=llm, sandbox=sandbox, search_tool=search_tool)
        >>> critic = factory.create_critic(session_id="sess_123")
        >>> orchestrator = factory.create_research_orchestrator(session_id="sess_123")
    """

    def __init__(
        self,
        llm: Any,
        sandbox: Any,
        search_tool: Any,
        skill_loader: SkillLoader | None = None,
    ) -> None:
        """Initialize the ManusAgentFactory.

        Args:
            llm: Language model instance that implements chat() method.
            sandbox: Sandbox instance for file operations.
            search_tool: Search tool for research operations.
            skill_loader: Optional skill loader for progressive disclosure.
        """
        self.llm = llm
        self.sandbox = sandbox
        self.search_tool = search_tool
        self.skill_loader = skill_loader

        # Per-session state storage
        self._manifests: dict[str, StateManifest] = {}
        self._context_managers: dict[str, SandboxContextManager] = {}
        self._attention_injector: AttentionInjector | None = None

        logger.debug(
            "ManusAgentFactory initialized",
            extra={
                "has_llm": llm is not None,
                "has_sandbox": sandbox is not None,
                "has_search_tool": search_tool is not None,
                "has_skill_loader": skill_loader is not None,
            },
        )

    def _get_manifest(self, session_id: str) -> StateManifest:
        """Get or create a StateManifest for a session.

        The manifest provides a shared blackboard for inter-agent communication.
        Each session gets its own manifest to isolate state.

        Args:
            session_id: The session identifier.

        Returns:
            StateManifest instance for the session.
        """
        if session_id not in self._manifests:
            self._manifests[session_id] = StateManifest(session_id=session_id)
            logger.debug(f"Created new StateManifest for session: {session_id}")
        return self._manifests[session_id]

    def _get_context_manager(self, session_id: str) -> SandboxContextManager:
        """Get or create a SandboxContextManager for a session.

        The context manager provides externalized memory in the sandbox
        filesystem, implementing the "File-System-as-Context" pattern.

        Args:
            session_id: The session identifier.

        Returns:
            SandboxContextManager instance for the session.
        """
        if session_id not in self._context_managers:
            self._context_managers[session_id] = SandboxContextManager(
                session_id=session_id,
                sandbox=self.sandbox,
            )
            logger.debug(f"Created new SandboxContextManager for session: {session_id}")
        return self._context_managers[session_id]

    def get_attention_injector(self) -> AttentionInjector:
        """Get the shared AttentionInjector.

        The attention injector is shared across sessions since it's stateless
        except for configuration. It provides goal recitation to prevent
        "lost-in-the-middle" issues in long conversations.

        Returns:
            AttentionInjector instance.
        """
        if self._attention_injector is None:
            self._attention_injector = AttentionInjector()
            logger.debug("Created new AttentionInjector")
        return self._attention_injector

    def create_critic(self, session_id: str) -> CriticAgent:
        """Create a CriticAgent for quality gate pattern.

        The critic reviews outputs against tasks and criteria, providing
        structured feedback for self-correction loops.

        Args:
            session_id: The session identifier.

        Returns:
            CriticAgent configured with the factory's LLM.
        """
        critic = CriticAgent(session_id=session_id, llm=self.llm)
        logger.debug(f"Created CriticAgent for session: {session_id}")
        return critic

    def create_research_orchestrator(
        self,
        session_id: str,
        max_concurrency: int = 10,
    ) -> WideResearchOrchestrator:
        """Create a WideResearchOrchestrator for parallel research.

        The orchestrator implements Manus AI's "Wide Research" pattern:
        - Decomposes research into independent sub-tasks
        - Executes sub-tasks in parallel with separate contexts
        - Synthesizes results with critic review

        Args:
            session_id: The session identifier.
            max_concurrency: Maximum number of parallel research tasks.

        Returns:
            WideResearchOrchestrator configured with search tool, LLM, and critic.
        """
        # Create a dedicated critic for the research orchestrator
        critic = self.create_critic(session_id)

        orchestrator = WideResearchOrchestrator(
            session_id=session_id,
            search_tool=self.search_tool,
            llm=self.llm,
            max_concurrency=max_concurrency,
            critic=critic,
        )
        logger.debug(f"Created WideResearchOrchestrator for session: {session_id} (max_concurrency={max_concurrency})")
        return orchestrator

    def get_session_components(self, session_id: str) -> dict[str, Any]:
        """Get all Manus-style components for a session.

        Returns a dictionary with all the components needed for
        Manus-style agent operation in a single session.

        Args:
            session_id: The session identifier.

        Returns:
            Dictionary containing:
            - manifest: StateManifest for inter-agent communication
            - context_manager: SandboxContextManager for externalized memory
            - attention_injector: AttentionInjector for goal recitation
        """
        return {
            "manifest": self._get_manifest(session_id),
            "context_manager": self._get_context_manager(session_id),
            "attention_injector": self.get_attention_injector(),
        }

    def cleanup_session(self, session_id: str) -> None:
        """Clean up all state for a session.

        Should be called when a session ends to free resources.
        Removes the session's manifest and context manager from cache.

        Args:
            session_id: The session identifier to clean up.
        """
        removed_manifest = self._manifests.pop(session_id, None)
        removed_context = self._context_managers.pop(session_id, None)

        logger.debug(
            f"Cleaned up session: {session_id}",
            extra={
                "removed_manifest": removed_manifest is not None,
                "removed_context_manager": removed_context is not None,
            },
        )
