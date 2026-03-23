"""
Agent Capability Registry.

This module provides a registry for tracking agent capabilities
and routing tasks to the most suitable agents.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from app.domain.models.agent_capability import (
    AgentAssignment,
    AgentCapability,
    AgentProfile,
    CapabilityCategory,
    CapabilityLevel,
    TaskRequirement,
)

logger = logging.getLogger(__name__)

# Default agent profiles with capabilities
DEFAULT_AGENT_PROFILES = {
    "planner": {
        "primary_category": CapabilityCategory.PLANNING,
        "capabilities": [
            {
                "name": "task_decomposition",
                "category": CapabilityCategory.PLANNING,
                "level": CapabilityLevel.EXPERT,
                "description": "Break down complex tasks into actionable steps",
            },
            {
                "name": "requirement_analysis",
                "category": CapabilityCategory.ANALYSIS,
                "level": CapabilityLevel.PROFICIENT,
                "description": "Analyze and extract requirements from user requests",
            },
            {
                "name": "complexity_assessment",
                "category": CapabilityCategory.ANALYSIS,
                "level": CapabilityLevel.PROFICIENT,
                "description": "Assess task complexity and resource needs",
            },
        ],
    },
    "executor": {
        "primary_category": CapabilityCategory.CODING,
        "capabilities": [
            {
                "name": "code_execution",
                "category": CapabilityCategory.CODING,
                "level": CapabilityLevel.EXPERT,
                "description": "Execute code-related tasks",
                "required_tools": ["shell_exec", "file_write", "code_execute"],
            },
            {
                "name": "file_operations",
                "category": CapabilityCategory.FILE,
                "level": CapabilityLevel.EXPERT,
                "description": "Perform file system operations",
                "required_tools": ["file_read", "file_write", "file_search"],
            },
            {
                "name": "web_browsing",
                "category": CapabilityCategory.BROWSER,
                "level": CapabilityLevel.PROFICIENT,
                "description": "Browse and interact with web pages",
                "required_tools": ["browser_view", "browser_navigate"],
            },
            {
                "name": "research",
                "category": CapabilityCategory.RESEARCH,
                "level": CapabilityLevel.PROFICIENT,
                "description": "Conduct research and gather information",
                "required_tools": ["info_search_web", "browser_view"],
            },
        ],
    },
    "critic": {
        "primary_category": CapabilityCategory.VERIFICATION,
        "capabilities": [
            {
                "name": "quality_review",
                "category": CapabilityCategory.VERIFICATION,
                "level": CapabilityLevel.EXPERT,
                "description": "Review output quality and correctness",
            },
            {
                "name": "code_review",
                "category": CapabilityCategory.CODING,
                "level": CapabilityLevel.PROFICIENT,
                "description": "Review code for issues and improvements",
            },
            {
                "name": "fact_checking",
                "category": CapabilityCategory.VERIFICATION,
                "level": CapabilityLevel.PROFICIENT,
                "description": "Verify factual claims and accuracy",
            },
        ],
    },
    "verifier": {
        "primary_category": CapabilityCategory.VERIFICATION,
        "capabilities": [
            {
                "name": "plan_validation",
                "category": CapabilityCategory.VERIFICATION,
                "level": CapabilityLevel.EXPERT,
                "description": "Validate execution plans for feasibility",
            },
            {
                "name": "feasibility_check",
                "category": CapabilityCategory.VERIFICATION,
                "level": CapabilityLevel.EXPERT,
                "description": "Check if tasks are feasible with available tools",
            },
        ],
    },
    "reflection": {
        "primary_category": CapabilityCategory.ANALYSIS,
        "capabilities": [
            {
                "name": "progress_assessment",
                "category": CapabilityCategory.ANALYSIS,
                "level": CapabilityLevel.EXPERT,
                "description": "Assess execution progress and issues",
            },
            {
                "name": "adaptive_replanning",
                "category": CapabilityCategory.PLANNING,
                "level": CapabilityLevel.PROFICIENT,
                "description": "Suggest plan adjustments based on progress",
            },
        ],
    },
}


class AgentRegistry:
    """Registry for agent capabilities and routing.

    Maintains profiles of available agents and their capabilities,
    enabling intelligent task routing based on requirements.
    """

    _MAX_ASSIGNMENTS: int = 200  # Evict oldest assignments to prevent unbounded growth

    def __init__(self) -> None:
        """Initialize the agent registry."""
        self._profiles: dict[str, AgentProfile] = {}
        self._assignments: list[AgentAssignment] = []
        self._initialize_default_profiles()

    def _initialize_default_profiles(self) -> None:
        """Initialize default agent profiles."""
        for agent_type, config in DEFAULT_AGENT_PROFILES.items():
            capabilities = []
            for cap_config in config.get("capabilities", []):
                cap = AgentCapability(
                    name=cap_config["name"],
                    category=cap_config["category"],
                    level=cap_config.get("level", CapabilityLevel.PROFICIENT),
                    description=cap_config.get("description", ""),
                    required_tools=cap_config.get("required_tools", []),
                )
                capabilities.append(cap)

            profile = AgentProfile(
                agent_type=agent_type,
                agent_name=f"{agent_type}_default",
                capabilities=capabilities,
                primary_category=config.get("primary_category"),
            )
            self._profiles[agent_type] = profile

    def register_agent(
        self,
        agent_type: str,
        agent_name: str,
        capabilities: list[AgentCapability],
        primary_category: CapabilityCategory | None = None,
        max_concurrent: int = 1,
    ) -> AgentProfile:
        """Register a new agent with capabilities.

        Args:
            agent_type: Type of agent (planner, executor, etc.)
            agent_name: Unique instance name
            capabilities: List of agent capabilities
            primary_category: Primary capability category
            max_concurrent: Maximum concurrent tasks

        Returns:
            The created agent profile
        """
        profile = AgentProfile(
            agent_type=agent_type,
            agent_name=agent_name,
            capabilities=capabilities,
            primary_category=primary_category,
            max_concurrent_tasks=max_concurrent,
        )
        self._profiles[agent_name] = profile
        logger.info(f"Registered agent: {agent_name} ({agent_type}) with {len(capabilities)} capabilities")
        return profile

    def get_agent(self, agent_name: str) -> AgentProfile | None:
        """Get an agent profile by name."""
        return self._profiles.get(agent_name)

    def get_agents_by_type(self, agent_type: str) -> list[AgentProfile]:
        """Get all agents of a specific type."""
        return [p for p in self._profiles.values() if p.agent_type == agent_type]

    def get_agents_with_capability(
        self,
        capability_name: str,
        min_level: CapabilityLevel = CapabilityLevel.BASIC,
    ) -> list[AgentProfile]:
        """Get agents that have a specific capability."""
        return [profile for profile in self._profiles.values() if profile.has_capability(capability_name, min_level)]

    def get_agents_by_category(
        self,
        category: CapabilityCategory,
    ) -> list[AgentProfile]:
        """Get agents that have capabilities in a category."""
        return [profile for profile in self._profiles.values() if profile.get_capabilities_by_category(category)]

    def find_best_agent(
        self,
        requirement: TaskRequirement,
    ) -> tuple[AgentProfile | None, float]:
        """Find the best agent for a task requirement.

        Args:
            requirement: The task requirements

        Returns:
            Tuple of (best agent profile, suitability score)
        """
        best_agent = None
        best_score = 0.0

        for profile in self._profiles.values():
            score = profile.calculate_suitability(
                requirement.required_category,
                requirement.required_tools,
            )

            # Bonus for matching level
            if profile.has_capability(
                requirement.required_category.value,
                requirement.required_level,
            ):
                score *= 1.1

            if score > best_score and profile.can_take_task():
                best_score = score
                best_agent = profile

        if best_agent:
            logger.debug(f"Best agent for {requirement.task_id}: {best_agent.agent_name} (score={best_score:.2f})")
        else:
            logger.warning(f"No suitable agent found for {requirement.task_id}")

        return best_agent, min(1.0, best_score)

    def route_task(
        self,
        task_id: str,
        task_description: str,
        required_category: CapabilityCategory,
        required_tools: list[str] | None = None,
        priority: int = 1,
    ) -> AgentAssignment | None:
        """Route a task to the best available agent.

        Args:
            task_id: Unique task identifier
            task_description: Description of the task
            required_category: Category of capability needed
            required_tools: Optional list of required tools
            priority: Task priority (1-5)

        Returns:
            Assignment if successful, None if no agent available
        """
        requirement = TaskRequirement(
            task_id=task_id,
            task_description=task_description,
            required_category=required_category,
            required_tools=required_tools or [],
            priority=priority,
        )

        agent, score = self.find_best_agent(requirement)
        if not agent:
            return None

        # Get the capability being used
        cap = agent.get_best_capability_for_category(required_category)
        capability_name = cap.name if cap else "unknown"

        # Create assignment
        assignment = AgentAssignment(
            task_id=task_id,
            agent_name=agent.agent_name,
            agent_type=agent.agent_type,
            capability_used=capability_name,
            suitability_score=score,
        )

        # Update agent load
        agent.current_load += 1
        agent.last_active = datetime.now(UTC)

        self._assignments.append(assignment)
        # Evict oldest completed assignments to prevent unbounded memory growth
        if len(self._assignments) > self._MAX_ASSIGNMENTS:
            self._assignments = self._assignments[-self._MAX_ASSIGNMENTS :]
        logger.info(f"Routed task {task_id} to {agent.agent_name} (capability={capability_name}, score={score:.2f})")

        return assignment

    def complete_assignment(
        self,
        task_id: str,
        success: bool,
        duration_ms: float,
        result_summary: str | None = None,
    ) -> None:
        """Mark an assignment as complete and update metrics.

        Args:
            task_id: The task ID
            success: Whether the task was successful
            duration_ms: Duration in milliseconds
            result_summary: Optional result summary
        """
        # Find assignment
        assignment = None
        for a in self._assignments:
            if a.task_id == task_id and a.completed_at is None:
                assignment = a
                break

        if not assignment:
            logger.warning(f"No active assignment found for task {task_id}")
            return

        # Update assignment
        assignment.completed_at = datetime.now(UTC)
        assignment.success = success
        assignment.result_summary = result_summary

        # Update agent profile
        agent = self.get_agent(assignment.agent_name)
        if agent:
            agent.current_load = max(0, agent.current_load - 1)
            agent.total_tasks_completed += 1

            # Update capability performance
            cap = agent.get_capability(assignment.capability_used)
            if cap:
                cap.update_performance(success, duration_ms)

            # Update overall success rate
            alpha = 0.1
            agent.overall_success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * agent.overall_success_rate

        logger.info(f"Completed assignment {task_id}: success={success}, duration={duration_ms:.0f}ms")

    def get_agent_statistics(self, agent_name: str) -> dict[str, Any]:
        """Get statistics for an agent.

        Args:
            agent_name: The agent name

        Returns:
            Dictionary of statistics
        """
        agent = self.get_agent(agent_name)
        if not agent:
            return {}

        # Get recent assignments
        recent = [a for a in self._assignments if a.agent_name == agent_name and a.completed_at is not None][-10:]

        return {
            "agent_name": agent.agent_name,
            "agent_type": agent.agent_type,
            "total_tasks": agent.total_tasks_completed,
            "success_rate": agent.overall_success_rate,
            "current_load": agent.current_load,
            "is_available": agent.can_take_task(),
            "capabilities": len(agent.capabilities),
            "recent_assignments": len(recent),
        }

    def get_capability_coverage(self) -> dict[CapabilityCategory, int]:
        """Get count of agents for each capability category."""
        coverage: dict[CapabilityCategory, int] = dict.fromkeys(CapabilityCategory, 0)

        for profile in self._profiles.values():
            for cap in profile.capabilities:
                coverage[cap.category] += 1

        return coverage

    def list_all_agents(self) -> list[dict[str, Any]]:
        """List all registered agents with summary info."""
        return [
            {
                "name": p.agent_name,
                "type": p.agent_type,
                "primary_category": p.primary_category.value if p.primary_category else None,
                "capabilities": len(p.capabilities),
                "available": p.can_take_task(),
                "success_rate": p.overall_success_rate,
            }
            for p in self._profiles.values()
        ]


# Global registry instance
_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Get or create the global agent registry."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def reset_agent_registry() -> None:
    """Reset the global agent registry."""
    global _registry
    _registry = None
