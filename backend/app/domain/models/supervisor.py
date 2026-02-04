"""Supervisor model for hierarchical multi-agent system (HMAS).

This module implements the Supervisor model that is part of Manus AI's
Hierarchical Multi-Agent System pattern. Supervisors are mid-level agents
that manage specific domains, handle complex dependencies between sub-tasks,
and coordinate worker agents within their domain.

The hierarchy is:
    Orchestrator -> Supervisors -> Worker Agents

Each supervisor specializes in a domain (research, code, data, browser, etc.)
and is responsible for:
- Breaking down high-level tasks into sub-tasks
- Managing dependencies between sub-tasks
- Assigning sub-tasks to appropriate worker agents
- Tracking sub-task completion and aggregating results
"""

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SupervisorDomain(str, Enum):
    """Domains that supervisors can manage.

    Each domain represents a specialized area of expertise that
    a supervisor can coordinate worker agents for.
    """

    RESEARCH = "research"
    CODE = "code"
    DATA = "data"
    BROWSER = "browser"
    GENERAL = "general"


class SubTaskStatus(str, Enum):
    """Status of a supervised sub-task.

    Tracks the lifecycle of a sub-task from creation to completion.
    """

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SubTask(BaseModel):
    """A sub-task managed by a supervisor.

    Represents a unit of work that can be assigned to a worker agent.
    Sub-tasks can have dependencies on other sub-tasks, which the
    supervisor uses to determine execution order.

    Attributes:
        id: Unique identifier for the sub-task.
        description: Human-readable description of what needs to be done.
        assigned_agent: Name/ID of the worker agent assigned to this task.
        status: Current status of the sub-task.
        result: The output/result of the completed sub-task.
        dependencies: List of sub-task IDs that must complete before this one.
        created_at: UTC timestamp when the sub-task was created.
    """

    id: str
    description: str
    assigned_agent: str | None = None
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Any = None
    dependencies: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Supervisor(BaseModel):
    """A supervisor agent in the hierarchical multi-agent system.

    Implements Manus AI's HMAS pattern for domain-specific task coordination.
    Supervisors sit between the top-level orchestrator and worker agents,
    managing the complexity of task decomposition and dependency resolution
    within their specialized domain.

    Attributes:
        name: Unique name identifying this supervisor.
        domain: The domain this supervisor specializes in.
        description: Human-readable description of the supervisor's purpose.
        tasks: List of sub-tasks currently managed by this supervisor.
        worker_agents: List of worker agent names available to this supervisor.

    Example:
        >>> supervisor = Supervisor(
        ...     name="research-supervisor",
        ...     domain=SupervisorDomain.RESEARCH,
        ...     description="Manages research and information gathering tasks",
        ... )
        >>> task = SubTask(
        ...     id="task_1", description="Search for recent papers on LLM agents", assigned_agent="search-agent"
        ... )
        >>> supervisor.assign_task(task)
        >>> ready_tasks = supervisor.get_ready_tasks()
    """

    name: str
    domain: SupervisorDomain
    description: str = ""
    tasks: list[SubTask] = Field(default_factory=list)
    worker_agents: list[str] = Field(default_factory=list)

    def assign_task(self, task: SubTask) -> None:
        """Assign a task to be managed by this supervisor.

        Adds the task to the supervisor's task list for tracking
        and dependency management.

        Args:
            task: The sub-task to assign to this supervisor.
        """
        logger.debug(
            "Supervisor '%s' assigned task '%s': %s",
            self.name,
            task.id,
            task.description[:50],
        )
        self.tasks.append(task)

    def get_ready_tasks(self) -> list[SubTask]:
        """Get tasks whose dependencies are all completed.

        Returns only pending tasks that have no unmet dependencies,
        meaning they are ready to be executed by worker agents.

        Returns:
            List of sub-tasks that are pending and have all
            dependencies satisfied.
        """
        completed_ids = {task.id for task in self.tasks if task.status == SubTaskStatus.COMPLETED}

        ready_tasks = [
            task
            for task in self.tasks
            if task.status == SubTaskStatus.PENDING and all(dep in completed_ids for dep in task.dependencies)
        ]

        logger.debug(
            "Supervisor '%s' has %d ready tasks out of %d total",
            self.name,
            len(ready_tasks),
            len(self.tasks),
        )

        return ready_tasks

    def complete_task(self, task_id: str, result: Any) -> None:
        """Mark a task as completed with its result.

        Updates the task's status to COMPLETED and stores the result.
        This may unblock dependent tasks, making them available via
        get_ready_tasks().

        Args:
            task_id: The ID of the task to complete.
            result: The output/result of the completed task.
        """
        for task in self.tasks:
            if task.id == task_id:
                task.status = SubTaskStatus.COMPLETED
                task.result = result
                logger.info(
                    "Supervisor '%s' completed task '%s'",
                    self.name,
                    task_id,
                )
                break
