"""
Dynamic Agent Spawning module.

This module provides dynamic agent spawning based on task requirements,
enabling specialized agents to be created on-demand.
"""

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

from app.domain.models.agent_capability import (
    AgentCapability,
    AgentProfile,
    CapabilityCategory,
    CapabilityLevel,
)
from app.domain.services.agents.communication.protocol import (
    CommunicationProtocol,
    get_communication_protocol,
)
from app.domain.services.agents.registry.capability_registry import (
    AgentRegistry,
    get_agent_registry,
)

logger = logging.getLogger(__name__)


class SpawnTrigger(str, Enum):
    """Triggers for agent spawning."""

    COMPLEXITY_THRESHOLD = "complexity_threshold"  # Task too complex
    TOOL_REQUIREMENTS = "tool_requirements"  # Specific tools needed
    QUALITY_GATE_FAILURE = "quality_gate_failure"  # Quality check failed
    CAPABILITY_GAP = "capability_gap"  # Missing capability
    LOAD_BALANCING = "load_balancing"  # Distribute workload
    SPECIALIZATION = "specialization"  # Task needs specialist
    PARALLEL_EXECUTION = "parallel_execution"  # Run tasks in parallel


class SpawnedAgentConfig:
    """Configuration for a spawned agent."""

    def __init__(
        self,
        agent_type: str,
        agent_name: str,
        parent_id: str | None = None,
        capabilities: list[AgentCapability] | None = None,
        tools: list[str] | None = None,
        context: dict[str, Any] | None = None,
        max_iterations: int = 50,
        timeout_seconds: float = 300,
    ) -> None:
        """Initialize spawned agent configuration.

        Args:
            agent_type: Type of agent to spawn
            agent_name: Unique name for the agent
            parent_id: ID of parent agent that spawned this one
            capabilities: Agent capabilities
            tools: Tools to make available
            context: Context to pass to agent
            max_iterations: Maximum iterations
            timeout_seconds: Timeout in seconds
        """
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.parent_id = parent_id
        self.capabilities = capabilities or []
        self.tools = tools or []
        self.context = context or {}
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        self.created_at = datetime.now(UTC)


class SpawnDecision:
    """Decision about whether and how to spawn an agent."""

    def __init__(
        self,
        should_spawn: bool,
        trigger: SpawnTrigger | None = None,
        config: SpawnedAgentConfig | None = None,
        reason: str = "",
        alternative_actions: list[str] | None = None,
    ) -> None:
        """Initialize spawn decision.

        Args:
            should_spawn: Whether to spawn an agent
            trigger: What triggered the decision
            config: Configuration for the agent
            reason: Explanation of the decision
            alternative_actions: Alternatives if not spawning
        """
        self.should_spawn = should_spawn
        self.trigger = trigger
        self.config = config
        self.reason = reason
        self.alternative_actions = alternative_actions or []


class AgentSpawner:
    """Spawner for dynamically creating specialized agents.

    Analyzes tasks and context to determine when to spawn
    new agents and with what configuration.
    """

    # Complexity thresholds
    COMPLEXITY_SPAWN_THRESHOLD = 0.7  # Spawn if complexity > 0.7
    MAX_SPAWNED_AGENTS = 5  # Maximum concurrent spawned agents

    # Capability to agent type mapping
    CAPABILITY_AGENT_MAP: ClassVar[dict[CapabilityCategory, str]] = {
        CapabilityCategory.RESEARCH: "researcher",
        CapabilityCategory.CODING: "coder",
        CapabilityCategory.ANALYSIS: "analyst",
        CapabilityCategory.VERIFICATION: "critic",
        CapabilityCategory.BROWSER: "browser_agent",
        CapabilityCategory.FILE: "file_agent",
    }

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        protocol: CommunicationProtocol | None = None,
    ) -> None:
        """Initialize the agent spawner.

        Args:
            registry: Agent registry to use
            protocol: Communication protocol to use
        """
        self._registry = registry or get_agent_registry()
        self._protocol = protocol or get_communication_protocol()
        self._spawned_agents: dict[str, SpawnedAgentConfig] = {}
        self._spawn_count = 0

    def should_spawn(
        self,
        task_description: str,
        current_agent_type: str,
        complexity_score: float,
        required_tools: list[str] | None = None,
        quality_failure: bool = False,
    ) -> SpawnDecision:
        """Determine if a new agent should be spawned.

        Args:
            task_description: Description of the task
            current_agent_type: Type of current agent
            complexity_score: Task complexity (0-1)
            required_tools: Tools needed for the task
            quality_failure: Whether a quality check failed

        Returns:
            Decision about spawning
        """
        # Check if we've hit the spawn limit
        if len(self._spawned_agents) >= self.MAX_SPAWNED_AGENTS:
            return SpawnDecision(
                should_spawn=False,
                reason=f"Maximum spawned agents ({self.MAX_SPAWNED_AGENTS}) reached",
                alternative_actions=["Wait for existing agents to complete"],
            )

        # Check for quality gate failure trigger
        if quality_failure:
            return self._decide_for_quality_failure(task_description, current_agent_type)

        # Check for complexity threshold trigger
        if complexity_score >= self.COMPLEXITY_SPAWN_THRESHOLD:
            return self._decide_for_complexity(task_description, current_agent_type, complexity_score)

        # Check for tool requirements trigger
        if required_tools:
            return self._decide_for_tools(task_description, required_tools)

        # Check for specialization needs
        specialization = self._check_specialization_need(task_description)
        if specialization:
            return specialization

        # Default: don't spawn
        return SpawnDecision(
            should_spawn=False,
            reason="No spawn trigger conditions met",
        )

    def spawn_agent(
        self,
        config: SpawnedAgentConfig,
    ) -> AgentProfile:
        """Spawn a new agent with the given configuration.

        Args:
            config: Configuration for the agent

        Returns:
            The spawned agent's profile
        """
        # Register with the registry
        profile = self._registry.register_agent(
            agent_type=config.agent_type,
            agent_name=config.agent_name,
            capabilities=config.capabilities,
            primary_category=self._get_primary_category(config.agent_type),
            max_concurrent=1,
        )

        # Register with communication protocol
        self._protocol.register_agent(config.agent_name)

        # Track spawned agent
        self._spawned_agents[config.agent_name] = config
        self._spawn_count += 1

        logger.info(f"Spawned agent: {config.agent_name} ({config.agent_type}), parent={config.parent_id}")

        return profile

    def terminate_agent(self, agent_name: str) -> bool:
        """Terminate a spawned agent.

        Args:
            agent_name: Name of the agent to terminate

        Returns:
            True if terminated, False if not found
        """
        if agent_name not in self._spawned_agents:
            return False

        # Unregister from protocol
        self._protocol.unregister_agent(agent_name)

        # Remove from tracking
        del self._spawned_agents[agent_name]

        logger.info(f"Terminated spawned agent: {agent_name}")
        return True

    def spawn_for_task(
        self,
        task_id: str,
        task_description: str,
        required_category: CapabilityCategory,
        parent_agent_id: str,
        context: dict[str, Any] | None = None,
    ) -> SpawnedAgentConfig | None:
        """Spawn an agent optimized for a specific task.

        Args:
            task_id: Task ID
            task_description: Task description
            required_category: Required capability category
            parent_agent_id: Parent agent ID
            context: Task context

        Returns:
            Configuration of spawned agent, or None if spawn not needed
        """
        # Determine agent type
        agent_type = self.CAPABILITY_AGENT_MAP.get(required_category, "generic")

        # Create configuration
        agent_name = f"spawned_{agent_type}_{self._spawn_count + 1}"

        # Create appropriate capabilities
        capabilities = self._create_capabilities_for_category(required_category)

        config = SpawnedAgentConfig(
            agent_type=agent_type,
            agent_name=agent_name,
            parent_id=parent_agent_id,
            capabilities=capabilities,
            context=context or {},
        )

        # Spawn the agent
        self.spawn_agent(config)

        return config

    def spawn_parallel_agents(
        self,
        tasks: list[tuple[str, str, CapabilityCategory]],  # (task_id, description, category)
        parent_agent_id: str,
    ) -> list[SpawnedAgentConfig]:
        """Spawn multiple agents for parallel task execution.

        Args:
            tasks: List of (task_id, description, category) tuples
            parent_agent_id: Parent agent ID

        Returns:
            List of spawned agent configurations
        """
        configs = []
        available_slots = self.MAX_SPAWNED_AGENTS - len(self._spawned_agents)

        for task_id, description, category in tasks[:available_slots]:
            config = self.spawn_for_task(
                task_id=task_id,
                task_description=description,
                required_category=category,
                parent_agent_id=parent_agent_id,
            )
            if config:
                configs.append(config)

        logger.info(f"Spawned {len(configs)} parallel agents")
        return configs

    def get_spawned_agents(self) -> list[SpawnedAgentConfig]:
        """Get all currently spawned agents."""
        return list(self._spawned_agents.values())

    def get_agent_count(self) -> int:
        """Get count of currently spawned agents."""
        return len(self._spawned_agents)

    def cleanup_idle_agents(self, max_idle_seconds: float = 300) -> int:
        """Clean up idle spawned agents.

        Args:
            max_idle_seconds: Maximum idle time before cleanup

        Returns:
            Number of agents cleaned up
        """
        now = datetime.now(UTC)
        to_remove = []

        for name, config in self._spawned_agents.items():
            idle_time = (now - config.created_at).total_seconds()
            if idle_time > max_idle_seconds:
                to_remove.append(name)

        for name in to_remove:
            self.terminate_agent(name)

        return len(to_remove)

    def _decide_for_quality_failure(
        self,
        task_description: str,
        current_agent_type: str,
    ) -> SpawnDecision:
        """Decide spawning for quality failure trigger."""
        # Spawn a critic if not already a critic
        if current_agent_type != "critic":
            config = SpawnedAgentConfig(
                agent_type="critic",
                agent_name=f"spawned_critic_{self._spawn_count + 1}",
                capabilities=self._create_capabilities_for_category(CapabilityCategory.VERIFICATION),
            )
            return SpawnDecision(
                should_spawn=True,
                trigger=SpawnTrigger.QUALITY_GATE_FAILURE,
                config=config,
                reason="Quality check failed, spawning critic for review",
            )

        return SpawnDecision(
            should_spawn=False,
            reason="Already using critic agent",
            alternative_actions=["Retry with different approach"],
        )

    def _decide_for_complexity(
        self,
        task_description: str,
        current_agent_type: str,
        complexity_score: float,
    ) -> SpawnDecision:
        """Decide spawning for complexity trigger."""
        # Determine best agent type for the task
        category = self._infer_category_from_task(task_description)
        agent_type = self.CAPABILITY_AGENT_MAP.get(category, "executor")

        if agent_type == current_agent_type:
            return SpawnDecision(
                should_spawn=False,
                reason="Already using appropriate agent type",
                alternative_actions=["Break down task further"],
            )

        config = SpawnedAgentConfig(
            agent_type=agent_type,
            agent_name=f"spawned_{agent_type}_{self._spawn_count + 1}",
            capabilities=self._create_capabilities_for_category(category),
        )

        return SpawnDecision(
            should_spawn=True,
            trigger=SpawnTrigger.COMPLEXITY_THRESHOLD,
            config=config,
            reason=f"Task complexity ({complexity_score:.2f}) exceeds threshold",
        )

    def _decide_for_tools(
        self,
        task_description: str,
        required_tools: list[str],
    ) -> SpawnDecision:
        """Decide spawning for tool requirements trigger."""
        # Check if any registered agent has the required tools
        for tool in required_tools:
            agents = self._registry.get_agents_with_capability(tool)
            if not agents:
                # Need to spawn an agent with this tool
                config = SpawnedAgentConfig(
                    agent_type="tool_specialist",
                    agent_name=f"spawned_tool_{self._spawn_count + 1}",
                    tools=required_tools,
                )
                return SpawnDecision(
                    should_spawn=True,
                    trigger=SpawnTrigger.TOOL_REQUIREMENTS,
                    config=config,
                    reason=f"Required tool '{tool}' not available in current agents",
                )

        return SpawnDecision(
            should_spawn=False,
            reason="Required tools are available",
        )

    def _check_specialization_need(
        self,
        task_description: str,
    ) -> SpawnDecision | None:
        """Check if task needs a specialist agent."""
        task_lower = task_description.lower()

        # Research specialist
        if any(
            word in task_lower for word in ["research", "investigate", "analyze data"]
        ) and not self._registry.get_agents_by_category(CapabilityCategory.RESEARCH):
            config = SpawnedAgentConfig(
                agent_type="researcher",
                agent_name=f"spawned_researcher_{self._spawn_count + 1}",
                capabilities=self._create_capabilities_for_category(CapabilityCategory.RESEARCH),
            )
            return SpawnDecision(
                should_spawn=True,
                trigger=SpawnTrigger.SPECIALIZATION,
                config=config,
                reason="Task requires research specialist",
            )

        return None

    def _infer_category_from_task(self, task_description: str) -> CapabilityCategory:
        """Infer the capability category from task description."""
        task_lower = task_description.lower()

        if any(word in task_lower for word in ["code", "implement", "fix", "debug"]):
            return CapabilityCategory.CODING
        if any(word in task_lower for word in ["research", "search", "find"]):
            return CapabilityCategory.RESEARCH
        if any(word in task_lower for word in ["analyze", "compare", "evaluate"]):
            return CapabilityCategory.ANALYSIS
        if any(word in task_lower for word in ["browse", "website", "web"]):
            return CapabilityCategory.BROWSER
        if any(word in task_lower for word in ["file", "read", "write"]):
            return CapabilityCategory.FILE

        return CapabilityCategory.ANALYSIS  # Default

    def _get_primary_category(self, agent_type: str) -> CapabilityCategory | None:
        """Get primary category for an agent type."""
        type_to_category = {
            "researcher": CapabilityCategory.RESEARCH,
            "coder": CapabilityCategory.CODING,
            "analyst": CapabilityCategory.ANALYSIS,
            "critic": CapabilityCategory.VERIFICATION,
            "browser_agent": CapabilityCategory.BROWSER,
            "file_agent": CapabilityCategory.FILE,
        }
        return type_to_category.get(agent_type)

    def _create_capabilities_for_category(
        self,
        category: CapabilityCategory,
    ) -> list[AgentCapability]:
        """Create default capabilities for a category."""
        capability_templates = {
            CapabilityCategory.RESEARCH: [
                AgentCapability(
                    name="web_research",
                    category=CapabilityCategory.RESEARCH,
                    level=CapabilityLevel.PROFICIENT,
                    description="Conduct web research",
                    required_tools=["info_search_web"],
                ),
            ],
            CapabilityCategory.CODING: [
                AgentCapability(
                    name="code_writing",
                    category=CapabilityCategory.CODING,
                    level=CapabilityLevel.PROFICIENT,
                    description="Write and modify code",
                    required_tools=["file_write", "shell_exec"],
                ),
            ],
            CapabilityCategory.ANALYSIS: [
                AgentCapability(
                    name="data_analysis",
                    category=CapabilityCategory.ANALYSIS,
                    level=CapabilityLevel.PROFICIENT,
                    description="Analyze data and patterns",
                ),
            ],
            CapabilityCategory.VERIFICATION: [
                AgentCapability(
                    name="quality_review",
                    category=CapabilityCategory.VERIFICATION,
                    level=CapabilityLevel.EXPERT,
                    description="Review and validate quality",
                ),
            ],
        }
        return capability_templates.get(category, [])


# Global spawner instance
_spawner: AgentSpawner | None = None


def get_agent_spawner() -> AgentSpawner:
    """Get or create the global agent spawner."""
    global _spawner
    if _spawner is None:
        _spawner = AgentSpawner()
    return _spawner


def reset_agent_spawner() -> None:
    """Reset the global agent spawner."""
    global _spawner
    _spawner = None
