"""
Enhanced Agent Workflow Manager
Provides robust workflow orchestration with comprehensive error handling.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.error_manager import (
    ErrorCategory,
    ErrorSeverity,
    error_context,
    error_handler,
)

logger = logging.getLogger(__name__)


class WorkflowState(str, Enum):
    """Workflow execution states"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


class WorkflowStep(str, Enum):
    """Standard workflow steps"""
    SANDBOX_INIT = "sandbox_init"
    AGENT_INIT = "agent_init"
    PLANNING = "planning"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    CLEANUP = "cleanup"


@dataclass
class WorkflowContext:
    """Context for workflow execution"""
    session_id: str
    agent_id: str
    user_id: str
    current_step: WorkflowStep | None = None
    state: WorkflowState = WorkflowState.INITIALIZING
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class WorkflowManager:
    """Enhanced workflow manager with robust error handling"""

    def __init__(self):
        self._active_workflows: dict[str, WorkflowContext] = {}
        self._step_handlers: dict[WorkflowStep, callable] = {}
        self._recovery_handlers: dict[WorkflowStep, callable] = {}

    def register_step_handler(self, step: WorkflowStep, handler: callable):
        """Register a handler for a workflow step"""
        self._step_handlers[step] = handler

    def register_recovery_handler(self, step: WorkflowStep, handler: callable):
        """Register a recovery handler for a workflow step"""
        self._recovery_handlers[step] = handler

    @error_handler(
        severity=ErrorSeverity.HIGH,
        category=ErrorCategory.AGENT,
        auto_recover=True
    )
    async def start_workflow(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        steps: list[WorkflowStep]
    ) -> bool:
        """Start a new workflow with error handling"""

        context = WorkflowContext(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id
        )

        self._active_workflows[session_id] = context

        try:
            async with error_context(
                component="WorkflowManager",
                operation="start_workflow",
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                category=ErrorCategory.AGENT
            ):
                context.state = WorkflowState.RUNNING

                for step in steps:
                    await self._execute_step(context, step)

                context.state = WorkflowState.COMPLETED
                logger.info(f"Workflow completed successfully for session {session_id}")
                return True

        except Exception as e:
            context.state = WorkflowState.FAILED
            logger.error(f"Workflow failed for session {session_id}: {e}")

            # Attempt recovery
            if await self._attempt_workflow_recovery(context):
                return True

            return False
        finally:
            # Cleanup
            await self._cleanup_workflow(context)

    async def _execute_step(self, context: WorkflowContext, step: WorkflowStep):
        """Execute a single workflow step with error handling"""
        context.current_step = step

        async with error_context(
            component="WorkflowManager",
            operation=f"execute_step_{step.value}",
            session_id=context.session_id,
            agent_id=context.agent_id,
            user_id=context.user_id,
            category=ErrorCategory.AGENT
        ):
            if step not in self._step_handlers:
                raise ValueError(f"No handler registered for step {step}")

            handler = self._step_handlers[step]
            await handler(context)

            logger.debug(f"Step {step.value} completed for session {context.session_id}")

    async def _attempt_workflow_recovery(self, context: WorkflowContext) -> bool:
        """Attempt to recover a failed workflow"""
        if context.current_step and context.current_step in self._recovery_handlers:
            try:
                context.state = WorkflowState.RECOVERING
                recovery_handler = self._recovery_handlers[context.current_step]

                logger.info(f"Attempting recovery for step {context.current_step.value}")
                await recovery_handler(context)

                context.state = WorkflowState.RUNNING
                logger.info(f"Recovery successful for step {context.current_step.value}")
                return True

            except Exception as e:
                logger.error(f"Recovery failed for step {context.current_step.value}: {e}")

        return False

    async def _cleanup_workflow(self, context: WorkflowContext):
        """Clean up workflow resources"""
        try:
            # Execute cleanup step if handler exists
            if WorkflowStep.CLEANUP in self._step_handlers:
                await self._step_handlers[WorkflowStep.CLEANUP](context)

        except Exception as e:
            logger.warning(f"Cleanup failed for session {context.session_id}: {e}")
        finally:
            # Remove from active workflows
            self._active_workflows.pop(context.session_id, None)

    def get_workflow_status(self, session_id: str) -> dict[str, Any] | None:
        """Get current workflow status"""
        context = self._active_workflows.get(session_id)
        if not context:
            return None

        return {
            "session_id": context.session_id,
            "agent_id": context.agent_id,
            "state": context.state.value,
            "current_step": context.current_step.value if context.current_step else None,
            "metadata": context.metadata
        }

    def pause_workflow(self, session_id: str) -> bool:
        """Pause a running workflow"""
        context = self._active_workflows.get(session_id)
        if context and context.state == WorkflowState.RUNNING:
            context.state = WorkflowState.PAUSED
            return True
        return False

    def resume_workflow(self, session_id: str) -> bool:
        """Resume a paused workflow"""
        context = self._active_workflows.get(session_id)
        if context and context.state == WorkflowState.PAUSED:
            context.state = WorkflowState.RUNNING
            return True
        return False


# Global workflow manager instance
_workflow_manager = WorkflowManager()


def get_workflow_manager() -> WorkflowManager:
    """Get the global workflow manager instance"""
    return _workflow_manager


# Standard workflow step implementations
@error_handler(
    severity=ErrorSeverity.CRITICAL,
    category=ErrorCategory.SANDBOX,
    auto_recover=True
)
async def sandbox_init_handler(context: WorkflowContext):
    """Initialize sandbox with robust error handling"""
    logger.info(f"Initializing sandbox for session {context.session_id}")

    # Implementation would initialize sandbox
    # This is a placeholder for the actual sandbox initialization
    context.metadata["sandbox_initialized"] = True


@error_handler(
    severity=ErrorSeverity.HIGH,
    category=ErrorCategory.AGENT,
    auto_recover=True
)
async def agent_init_handler(context: WorkflowContext):
    """Initialize agent with error handling"""
    logger.info(f"Initializing agent {context.agent_id}")

    # Implementation would initialize agent
    context.metadata["agent_initialized"] = True


@error_handler(
    severity=ErrorSeverity.MEDIUM,
    category=ErrorCategory.AGENT,
    auto_recover=True
)
async def planning_handler(context: WorkflowContext):
    """Execute planning phase with error handling"""
    logger.info(f"Starting planning for session {context.session_id}")

    # Implementation would execute planning
    context.metadata["planning_completed"] = True


@error_handler(
    severity=ErrorSeverity.MEDIUM,
    category=ErrorCategory.AGENT,
    auto_recover=True
)
async def execution_handler(context: WorkflowContext):
    """Execute agent actions with error handling"""
    logger.info(f"Starting execution for session {context.session_id}")

    # Implementation would execute agent actions
    context.metadata["execution_completed"] = True


async def cleanup_handler(context: WorkflowContext):
    """Clean up resources"""
    logger.info(f"Cleaning up resources for session {context.session_id}")

    # Implementation would clean up resources
    context.metadata["cleanup_completed"] = True


# Recovery handlers
async def sandbox_recovery_handler(context: WorkflowContext):
    """Recover from sandbox initialization failure"""
    logger.info(f"Attempting sandbox recovery for session {context.session_id}")

    # Implementation would attempt to recover sandbox
    # For example: restart container, check network connectivity, etc.
    await asyncio.sleep(2)  # Simulate recovery time
    context.metadata["sandbox_recovered"] = True


async def agent_recovery_handler(context: WorkflowContext):
    """Recover from agent initialization failure"""
    logger.info(f"Attempting agent recovery for session {context.session_id}")

    # Implementation would attempt to recover agent
    await asyncio.sleep(1)  # Simulate recovery time
    context.metadata["agent_recovered"] = True


# Register handlers
_workflow_manager.register_step_handler(WorkflowStep.SANDBOX_INIT, sandbox_init_handler)
_workflow_manager.register_step_handler(WorkflowStep.AGENT_INIT, agent_init_handler)
_workflow_manager.register_step_handler(WorkflowStep.PLANNING, planning_handler)
_workflow_manager.register_step_handler(WorkflowStep.EXECUTION, execution_handler)
_workflow_manager.register_step_handler(WorkflowStep.CLEANUP, cleanup_handler)

# Register recovery handlers
_workflow_manager.register_recovery_handler(WorkflowStep.SANDBOX_INIT, sandbox_recovery_handler)
_workflow_manager.register_recovery_handler(WorkflowStep.AGENT_INIT, agent_recovery_handler)
