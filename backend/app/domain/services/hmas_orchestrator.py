"""Hierarchical Multi-Agent System (HMAS) Orchestrator.

This module implements the HMAS orchestrator pattern from Manus AI architecture.
The orchestrator sits at the top of the agent hierarchy and is responsible for:

- Registering and managing domain-specific supervisors
- Routing tasks to the appropriate supervisor based on domain
- Coordinating parallel execution while respecting dependencies
- Providing automatic domain detection from task descriptions

Hierarchy:
    Orchestrator (this module)
        -> Supervisors (domain-specific coordinators)
            -> Worker Agents (task executors)

Example:
    >>> orchestrator = HMASOrchestrator(agent_factory=factory)
    >>> orchestrator.register_supervisor(Supervisor(name="research-sup", domain=SupervisorDomain.RESEARCH))
    >>> supervisor = orchestrator.route_task("Research AI trends")
    >>> results = await orchestrator.execute_with_supervisor(supervisor)
"""

import asyncio
import logging
from typing import Any, Protocol

from app.domain.models.supervisor import (
    SubTaskStatus,
    Supervisor,
    SupervisorDomain,
)

logger = logging.getLogger(__name__)


class AgentFactoryProtocol(Protocol):
    """Protocol for agent creation.

    Defines the interface that agent factories must implement to be
    compatible with the HMAS orchestrator.
    """

    def create_agent(self, agent_type: str) -> Any:
        """Create an agent of the specified type.

        Args:
            agent_type: The type/name of agent to create.

        Returns:
            An agent instance with an async execute() method.
        """
        ...


class HMASOrchestrator:
    """Orchestrator for Hierarchical Multi-Agent System.

    Implements Manus AI's HMAS pattern for coordinating multiple supervisors
    and their worker agents. The orchestrator handles task routing, dependency
    management, and parallel execution across the agent hierarchy.

    Attributes:
        agent_factory: Optional factory for creating worker agents.

    Example:
        >>> orchestrator = HMASOrchestrator()
        >>> orchestrator.register_supervisor(Supervisor(name="code-sup", domain=SupervisorDomain.CODE))
        >>> sup = orchestrator.route_task("Write a function", SupervisorDomain.CODE)
        >>> print(sup.name)
        'code-sup'
    """

    # Primary keywords for automatic domain detection (weight: 2)
    # These are strong indicators of a specific domain
    RESEARCH_PRIMARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "research",
            "investigate",
            "gather",
            "look up",
            "discover",
            "explore",
            "study",
            "trends",
            "papers",
            "articles",
            "survey",
            "review",
            "history",
        }
    )

    CODE_PRIMARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "implement",
            "function",
            "class",
            "method",
            "debug",
            "fix",
            "refactor",
            "algorithm",
            "bug",
            "error",
            "module",
            "script",
            "variable",
            "compile",
            "runtime",
            "syntax",
        }
    )

    DATA_PRIMARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "dataset",
            "csv",
            "etl",
            "pipeline",
            "database",
            "sql",
            "schema",
            "migrate",
            "aggregate",
            "statistics",
        }
    )

    BROWSER_PRIMARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "browser",
            "navigate",
            "click",
            "fill",
            "form",
            "scrape",
            "login",
            "button",
            "element",
            "screenshot",
            "browse",
        }
    )

    # Secondary keywords (weight: 1)
    # These are weaker indicators that might appear in multiple contexts
    RESEARCH_SECONDARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "find",
            "search",
            "analyze",
            "information",
            "data",
        }
    )

    CODE_SECONDARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "code",
            "write",
            "program",
            "develop",
            "create",
            "build",
            "python",
            "javascript",
            "typescript",
            "java",
            "rust",
            "go",
        }
    )

    DATA_SECONDARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "data",
            "json",
            "xml",
            "process",
            "transform",
            "clean",
            "parse",
            "table",
        }
    )

    BROWSER_SECONDARY_KEYWORDS: frozenset[str] = frozenset(
        {
            "website",
            "web",
            "page",
            "download",
            "link",
            "url",
            "http",
            "html",
        }
    )

    def __init__(self, agent_factory: AgentFactoryProtocol | None = None) -> None:
        """Initialize the HMAS orchestrator.

        Args:
            agent_factory: Optional factory for creating worker agents.
                If not provided, execute_with_supervisor will require
                tasks to have pre-assigned agents.
        """
        self.agent_factory = agent_factory
        self._supervisors: dict[SupervisorDomain, Supervisor] = {}
        logger.debug("HMASOrchestrator initialized")

    def register_supervisor(self, supervisor: Supervisor) -> None:
        """Register a supervisor for a domain.

        Associates the supervisor with its domain. If a supervisor already
        exists for the domain, it will be replaced.

        Args:
            supervisor: The supervisor to register.
        """
        self._supervisors[supervisor.domain] = supervisor
        logger.info(
            "Registered supervisor '%s' for domain '%s'",
            supervisor.name,
            supervisor.domain.value,
        )

    def get_supervisor(self, domain: SupervisorDomain) -> Supervisor | None:
        """Get a supervisor by domain.

        Args:
            domain: The domain to get the supervisor for.

        Returns:
            The supervisor for the domain, or None if not registered.
        """
        return self._supervisors.get(domain)

    def get_all_supervisors(self) -> list[Supervisor]:
        """Get all registered supervisors.

        Returns:
            List of all registered supervisors.
        """
        return list(self._supervisors.values())

    def route_task(
        self,
        task_description: str,
        domain: SupervisorDomain | None = None,
    ) -> Supervisor | None:
        """Route a task to the appropriate supervisor.

        If a domain is explicitly specified, routes directly to that domain's
        supervisor. Otherwise, attempts to detect the domain from the task
        description using keyword matching.

        Args:
            task_description: Description of the task to route.
            domain: Optional explicit domain specification.

        Returns:
            The supervisor to handle the task, or None if no matching
            supervisor is registered.
        """
        if domain is not None:
            supervisor = self._supervisors.get(domain)
            if supervisor:
                logger.debug(
                    "Routed task to supervisor '%s' (explicit domain: %s)",
                    supervisor.name,
                    domain.value,
                )
            else:
                logger.warning(
                    "No supervisor registered for domain '%s'",
                    domain.value,
                )
            return supervisor

        # Auto-detect domain from task description
        detected_domain = self._detect_domain(task_description)
        supervisor = self._supervisors.get(detected_domain)

        if supervisor:
            logger.debug(
                "Routed task to supervisor '%s' (detected domain: %s)",
                supervisor.name,
                detected_domain.value,
            )
        else:
            logger.warning(
                "No supervisor registered for detected domain '%s'",
                detected_domain.value,
            )

        return supervisor

    def _detect_domain(self, task_description: str) -> SupervisorDomain:
        """Detect the most appropriate domain for a task.

        Uses weighted keyword matching to determine which domain is most
        relevant to the task description. Primary keywords have weight 2,
        secondary keywords have weight 1. Returns GENERAL if no specific
        domain matches strongly.

        Args:
            task_description: The task description to analyze.

        Returns:
            The detected domain for the task.
        """
        description_lower = task_description.lower()

        # Score each domain based on weighted keyword matches
        # Primary keywords: weight 2, Secondary keywords: weight 1
        scores: dict[SupervisorDomain, int] = {
            SupervisorDomain.RESEARCH: self._calculate_weighted_score(
                description_lower,
                self.RESEARCH_PRIMARY_KEYWORDS,
                self.RESEARCH_SECONDARY_KEYWORDS,
            ),
            SupervisorDomain.CODE: self._calculate_weighted_score(
                description_lower,
                self.CODE_PRIMARY_KEYWORDS,
                self.CODE_SECONDARY_KEYWORDS,
            ),
            SupervisorDomain.DATA: self._calculate_weighted_score(
                description_lower,
                self.DATA_PRIMARY_KEYWORDS,
                self.DATA_SECONDARY_KEYWORDS,
            ),
            SupervisorDomain.BROWSER: self._calculate_weighted_score(
                description_lower,
                self.BROWSER_PRIMARY_KEYWORDS,
                self.BROWSER_SECONDARY_KEYWORDS,
            ),
        }

        # Find the domain with the highest score
        max_score = max(scores.values())

        if max_score == 0:
            logger.debug(
                "No domain keywords matched for task: '%s'. Defaulting to GENERAL.",
                task_description[:50],
            )
            return SupervisorDomain.GENERAL

        # Return the domain with the highest score
        for domain, score in scores.items():
            if score == max_score:
                logger.debug(
                    "Detected domain '%s' (score: %d) for task: '%s'",
                    domain.value,
                    score,
                    task_description[:50],
                )
                return domain

        # Fallback (should not reach here)
        return SupervisorDomain.GENERAL

    def _calculate_weighted_score(
        self,
        text: str,
        primary_keywords: frozenset[str],
        secondary_keywords: frozenset[str],
    ) -> int:
        """Calculate weighted score for keyword matches.

        Primary keywords have weight 2, secondary keywords have weight 1.

        Args:
            text: The text to search (should be lowercase).
            primary_keywords: Strong indicator keywords (weight 2).
            secondary_keywords: Weaker indicator keywords (weight 1).

        Returns:
            The weighted score based on keyword matches.
        """
        primary_score = sum(2 for keyword in primary_keywords if keyword in text)
        secondary_score = sum(1 for keyword in secondary_keywords if keyword in text)
        return primary_score + secondary_score

    async def execute_with_supervisor(
        self,
        supervisor: Supervisor,
        max_parallel: int = 5,
    ) -> dict[str, Any]:
        """Execute all tasks under a supervisor.

        Executes tasks managed by the supervisor while respecting their
        dependencies. Tasks without dependencies (or whose dependencies
        are complete) are executed in parallel, up to max_parallel at a time.

        Args:
            supervisor: The supervisor whose tasks to execute.
            max_parallel: Maximum number of tasks to execute in parallel.

        Returns:
            Dictionary mapping task IDs to their results.

        Raises:
            ValueError: If agent_factory is not set and needed.
        """
        results: dict[str, Any] = {}
        semaphore = asyncio.Semaphore(max_parallel)

        logger.info(
            "Starting execution with supervisor '%s' (max_parallel=%d)",
            supervisor.name,
            max_parallel,
        )

        async def execute_task(task_id: str, agent: Any) -> tuple[str, Any]:
            """Execute a single task with the semaphore."""
            async with semaphore:
                logger.debug("Executing task '%s'", task_id)
                try:
                    result = await agent.execute(task_id)
                    return task_id, result
                except Exception as e:
                    logger.error("Task '%s' failed: %s", task_id, str(e))
                    return task_id, str(e)

        # Keep executing until all tasks are complete
        while True:
            ready_tasks = supervisor.get_ready_tasks()

            if not ready_tasks:
                # Check if we're actually done or just waiting
                pending_tasks = [
                    t for t in supervisor.tasks if t.status in (SubTaskStatus.PENDING, SubTaskStatus.IN_PROGRESS)
                ]
                if not pending_tasks:
                    break
                # Still have pending tasks but none are ready - might be blocked
                if not any(t.status == SubTaskStatus.IN_PROGRESS for t in supervisor.tasks):
                    logger.warning("Deadlock detected: tasks pending but none ready")
                    break
                await asyncio.sleep(0.1)
                continue

            # Create execution tasks for all ready tasks
            execution_tasks: list[asyncio.Task[tuple[str, Any]]] = []

            for task in ready_tasks:
                task.status = SubTaskStatus.IN_PROGRESS

                if self.agent_factory and task.assigned_agent:
                    agent = self.agent_factory.create_agent(task.assigned_agent)
                elif self.agent_factory:
                    agent = self.agent_factory.create_agent("default")
                else:
                    # No factory - create a mock that just returns success
                    agent = _MockAgent()

                execution_tasks.append(asyncio.create_task(execute_task(task.id, agent)))

            # Wait for all ready tasks to complete
            completed = await asyncio.gather(*execution_tasks)

            # Record results and mark tasks as complete
            for task_id, result in completed:
                results[task_id] = result
                supervisor.complete_task(task_id, result)
                logger.debug("Task '%s' completed with result: %s", task_id, str(result)[:50])

        logger.info(
            "Supervisor '%s' completed all tasks. Results: %d tasks",
            supervisor.name,
            len(results),
        )

        return results


class _MockAgent:
    """Mock agent for testing when no factory is provided."""

    async def execute(self, task_id: str) -> str:
        """Execute returns a generic completion message."""
        return "Task completed"
