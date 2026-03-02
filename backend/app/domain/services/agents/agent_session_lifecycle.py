"""Agent Session Lifecycle Manager.

Handles session lifecycle operations: stop, pause, resume, teardown.
Extracted from AgentDomainService to follow Single Responsibility Principle.
"""

import asyncio
import contextlib
import logging
from typing import Any

from app.domain.external.sandbox import Sandbox
from app.domain.external.task import Task
from app.domain.models.event import MessageEvent
from app.domain.models.session import Session, SessionStatus, TakeoverState
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.browser_login_state_store import BrowserLoginStateStore

logger = logging.getLogger(__name__)


class AgentSessionLifecycle:
    """Manages session lifecycle: stop, pause, resume, and runtime teardown.

    This class owns the session-level locks and background task tracking
    that were previously part of AgentDomainService.
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        sandbox_cls: type[Sandbox],
        task_cls: type[Task],
    ) -> None:
        self._session_repository = session_repository
        self._sandbox_cls = sandbox_cls
        self._task_cls = task_cls
        self._login_state_store = BrowserLoginStateStore()
        # Session-level locks to prevent concurrent task creation for the same session
        self._task_creation_locks: dict[str, asyncio.Lock] = {}
        # Background tasks (prevents garbage collection of fire-and-forget tasks)
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _get_task_creation_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for task creation for a specific session."""
        if session_id not in self._task_creation_locks:
            self._task_creation_locks[session_id] = asyncio.Lock()
        return self._task_creation_locks[session_id]

    def _register_background_task(self, task: asyncio.Task[None]) -> None:
        """Track background tasks and consume failures for observability."""
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[None]) -> None:
        """Consume background task results to avoid silent failures."""
        self._background_tasks.discard(task)
        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.warning("Background task failed in AgentSessionLifecycle: %s", exc)

    async def _force_destroy_sandbox(self, sandbox: Sandbox, sandbox_id: str, session_id: str) -> bool:
        """Best-effort force destroy fallback when graceful destroy times out."""
        force_destroy = getattr(sandbox, "force_destroy", None)
        if not callable(force_destroy):
            logger.warning(
                "Sandbox %s for session %s does not expose force_destroy(); deferred cleanup only",
                sandbox_id,
                session_id,
            )
            return False
        try:
            destroyed = await force_destroy()
            if destroyed:
                logger.info("Force-destroyed sandbox %s for session %s", sandbox_id, session_id)
            else:
                logger.warning("force_destroy returned False for sandbox %s (session %s)", sandbox_id, session_id)
            return bool(destroyed)
        except Exception as e:
            logger.warning("Force-destroy fallback failed for sandbox %s (session %s): %s", sandbox_id, session_id, e)
            return False

    async def _get_task(self, session: Session) -> Task | None:
        """Get a task for the given session."""
        task_id = session.task_id
        if not task_id:
            return None
        return self._task_cls.get(task_id)

    @staticmethod
    def _extract_browser_from_task(task: Task | None) -> Any | None:
        if task is None:
            return None
        browser = getattr(task, "_browser", None)
        if browser is None:
            browser = getattr(task, "browser", None)
        return browser

    async def _persist_login_state_snapshot(self, session: Session, task: Task | None) -> None:
        """Persist browser storage state for a session when takeover requests it."""
        browser = self._extract_browser_from_task(task)
        if browser is None:
            logger.warning("No active browser available for login-state snapshot (session=%s)", session.id)
            return

        export_storage_state = getattr(browser, "export_storage_state", None)
        if not callable(export_storage_state):
            logger.warning("Browser does not support storage-state export (session=%s)", session.id)
            return

        try:
            storage_state = await export_storage_state()
            if not isinstance(storage_state, dict) or not storage_state:
                logger.warning("Storage-state snapshot returned empty payload (session=%s)", session.id)
                return

            persisted = self._login_state_store.save_state(session.user_id, session.id, storage_state)
            if persisted:
                logger.info("Persisted browser login-state snapshot (session=%s)", session.id)
        except Exception as e:
            logger.warning("Failed to snapshot browser login state for session %s: %s", session.id, e)

    async def _teardown_session_runtime(
        self,
        session_id: str,
        session: Session | None = None,
        *,
        status: SessionStatus | None = None,
        destroy_sandbox: bool = True,
    ) -> None:
        """Release runtime resources for a session in an idempotent way."""
        target_session = session or await self._session_repository.find_by_id(session_id)
        if not target_session:
            return

        # Idempotent early-exit: already stopped (no sandbox, terminal status)
        terminal_statuses = (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED)
        if not target_session.sandbox_id and target_session.status in terminal_statuses:
            self._task_creation_locks.pop(session_id, None)
            return

        task = await self._get_task(target_session)
        if task:
            task.cancel()

        # Update status BEFORE sandbox destruction so frontend sees terminal state
        # immediately and does not observe stale in-flight status during teardown.
        target_session.task_id = None
        if status is not None:
            target_session.status = status
        await self._session_repository.save(target_session)

        if destroy_sandbox and target_session.sandbox_id:
            owns_sandbox = target_session.sandbox_owned or target_session.sandbox_lifecycle_mode == "ephemeral"
            if target_session.sandbox_lifecycle_mode is None and not target_session.sandbox_owned:
                from app.core.config import get_settings as _get_settings

                configured_lifecycle_mode = getattr(_get_settings(), "sandbox_lifecycle_mode", "static")
                if configured_lifecycle_mode == "ephemeral":
                    owns_sandbox = True

            if owns_sandbox:
                sandbox = None
                try:
                    sandbox = await self._sandbox_cls.get(target_session.sandbox_id)
                    if sandbox:
                        await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
                        logger.info(f"Destroyed owned sandbox {target_session.sandbox_id} for session {session_id}")
                except TimeoutError:
                    logger.warning(f"Sandbox {target_session.sandbox_id} destroy timed out during teardown")
                    force_destroyed = False
                    if sandbox is not None:
                        try:
                            force_destroyed = await asyncio.wait_for(
                                self._force_destroy_sandbox(
                                    sandbox=sandbox,
                                    sandbox_id=target_session.sandbox_id,
                                    session_id=session_id,
                                ),
                                timeout=10.0,
                            )
                        except TimeoutError:
                            logger.warning(
                                "Force-destroy fallback timed out for sandbox %s (session %s)",
                                target_session.sandbox_id,
                                session_id,
                            )
                        except Exception as e:
                            logger.warning(
                                "Force-destroy fallback raised for sandbox %s (session %s): %s",
                                target_session.sandbox_id,
                                session_id,
                                e,
                            )
                    if not force_destroyed and sandbox is not None:

                        async def _delayed_destroy() -> None:
                            with contextlib.suppress(Exception):
                                await sandbox.destroy()

                        self._register_background_task(asyncio.create_task(_delayed_destroy()))
                except Exception as e:
                    error_text = str(e)
                    if "No such container" in error_text:
                        logger.info(
                            "Sandbox %s already removed during teardown, continuing",
                            target_session.sandbox_id,
                        )
                    else:
                        logger.warning(f"Failed to destroy sandbox {target_session.sandbox_id} during teardown: {e}")
            else:
                logger.info(
                    "Skipping sandbox destroy for session %s (sandbox %s not owned by session)",
                    session_id,
                    target_session.sandbox_id,
                )

            # Clear sandbox references after destruction
            target_session.sandbox_id = None
            target_session.sandbox_owned = False
            target_session.sandbox_created_at = None
            await self._session_repository.save(target_session)

        # Clean up session lock to prevent unbounded growth
        self._task_creation_locks.pop(session_id, None)

    async def stop_session(self, session_id: str) -> None:
        """Stop a session and destroy its sandbox.

        Cancels any running task and destroys the associated sandbox container
        to prevent orphaned Docker containers.
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.info(f"Stop requested for non-existent Session {session_id}; treating as already stopped")
            return
        await self._teardown_session_runtime(
            session_id,
            session=session,
            status=SessionStatus.COMPLETED,
            destroy_sandbox=True,
        )

    async def pause_session(self, session_id: str) -> bool:
        """Pause a session (for user takeover).

        Returns:
            bool: True if the session was paused, False otherwise
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to pause non-existent Session {session_id}")
            raise RuntimeError("Session not found")
        task = await self._get_task(session)
        if task:
            result = task.pause()
            if result:
                logger.info(f"Session {session_id} paused for user takeover")
            return result
        # No active task — the session is already idle/completed, takeover can proceed
        logger.info(f"Session {session_id} has no active task; takeover proceeds immediately")
        return True

    async def resume_session(
        self, session_id: str, context: str | None = None, persist_login_state: bool | None = None
    ) -> bool:
        """Resume a paused session (after user takeover).

        Args:
            session_id: Session ID to resume
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state

        Returns:
            bool: True if the session was resumed, False otherwise
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to resume non-existent Session {session_id}")
            raise RuntimeError("Session not found")
        task = await self._get_task(session)

        # If context is provided, inject it as a message event to inform the agent
        if context is not None:
            context_text = context.strip() if context else ""
            context_message = MessageEvent(
                message=f"""[User Browser Interaction]
The user interacted with the browser directly.
User's summary: {context_text or "No details provided."}

NOTE: The browser state may have changed. When you next use the browser:
1. Take a fresh screenshot to see the current state
2. Adapt your actions based on any changes the user made""",
                role="user",
            )
            await self._session_repository.add_event(session_id, context_message)
            logger.info(f"Injected user takeover context for session {session_id}")

            # Also put it in the task's input stream if task exists
            if task:
                await task.input_stream.put(context_message.model_dump_json())

        # Handle persist_login_state: metadata + optional storage-state snapshot/cleanup
        if persist_login_state is not None:
            session.persist_login_state = persist_login_state
            await self._session_repository.save(session)
            logger.info(f"Session {session_id} persist_login_state set to {persist_login_state}")
            if persist_login_state:
                await self._persist_login_state_snapshot(session, task)
            else:
                self._login_state_store.delete_state(session.user_id, session.id)

        if task:
            result = task.resume()
            if result:
                logger.info(f"Session {session_id} resumed after user takeover")
            return result
        return False

    async def start_takeover(self, session_id: str, reason: str = "manual") -> bool:
        """Start browser takeover by pausing the agent first.

        Transitions: idle -> takeover_requested -> takeover_active
        On failure: rolls back to idle.

        Args:
            session_id: Session ID to take over
            reason: Reason for takeover (manual|captcha|login|2fa|payment|verification)

        Returns:
            bool: True if takeover started successfully
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to start takeover for non-existent Session {session_id}")
            raise RuntimeError("Session not found")

        if session.takeover_state != TakeoverState.IDLE:
            logger.warning(
                f"Session {session_id} takeover already in state {session.takeover_state.value}, treating as idempotent"
            )
            return session.takeover_state == TakeoverState.TAKEOVER_ACTIVE

        # Transition: idle -> takeover_requested
        session.takeover_state = TakeoverState.TAKEOVER_REQUESTED
        session.takeover_reason = reason
        await self._session_repository.save(session)

        # Attempt to pause the agent — must succeed before granting takeover
        try:
            paused = await self.pause_session(session_id)
        except Exception as e:
            logger.error(f"Failed to pause session {session_id} for takeover: {e}")
            # Rollback to idle
            session.takeover_state = TakeoverState.IDLE
            session.takeover_reason = None
            await self._session_repository.save(session)
            raise

        if not paused:
            logger.error(
                f"Session {session_id} pause returned False during takeover start; "
                f"refusing to grant takeover while agent may still be running"
            )
            # Rollback to idle — do not allow takeover while agent may still be running
            session.takeover_state = TakeoverState.IDLE
            session.takeover_reason = None
            await self._session_repository.save(session)
            return False

        # Transition: takeover_requested -> takeover_active
        session.takeover_state = TakeoverState.TAKEOVER_ACTIVE
        await self._session_repository.save(session)
        logger.info(f"Session {session_id} takeover active (reason={reason})")
        return True

    async def end_takeover(
        self,
        session_id: str,
        context: str | None = None,
        persist_login_state: bool | None = None,
        resume_agent: bool = True,
    ) -> bool:
        """End browser takeover and optionally resume the agent.

        Transitions: takeover_active -> resuming -> idle
        On resume failure: stays takeover_active so user can retry.

        Args:
            session_id: Session ID to end takeover for
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state
            resume_agent: Whether to resume the agent after takeover

        Returns:
            bool: True if takeover ended and agent resumed successfully
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to end takeover for non-existent Session {session_id}")
            raise RuntimeError("Session not found")

        if session.takeover_state == TakeoverState.IDLE:
            logger.info(f"Session {session_id} takeover already idle, treating as idempotent")
            return True

        if session.takeover_state not in (TakeoverState.TAKEOVER_ACTIVE, TakeoverState.RESUMING):
            logger.warning(
                f"Session {session_id} in unexpected takeover state {session.takeover_state.value} for end_takeover"
            )

        # Transition: takeover_active -> resuming
        session.takeover_state = TakeoverState.RESUMING
        await self._session_repository.save(session)

        if not resume_agent and persist_login_state is not None:
            session.persist_login_state = persist_login_state
            await self._session_repository.save(session)
            if persist_login_state:
                task = await self._get_task(session)
                await self._persist_login_state_snapshot(session, task)
            else:
                self._login_state_store.delete_state(session.user_id, session.id)

        resumed = True
        if resume_agent:
            try:
                resumed = await self.resume_session(
                    session_id, context=context, persist_login_state=persist_login_state
                )
            except Exception as e:
                logger.error(f"Failed to resume session {session_id} after takeover: {e}")
                # Stay in takeover_active so user can retry
                session.takeover_state = TakeoverState.TAKEOVER_ACTIVE
                await self._session_repository.save(session)
                raise

            if not resumed:
                logger.warning(
                    f"Session {session_id} resume returned False after takeover; "
                    f"staying in takeover_active so user can retry"
                )
                # Per plan (§4.1): Resume failure → remain takeover_active, surface retry
                session = await self._session_repository.find_by_id(session_id)
                if session:
                    session.takeover_state = TakeoverState.TAKEOVER_ACTIVE
                    await self._session_repository.save(session)
                return False
        # resume_agent=False: do not call resume_session at all — context/persist values
        # are metadata only; caller must explicitly request agent resume when ready.

        # Transition: resuming -> idle (only reached when resume succeeded or not requested)
        session = await self._session_repository.find_by_id(session_id)
        if session:
            session.takeover_state = TakeoverState.IDLE
            session.takeover_reason = None
            await self._session_repository.save(session)

        logger.info(f"Session {session_id} takeover ended (resumed={resumed})")
        return resumed
