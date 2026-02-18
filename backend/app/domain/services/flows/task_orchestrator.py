"""
Task Orchestrator for complex multi-stage workflows.

Provides workflow management with stages, steps, DAG-based dependencies,
parallel execution, configurable concurrency, timeouts, and resource limits.
Builds on the ParallelExecutor foundation.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import (
    Any,
)

from app.domain.models.event import BaseEvent, ErrorEvent, MessageEvent
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.flows.parallel_executor import (
    ExecutionStats,
    ParallelExecutionMode,
    ParallelExecutor,
    StepResult,
)

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Status of a workflow."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(str, Enum):
    """Status of a workflow stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """
    A step within a workflow stage.

    Similar to Plan Step but with additional orchestration metadata.
    """

    id: str
    description: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    result: str | None = None
    error: str | None = None
    agent_type: str | None = None
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_plan_step(self) -> Step:
        """Convert to a Plan Step for execution."""
        return Step(
            id=self.id,
            description=self.description,
            status=self.status,
            dependencies=self.dependencies,
            result=self.result,
            error=self.error,
            agent_type=self.agent_type,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "result": self.result,
            "error": self.error,
            "agent_type": self.agent_type,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            description=data["description"],
            status=ExecutionStatus(data.get("status", "pending")),
            dependencies=data.get("dependencies", []),
            result=data.get("result"),
            error=data.get("error"),
            agent_type=data.get("agent_type"),
            timeout_seconds=data.get("timeout_seconds", 300),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            metadata=data.get("metadata", {}),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class WorkflowStage:
    """
    A stage within a workflow containing multiple steps.

    Stages execute sequentially, but steps within a stage can execute
    in parallel based on their dependencies.
    """

    id: str
    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    status: StageStatus = StageStatus.PENDING
    dependencies: list[str] = field(default_factory=list)  # Stage IDs
    timeout_seconds: int = 1800
    max_concurrency: int = 3
    continue_on_failure: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def get_progress(self) -> dict[str, int]:
        """Get progress of steps in this stage."""
        return {
            "total": len(self.steps),
            "completed": sum(1 for s in self.steps if s.status == ExecutionStatus.COMPLETED),
            "failed": sum(1 for s in self.steps if s.status == ExecutionStatus.FAILED),
            "pending": sum(1 for s in self.steps if s.status == ExecutionStatus.PENDING),
            "running": sum(1 for s in self.steps if s.status == ExecutionStatus.RUNNING),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "dependencies": self.dependencies,
            "timeout_seconds": self.timeout_seconds,
            "max_concurrency": self.max_concurrency,
            "continue_on_failure": self.continue_on_failure,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStage":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            status=StageStatus(data.get("status", "pending")),
            dependencies=data.get("dependencies", []),
            timeout_seconds=data.get("timeout_seconds", 1800),
            max_concurrency=data.get("max_concurrency", 3),
            continue_on_failure=data.get("continue_on_failure", False),
            metadata=data.get("metadata", {}),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class Workflow:
    """
    A complete workflow with multiple stages.

    Workflows manage complex multi-step tasks with stage-level
    sequencing and step-level parallelism.
    """

    id: str
    name: str
    description: str
    stages: list[WorkflowStage] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    context: dict[str, Any] = field(default_factory=dict)  # Shared context
    timeout_seconds: int = 3600
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_progress(self) -> dict[str, Any]:
        """Get overall workflow progress."""
        total_steps = sum(len(stage.steps) for stage in self.stages)
        completed_steps = sum(
            sum(1 for s in stage.steps if s.status == ExecutionStatus.COMPLETED) for stage in self.stages
        )
        failed_steps = sum(sum(1 for s in stage.steps if s.status == ExecutionStatus.FAILED) for stage in self.stages)

        return {
            "total_stages": len(self.stages),
            "completed_stages": sum(1 for s in self.stages if s.status == StageStatus.COMPLETED),
            "failed_stages": sum(1 for s in self.stages if s.status == StageStatus.FAILED),
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "progress_percent": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
        }

    def get_current_stage(self) -> WorkflowStage | None:
        """Get the currently running stage."""
        for stage in self.stages:
            if stage.status == StageStatus.RUNNING:
                return stage
        return None

    def get_next_stage(self) -> WorkflowStage | None:
        """Get the next pending stage with satisfied dependencies."""
        completed_ids = {s.id for s in self.stages if s.status == StageStatus.COMPLETED}

        for stage in self.stages:
            if stage.status != StageStatus.PENDING:
                continue

            # Check dependencies
            if all(dep_id in completed_ids for dep_id in stage.dependencies):
                return stage

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "stages": [s.to_dict() for s in self.stages],
            "status": self.status.value,
            "context": self.context,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            stages=[WorkflowStage.from_dict(s) for s in data.get("stages", [])],
            status=WorkflowStatus(data.get("status", "pending")),
            context=data.get("context", {}),
            timeout_seconds=data.get("timeout_seconds", 3600),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metadata=data.get("metadata", {}),
        )


@dataclass
class OrchestratorConfig:
    """Configuration for the task orchestrator."""

    max_concurrency: int = 3
    default_step_timeout: int = 300
    default_stage_timeout: int = 1800
    default_workflow_timeout: int = 3600
    enable_checkpoints: bool = True
    checkpoint_interval: int = 1  # Checkpoint after every N steps
    retry_failed_steps: bool = True
    max_step_retries: int = 3


class TaskOrchestrator:
    """
    Orchestrates complex multi-stage workflows.

    Features:
    - DAG-based stage and step dependency management
    - Parallel execution within stages
    - Configurable concurrency limits
    - Timeout and resource limits per stage
    - Checkpoint/resume support (via CheckpointManager)
    - Progress tracking and metrics
    """

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        checkpoint_manager: Any | None = None,  # CheckpointManager instance
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Orchestrator configuration
            checkpoint_manager: Optional checkpoint manager for persistence
        """
        self.config = config or OrchestratorConfig()
        self._checkpoint_manager = checkpoint_manager
        self._current_workflow: Workflow | None = None
        self._execution_stats: dict[str, ExecutionStats] = {}
        self._step_results: dict[str, StepResult] = {}

    def create_workflow(
        self,
        name: str,
        description: str,
        stages: list[WorkflowStage] | None = None,
        context: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> Workflow:
        """
        Create a new workflow.

        Args:
            name: Workflow name
            description: Workflow description
            stages: List of stages
            context: Shared context data
            timeout_seconds: Overall timeout

        Returns:
            Created Workflow
        """
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=description,
            stages=stages or [],
            context=context or {},
            timeout_seconds=timeout_seconds or self.config.default_workflow_timeout,
        )

        logger.info(f"Created workflow {workflow_id}: {name}")
        return workflow

    def add_stage(
        self,
        workflow: Workflow,
        name: str,
        description: str,
        steps: list[WorkflowStep] | None = None,
        dependencies: list[str] | None = None,
        timeout_seconds: int | None = None,
        max_concurrency: int | None = None,
    ) -> WorkflowStage:
        """
        Add a stage to a workflow.

        Args:
            workflow: Workflow to add stage to
            name: Stage name
            description: Stage description
            steps: Steps in the stage
            dependencies: Stage IDs this depends on
            timeout_seconds: Stage timeout
            max_concurrency: Max parallel steps

        Returns:
            Created WorkflowStage
        """
        stage_id = f"stage_{len(workflow.stages) + 1}"

        stage = WorkflowStage(
            id=stage_id,
            name=name,
            description=description,
            steps=steps or [],
            dependencies=dependencies or [],
            timeout_seconds=timeout_seconds or self.config.default_stage_timeout,
            max_concurrency=max_concurrency or self.config.max_concurrency,
        )

        workflow.stages.append(stage)
        logger.debug(f"Added stage {stage_id} to workflow {workflow.id}")
        return stage

    def add_step(
        self,
        stage: WorkflowStage,
        description: str,
        dependencies: list[str] | None = None,
        agent_type: str | None = None,
        timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowStep:
        """
        Add a step to a stage.

        Args:
            stage: Stage to add step to
            description: Step description
            dependencies: Step IDs this depends on
            agent_type: Agent type for execution
            timeout_seconds: Step timeout
            metadata: Additional metadata

        Returns:
            Created WorkflowStep
        """
        step_id = f"{stage.id}_step_{len(stage.steps) + 1}"

        step = WorkflowStep(
            id=step_id,
            description=description,
            dependencies=dependencies or [],
            agent_type=agent_type,
            timeout_seconds=timeout_seconds or self.config.default_step_timeout,
            metadata=metadata or {},
        )

        stage.steps.append(step)
        return step

    async def execute_workflow(
        self,
        workflow: Workflow,
        execute_step_func: Callable[[WorkflowStep, dict[str, Any]], Awaitable[StepResult]],
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Execute a workflow.

        Args:
            workflow: Workflow to execute
            execute_step_func: Function to execute individual steps

        Yields:
            Events from execution
        """
        self._current_workflow = workflow
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now(UTC)

        logger.info(f"Starting workflow {workflow.id}: {workflow.name}")

        yield MessageEvent(
            message=f"Starting workflow: {workflow.name}",
        )

        try:
            # Execute stages in order
            while True:
                # Check for timeout
                if workflow.started_at:
                    elapsed = (datetime.now(UTC) - workflow.started_at).total_seconds()
                    if elapsed > workflow.timeout_seconds:
                        workflow.status = WorkflowStatus.FAILED
                        yield ErrorEvent(error=f"Workflow timeout after {elapsed:.0f}s")
                        break

                # Get next stage
                stage = workflow.get_next_stage()
                if not stage:
                    # Check if all stages are complete
                    pending = [s for s in workflow.stages if s.status == StageStatus.PENDING]
                    if pending:
                        # Stages have unmet dependencies - deadlock or failure
                        workflow.status = WorkflowStatus.FAILED
                        yield ErrorEvent(error=f"Workflow has {len(pending)} stages with unmet dependencies")
                    else:
                        # All stages complete
                        workflow.status = WorkflowStatus.COMPLETED
                        workflow.completed_at = datetime.now(UTC)
                    break

                # Execute stage
                async for event in self._execute_stage(workflow, stage, execute_step_func):
                    yield event

                # Checkpoint after stage
                if self.config.enable_checkpoints and self._checkpoint_manager:
                    await self._checkpoint_manager.save_checkpoint(workflow)

        except asyncio.CancelledError:
            workflow.status = WorkflowStatus.CANCELLED
            raise
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            logger.error(f"Workflow {workflow.id} failed: {e}")
            yield ErrorEvent(error=str(e))

        # Final summary
        progress = workflow.get_progress()
        yield MessageEvent(
            message=f"Workflow {workflow.status.value}: "
            f"{progress['completed_steps']}/{progress['total_steps']} steps, "
            f"{progress['completed_stages']}/{progress['total_stages']} stages"
        )

    async def _execute_stage(
        self,
        workflow: Workflow,
        stage: WorkflowStage,
        execute_step_func: Callable[[WorkflowStep, dict[str, Any]], Awaitable[StepResult]],
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Execute a single stage.

        Args:
            workflow: Parent workflow
            stage: Stage to execute
            execute_step_func: Function to execute steps

        Yields:
            Events from execution
        """
        stage.status = StageStatus.RUNNING
        stage.started_at = datetime.now(UTC)

        logger.info(f"Executing stage {stage.id}: {stage.name}")

        yield MessageEvent(message=f"Stage: {stage.name}")

        # Create parallel executor for this stage
        executor = ParallelExecutor(
            max_concurrency=stage.max_concurrency,
            mode=ParallelExecutionMode.PARALLEL,
        )

        # Convert to Plan for parallel execution
        plan = Plan(
            id=f"plan_{stage.id}",
            title=stage.name,
            message=stage.description,
            steps=[step.to_plan_step() for step in stage.steps],
        )

        # Infer dependencies if not set
        if not any(step.dependencies for step in plan.steps):
            plan.infer_smart_dependencies()

        # Execute with timeout
        try:
            async with asyncio.timeout(stage.timeout_seconds):

                async def wrapped_execute(plan_step: Step) -> StepResult:
                    # Find corresponding workflow step
                    wf_step = next((s for s in stage.steps if s.id == plan_step.id), None)
                    if not wf_step:
                        return StepResult(
                            step_id=plan_step.id,
                            success=False,
                            error="Step not found",
                        )

                    wf_step.started_at = datetime.now(UTC)
                    result = await execute_step_func(wf_step, workflow.context)
                    wf_step.completed_at = datetime.now(UTC)

                    # Update workflow step status
                    if result.success:
                        wf_step.status = ExecutionStatus.COMPLETED
                        wf_step.result = result.result
                        # Store result in context for downstream steps
                        workflow.context[f"step_{wf_step.id}_result"] = result.result
                    else:
                        wf_step.status = ExecutionStatus.FAILED
                        wf_step.error = result.error

                    return result

                async for event in executor.execute_plan(plan, wrapped_execute):
                    yield event

        except TimeoutError:
            stage.status = StageStatus.FAILED
            yield ErrorEvent(error=f"Stage {stage.id} timed out after {stage.timeout_seconds}s")
            return

        # Update stage status
        progress = stage.get_progress()
        if progress["failed"] > 0 and not stage.continue_on_failure:
            stage.status = StageStatus.FAILED
        elif progress["completed"] + progress["failed"] == progress["total"]:
            stage.status = StageStatus.COMPLETED
        else:
            stage.status = StageStatus.FAILED

        stage.completed_at = datetime.now(UTC)
        self._execution_stats[stage.id] = executor.get_stats()

        logger.info(f"Stage {stage.id} {stage.status.value}: {progress['completed']}/{progress['total']} completed")

    async def pause_workflow(self, workflow: Workflow) -> bool:
        """
        Pause a running workflow.

        Args:
            workflow: Workflow to pause

        Returns:
            True if paused, False otherwise
        """
        if workflow.status != WorkflowStatus.RUNNING:
            return False

        workflow.status = WorkflowStatus.PAUSED
        logger.info(f"Paused workflow {workflow.id}")

        # Save checkpoint
        if self._checkpoint_manager:
            await self._checkpoint_manager.save_checkpoint(workflow)

        return True

    async def resume_workflow(
        self,
        workflow: Workflow,
        execute_step_func: Callable[[WorkflowStep, dict[str, Any]], Awaitable[StepResult]],
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Resume a paused workflow.

        Args:
            workflow: Workflow to resume
            execute_step_func: Function to execute steps

        Yields:
            Events from execution
        """
        if workflow.status not in [WorkflowStatus.PAUSED, WorkflowStatus.PENDING]:
            yield ErrorEvent(error=f"Cannot resume workflow in status {workflow.status.value}")
            return

        logger.info(f"Resuming workflow {workflow.id}")

        async for event in self.execute_workflow(workflow, execute_step_func):
            yield event

    def get_workflow_stats(self, workflow: Workflow) -> dict[str, Any]:
        """
        Get execution statistics for a workflow.

        Args:
            workflow: Workflow to get stats for

        Returns:
            Dictionary of statistics
        """
        stage_stats = {}
        for stage in workflow.stages:
            if stage.id in self._execution_stats:
                stage_stats[stage.id] = self._execution_stats[stage.id].to_dict()

        return {
            "workflow_id": workflow.id,
            "status": workflow.status.value,
            "progress": workflow.get_progress(),
            "stage_stats": stage_stats,
            "duration_seconds": ((workflow.completed_at or datetime.now(UTC)) - workflow.started_at).total_seconds()
            if workflow.started_at
            else 0,
        }
