"""
Enhanced Agent Task Runner with Robust Error Handling
Integrates with the new error management and workflow systems.
"""

import logging
from typing import Any

from app.core.error_manager import ErrorCategory, ErrorSeverity, error_context, error_handler
from app.core.sandbox_manager import get_sandbox_manager
from app.core.workflow_manager import WorkflowStep, get_workflow_manager
from app.domain.external.task import TaskRunner
from app.domain.models.session import AgentMode

logger = logging.getLogger(__name__)


class EnhancedAgentTaskRunner(TaskRunner):
    """Enhanced agent task runner with comprehensive error handling"""

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        llm,
        browser,
        agent_repository,
        session_repository,
        json_parser,
        file_storage,
        mcp_repository,
        search_engine=None,
        mode: AgentMode = AgentMode.AGENT,
        **kwargs,
    ):
        self._session_id = session_id
        self._agent_id = agent_id
        self._user_id = user_id
        self._llm = llm
        self._browser = browser
        self._agent_repository = agent_repository
        self._session_repository = session_repository
        self._json_parser = json_parser
        self._file_storage = file_storage
        self._mcp_repository = mcp_repository
        self._search_engine = search_engine
        self._mode = mode

        # Enhanced managers
        self._workflow_manager = get_workflow_manager()
        self._sandbox_manager = get_sandbox_manager()

        # State tracking
        self._is_running = False
        self._current_task = None
        self._sandbox = None

    @error_handler(severity=ErrorSeverity.HIGH, category=ErrorCategory.AGENT, auto_recover=True)
    async def run(self, user_message: str) -> None:
        """Run agent task with comprehensive error handling"""

        if self._is_running:
            logger.warning(f"Agent {self._agent_id} is already running")
            return

        self._is_running = True

        try:
            async with error_context(
                component="EnhancedAgentTaskRunner",
                operation="run",
                session_id=self._session_id,
                agent_id=self._agent_id,
                user_id=self._user_id,
                category=ErrorCategory.AGENT,
                severity=ErrorSeverity.HIGH,
            ):
                # Initialize sandbox
                await self._ensure_sandbox()

                # Start workflow
                workflow_steps = [
                    WorkflowStep.SANDBOX_INIT,
                    WorkflowStep.AGENT_INIT,
                    WorkflowStep.PLANNING,
                    WorkflowStep.EXECUTION,
                ]

                success = await self._workflow_manager.start_workflow(
                    session_id=self._session_id, agent_id=self._agent_id, user_id=self._user_id, steps=workflow_steps
                )

                if not success:
                    raise Exception("Workflow execution failed")

                logger.info(f"Agent task completed successfully for session {self._session_id}")

        except Exception as e:
            logger.error(f"Agent task failed for session {self._session_id}: {e}")

            # Emit error event
            await self._emit_error_event(str(e))

            # Attempt recovery
            await self._attempt_recovery()

        finally:
            self._is_running = False

    @error_handler(severity=ErrorSeverity.CRITICAL, category=ErrorCategory.SANDBOX, auto_recover=True)
    async def _ensure_sandbox(self):
        """Ensure sandbox is available and healthy"""

        async with error_context(
            component="EnhancedAgentTaskRunner",
            operation="ensure_sandbox",
            session_id=self._session_id,
            category=ErrorCategory.SANDBOX,
            severity=ErrorSeverity.CRITICAL,
        ):
            self._sandbox = await self._sandbox_manager.get_sandbox(self._session_id)

            if not self._sandbox:
                raise Exception("Failed to create or retrieve sandbox")

            # Verify sandbox health
            if not await self._sandbox.health_check():
                raise Exception("Sandbox is not healthy")

            logger.info(f"Sandbox ready for session {self._session_id}")

            # Start resource monitoring
            try:
                from app.core.resource_monitor import get_resource_monitor

                resource_monitor = get_resource_monitor()
                container_id = getattr(self._sandbox, "container_id", None)
                if container_id:
                    await resource_monitor.start_monitoring(self._session_id, container_id)
                    logger.info(f"Started resource monitoring for sandbox {container_id}")
            except Exception as e:
                logger.warning(f"Failed to start resource monitoring: {e}")

    async def _attempt_recovery(self):
        """Attempt to recover from task failure"""
        try:
            logger.info(f"Attempting recovery for agent {self._agent_id}")

            # Reset sandbox if needed
            if self._sandbox and not await self._sandbox.health_check():
                logger.info("Recreating unhealthy sandbox")
                await self._sandbox_manager.destroy_sandbox(self._session_id)
                self._sandbox = None

            # Clear any stuck state
            await self._clear_agent_state()

            logger.info(f"Recovery completed for agent {self._agent_id}")

        except Exception as e:
            logger.error(f"Recovery failed for agent {self._agent_id}: {e}")

    async def _clear_agent_state(self):
        """Clear agent state for recovery"""
        try:
            # Reset any persistent state
            # This would clear memory, reset tools, etc.
            logger.debug(f"Clearing state for agent {self._agent_id}")

        except Exception as e:
            logger.warning(f"Failed to clear agent state: {e}")

    async def _emit_error_event(self, error_message: str):
        """Emit error event to session"""
        try:
            from app.domain.models.event import ErrorEvent

            error_event = ErrorEvent(message=error_message, agent_id=self._agent_id)

            # Add event to session
            await self._session_repository.add_event(self._session_id, error_event)

        except Exception as e:
            logger.warning(f"Failed to emit error event: {e}")

    @error_handler(severity=ErrorSeverity.MEDIUM, category=ErrorCategory.AGENT, auto_recover=False)
    async def destroy(self):
        """Clean up resources"""

        try:
            async with error_context(
                component="EnhancedAgentTaskRunner",
                operation="destroy",
                session_id=self._session_id,
                category=ErrorCategory.AGENT,
            ):
                self._is_running = False

                # Clean up sandbox
                if self._sandbox:
                    await self._sandbox_manager.destroy_sandbox(self._session_id)
                    self._sandbox = None

                # Clean up other resources
                if hasattr(self, "_llm"):
                    # Clean up LLM resources if needed
                    pass

                logger.info(f"Agent task runner destroyed for session {self._session_id}")

        except Exception as e:
            logger.error(f"Error during cleanup for session {self._session_id}: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current task runner status"""
        return {
            "session_id": self._session_id,
            "agent_id": self._agent_id,
            "is_running": self._is_running,
            "mode": self._mode.value if self._mode else None,
            "sandbox_healthy": self._sandbox.health.is_healthy if self._sandbox else False,
            "workflow_status": self._workflow_manager.get_workflow_status(self._session_id),
        }

    async def pause(self) -> bool:
        """Pause the running task"""
        if self._is_running:
            return self._workflow_manager.pause_workflow(self._session_id)
        return False

    async def resume(self) -> bool:
        """Resume a paused task"""
        if not self._is_running:
            return self._workflow_manager.resume_workflow(self._session_id)
        return False
