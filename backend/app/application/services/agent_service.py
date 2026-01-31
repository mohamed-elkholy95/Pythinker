import asyncio
import logging
import posixpath
import shlex
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Optional

from app.core.config import get_settings
from app.core.sandbox_pool import get_sandbox_pool
from app.domain.external.file import FileStorage
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task
from app.domain.models.agent import Agent
from app.domain.models.event import AgentEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode, Session, SessionStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agent_domain_service import AgentDomainService
from app.domain.utils.json_parser import JsonParser
from app.interfaces.schemas.file import FileViewResponse
from app.interfaces.schemas.session import ShellViewResponse
from app.interfaces.schemas.workspace import (
    GitRemoteSpec,
    WorkspaceManifest,
    WorkspaceManifestResponse,
    WorkspaceWriteError,
)

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

# Set up logger
logger = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self,
        llm: LLM,
        agent_repository: AgentRepository,
        session_repository: SessionRepository,
        sandbox_cls: type[Sandbox],
        task_cls: type[Task],
        json_parser: JsonParser,
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: SearchEngine | None = None,
        memory_service: Optional["MemoryService"] = None,
    ):
        logger.info("Initializing AgentService")
        self._agent_repository = agent_repository
        self._session_repository = session_repository
        self._file_storage = file_storage
        self._agent_domain_service = AgentDomainService(
            self._agent_repository,
            self._session_repository,
            llm,
            sandbox_cls,
            task_cls,
            json_parser,
            file_storage,
            mcp_repository,
            search_engine,
            memory_service,
        )
        self._llm = llm
        self._search_engine = search_engine
        self._sandbox_cls = sandbox_cls

    async def create_session(self, user_id: str, mode: AgentMode = AgentMode.AGENT) -> Session:
        logger.info(f"Creating new session for user: {user_id} with mode: {mode}")
        agent = await self._create_agent()
        session = Session(agent_id=agent.id, user_id=user_id, mode=mode)
        logger.info(f"Created new Session with ID: {session.id} for user: {user_id} with mode: {mode}")
        await self._session_repository.save(session)

        # Phase 2: Start sandbox creation in background for faster first chat
        settings = get_settings()
        if settings.sandbox_eager_init:
            asyncio.create_task(self._warm_sandbox_for_session(session.id))
            logger.info(f"Started background sandbox warm-up for session {session.id}")

        return session

    async def _warm_sandbox_for_session(self, session_id: str) -> None:
        """Background task to pre-warm sandbox for session.

        Phase 2 optimization: Creates sandbox in background so it's ready
        when the user sends their first chat message.

        Phase 0 enhancement: Uses sandbox pool for instant allocation when enabled.
        Phase 1 enhancement: Pre-warms browser context for immediate use.
        """
        settings = get_settings()

        try:
            # Update session status to INITIALIZING
            await self._session_repository.update_status(session_id, SessionStatus.INITIALIZING)

            # Try to acquire from pool first (Phase 0: instant allocation)
            sandbox = None
            if settings.sandbox_pool_enabled:
                try:
                    pool = await get_sandbox_pool(self._sandbox_cls)
                    if pool.is_started and pool.size > 0:
                        sandbox = await pool.acquire(timeout=5.0)
                        logger.info(f"Acquired sandbox {sandbox.id} from pool for session {session_id}")
                except Exception as e:
                    logger.warning(f"Pool acquisition failed, creating on-demand: {e}")

            # Fall back to on-demand creation
            if not sandbox:
                sandbox = await self._sandbox_cls.create()
                logger.info(f"Created sandbox {sandbox.id} on-demand for session {session_id}")

            # Update session with sandbox_id
            session = await self._session_repository.find_by_id(session_id)
            if session and not session.sandbox_id:
                session.sandbox_id = sandbox.id
                await self._session_repository.save(session)

                # Run ensure_sandbox for full health check (includes browser verification)
                if hasattr(sandbox, "ensure_sandbox"):
                    await sandbox.ensure_sandbox()

                # Phase 1: Pre-warm browser context for immediate use
                await self._prewarm_browser(sandbox, session_id)

                logger.info(f"Sandbox {sandbox.id} fully ready with browser for session {session_id}")

            # Reset status to PENDING (ready for first chat)
            await self._session_repository.update_status(session_id, SessionStatus.PENDING)

        except Exception as e:
            logger.warning(f"Failed to pre-warm sandbox for session {session_id}: {e}")
            # Reset status to PENDING even on failure - first chat will create sandbox
            try:
                await self._session_repository.update_status(session_id, SessionStatus.PENDING)
            except Exception:
                pass

    async def _prewarm_browser(self, sandbox: Sandbox, session_id: str) -> None:
        """Pre-warm browser context so it's ready for immediate use.

        Phase 1 enhancement: Initializes browser connection during sandbox warm-up
        to eliminate browser startup delay on first user action.

        Note: This warms the Chrome browser via CDP. We disconnect Playwright
        but DO NOT close the browser context - it stays ready for later use.
        """
        browser = None
        try:
            # Get sandbox IP for CDP connection
            if not hasattr(sandbox, "ip_address") or not sandbox.ip_address:
                logger.debug("Sandbox has no IP address, skipping browser pre-warm")
                return

            # Import here to avoid circular dependency
            from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

            # Create browser instance with CDP URL
            cdp_url = f"ws://{sandbox.ip_address}:9222"
            browser = PlaywrightBrowser(cdp_url=cdp_url)

            # Initialize browser (this connects to Chrome via CDP)
            if not await browser.initialize():
                logger.warning(f"Browser pre-warm initialization failed for session {session_id}")
                return

            # Navigate to blank page to fully initialize rendering pipeline
            result = await browser.navigate("about:blank", timeout=10000, auto_extract=False)
            if result.success:
                logger.info(f"Browser pre-warmed successfully for session {session_id}")
            else:
                logger.warning(f"Browser pre-warm navigation failed: {result.message}")

        except Exception as e:
            # Non-fatal - browser will be initialized on first use
            logger.warning(f"Browser pre-warm failed (non-fatal) for session {session_id}: {e}")
        finally:
            # Disconnect Playwright but DO NOT close the browser context
            # The context needs to stay open for later use by the agent
            if browser:
                try:
                    # Only disconnect, don't close context/pages
                    if browser.playwright:
                        await browser.playwright.stop()
                    browser.page = None
                    browser.context = None
                    browser.browser = None
                    browser.playwright = None
                except Exception as cleanup_error:
                    logger.debug(f"Browser pre-warm disconnect error (non-fatal): {cleanup_error}")

    async def _create_agent(self) -> Agent:
        logger.info("Creating new agent")

        # Create Agent instance
        agent = Agent(
            model_name=self._llm.model_name,
            temperature=self._llm.temperature,
            max_tokens=self._llm.max_tokens,
        )
        logger.info(f"Created new Agent with ID: {agent.id}")

        # Save agent to repository
        await self._agent_repository.save(agent)
        logger.info(f"Saved agent {agent.id} to repository")

        logger.info(f"Agent created successfully with ID: {agent.id}")
        return agent

    async def chat(
        self,
        session_id: str,
        user_id: str,
        message: str | None = None,
        timestamp: datetime | None = None,
        event_id: str | None = None,
        attachments: list[dict] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        logger.info(f"Starting chat with session {session_id}: {message[:50]}...")
        # Directly use the domain service's chat method, which will check if the session exists
        async for event in self._agent_domain_service.chat(
            session_id, user_id, message, timestamp, event_id, attachments
        ):
            logger.debug(f"Received event: {event}")
            yield event
        logger.info(f"Chat with session {session_id} completed")

    async def get_session(self, session_id: str, user_id: str | None = None) -> Session | None:
        """Get a session by ID, ensuring it belongs to the user"""
        logger.info(f"Getting session {session_id} for user {user_id}")
        if not user_id:
            session = await self._session_repository.find_by_id(session_id)
        else:
            session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
        return session

    async def get_all_sessions(self, user_id: str) -> list[Session]:
        """Get all sessions for a specific user"""
        logger.info(f"Getting all sessions for user {user_id}")
        return await self._session_repository.find_by_user_id(user_id)

    async def delete_session(self, session_id: str, user_id: str) -> None:
        """Delete a session, ensuring it belongs to the user"""
        logger.info(f"Deleting session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        await self._session_repository.delete(session_id)
        logger.info(f"Session {session_id} deleted successfully")

    async def stop_session(self, session_id: str, user_id: str) -> None:
        """Stop a session, ensuring it belongs to the user"""
        logger.info(f"Stopping session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")
        await self._agent_domain_service.stop_session(session_id)
        logger.info(f"Session {session_id} stopped successfully")

    async def pause_session(self, session_id: str, user_id: str) -> bool:
        """Pause a session for user takeover, ensuring it belongs to the user"""
        logger.info(f"Pausing session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")
        result = await self._agent_domain_service.pause_session(session_id)
        if result:
            logger.info(f"Session {session_id} paused successfully")
        return result

    async def resume_session(
        self, session_id: str, user_id: str, context: str | None = None, persist_login_state: bool | None = None
    ) -> bool:
        """Resume a paused session after user takeover, ensuring it belongs to the user

        Args:
            session_id: Session ID to resume
            user_id: User ID for ownership verification
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state
        """
        logger.info(f"Resuming session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")
        result = await self._agent_domain_service.resume_session(
            session_id, context=context, persist_login_state=persist_login_state
        )
        if result:
            logger.info(f"Session {session_id} resumed successfully")
        return result

    async def rename_session(self, session_id: str, user_id: str, title: str) -> None:
        """Rename a session, ensuring it belongs to the user"""
        logger.info(f"Renaming session {session_id} for user {user_id} to '{title}'")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        await self._session_repository.update_title(session_id, title)
        logger.info(f"Session {session_id} renamed successfully")

    async def clear_unread_message_count(self, session_id: str, user_id: str) -> None:
        """Clear the unread message count for a session, ensuring it belongs to the user"""
        logger.info(f"Clearing unread message count for session {session_id} for user {user_id}")
        await self._session_repository.update_unread_message_count(session_id, 0)
        logger.info(f"Unread message count cleared for session {session_id}")

    async def shutdown(self):
        logger.info("Closing all agents and cleaning up resources")
        # Clean up all Agents and their associated sandboxes
        await self._agent_domain_service.shutdown()
        logger.info("All agents closed successfully")

    async def shell_view(self, session_id: str, shell_session_id: str, user_id: str) -> ShellViewResponse:
        """View shell session output, ensuring session belongs to the user"""
        logger.info(f"Getting shell view for session {session_id} for user {user_id}")
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        if not session.sandbox_id:
            raise RuntimeError("Session has no sandbox environment")

        # Get sandbox and shell output
        sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            raise RuntimeError("Sandbox environment not found")

        result = await sandbox.view_shell(shell_session_id, console=True)
        if result.success:
            return ShellViewResponse(**result.data)
        raise RuntimeError(f"Failed to get shell output: {result.message}")

    async def get_vnc_url(self, session_id: str) -> str:
        """Get VNC URL for a session, ensuring it belongs to the user"""
        logger.info(f"Getting VNC URL for session {session_id}")

        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            raise RuntimeError("Session not found")

        if not session.sandbox_id:
            raise RuntimeError("Session has no sandbox environment")

        # Get sandbox and return VNC URL
        sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            raise RuntimeError("Sandbox environment not found")

        return sandbox.vnc_url

    async def file_view(self, session_id: str, file_path: str, user_id: str) -> FileViewResponse:
        """View file content, ensuring session belongs to the user"""
        logger.info(f"Getting file view for session {session_id} for user {user_id}")
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        if not session.sandbox_id:
            raise RuntimeError("Session has no sandbox environment")

        # Get sandbox and file content
        sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            raise RuntimeError("Sandbox environment not found")

        result = await sandbox.file_read(file_path)
        if result.success:
            return FileViewResponse(**result.data)

        error_message = result.message or "Failed to read file"
        # Gracefully handle binary or non-UTF8 content to avoid 500s in the UI.
        if "codec can't decode" in error_message or "invalid start byte" in error_message:
            return FileViewResponse(content=f"[Binary file: {file_path}. Download to view.]", file=file_path)

        raise RuntimeError(f"Failed to read file: {error_message}")

    async def init_workspace_from_manifest(
        self,
        session_id: str,
        manifest: WorkspaceManifest,
        user_id: str,
    ) -> WorkspaceManifestResponse:
        """Initialize a sandbox workspace from a manifest."""
        logger.info("Initializing workspace from manifest for session %s", session_id)
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error("Session %s not found for user %s", session_id, user_id)
            raise RuntimeError("Session not found")

        sandbox = await self._get_or_create_sandbox(session)
        settings = get_settings()

        template_raw = (manifest.template_id or settings.workspace_default_template or "none").strip()
        template_used = self._map_template_id(template_raw, settings.workspace_default_template)

        project_name = self._resolve_project_name(
            manifest.name,
            manifest.path,
            settings.workspace_default_project_name,
        )
        workspace_root = f"/workspace/{session.id}"
        project_root = posixpath.join(workspace_root, project_name)

        exists_result = await sandbox.workspace_exists(session.id)
        if not exists_result.success or not (exists_result.data or {}).get("exists", False):
            await sandbox.workspace_init(
                session.id,
                project_name=project_name,
                template=template_used,
            )

        # Ensure project directory exists
        await sandbox.exec_command(
            session.id,
            "/",
            f"mkdir -p {shlex.quote(project_root)}",
        )

        git_clone_success = None
        git_clone_message = None
        sanitized_git_remote = self._sanitize_git_remote(manifest.git_remote)
        if sanitized_git_remote and sanitized_git_remote.repo_url:
            auth_token = None
            if manifest.git_remote and manifest.git_remote.credentials:
                auth_token = (
                    manifest.git_remote.credentials.get("token")
                    or manifest.git_remote.credentials.get("auth_token")
                    or manifest.git_remote.credentials.get("access_token")
                )
            clone_result = await sandbox.git_clone(
                url=sanitized_git_remote.repo_url,
                target_dir=project_root,
                branch=sanitized_git_remote.branch,
                shallow=True,
                auth_token=auth_token,
            )
            git_clone_success = clone_result.success
            git_clone_message = clone_result.message

        files_written, files_failed, write_errors = await self._write_manifest_files(
            sandbox,
            session.id,
            project_root,
            manifest.path,
            manifest.files,
        )

        # Write .env from env_vars + secrets (do not persist secrets)
        env_content = self._format_env_content(manifest.env_vars, manifest.secrets)
        if env_content:
            env_path = self._safe_join(project_root, ".env")
            env_result = await sandbox.file_write(env_path, env_content)
            if not env_result.success:
                write_errors.append(
                    WorkspaceWriteError(path=env_path, message=env_result.message or "Failed to write .env")
                )
                files_failed += 1
            else:
                files_written += 1

        session.project_name = project_name
        session.project_path = project_root
        session.template_id = manifest.template_id
        session.template_used = template_used
        session.workspace_capabilities = manifest.capabilities or []
        session.dev_command = manifest.dev_command
        session.build_command = manifest.build_command
        session.test_command = manifest.test_command
        session.port = manifest.port
        session.env_var_keys = sorted(manifest.env_vars.keys()) if manifest.env_vars else []
        session.secret_keys = sorted(manifest.secrets.keys()) if manifest.secrets else []
        session.git_remote = sanitized_git_remote.model_dump(exclude={"credentials"}) if sanitized_git_remote else None

        await self._session_repository.save(session)

        return WorkspaceManifestResponse(
            session_id=session.id,
            workspace_root=workspace_root,
            project_root=project_root,
            project_name=project_name,
            project_path=manifest.path,
            template_id=manifest.template_id,
            template_used=template_used,
            capabilities=manifest.capabilities or [],
            files_written=files_written,
            files_failed=files_failed,
            write_errors=write_errors,
            env_var_keys=sorted(manifest.env_vars.keys()) if manifest.env_vars else [],
            secret_keys=sorted(manifest.secrets.keys()) if manifest.secrets else [],
            dev_command=manifest.dev_command,
            build_command=manifest.build_command,
            test_command=manifest.test_command,
            port=manifest.port,
            git_remote=sanitized_git_remote,
            git_clone_success=git_clone_success,
            git_clone_message=git_clone_message,
        )

    async def confirm_action(
        self,
        session_id: str,
        action_id: str,
        accept: bool,
        user_id: str,
    ) -> None:
        """Record user confirmation for a pending tool action."""
        logger.info(
            "Confirming tool action %s for session %s (user %s): %s",
            action_id,
            session_id,
            user_id,
            "accepted" if accept else "rejected",
        )
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        pending_action = session.pending_action or {}
        if pending_action.get("tool_call_id") != action_id:
            logger.warning(
                "Action %s does not match pending action for session %s",
                action_id,
                session_id,
            )

        await self._agent_domain_service.confirm_action(
            session_id=session_id,
            user_id=user_id,
            action_id=action_id,
            accept=accept,
        )

    async def is_session_shared(self, session_id: str) -> bool:
        """Check if a session is shared"""
        logger.info(f"Checking if session {session_id} is shared")
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            raise RuntimeError("Session not found")
        return session.is_shared

    async def get_session_files(self, session_id: str, user_id: str | None = None) -> list[FileInfo]:
        """Get files for a session, ensuring it belongs to the user"""
        logger.info(f"Getting files for session {session_id} for user {user_id}")
        session = await self.get_session(session_id, user_id)
        return session.files

    async def get_shared_session_files(self, session_id: str) -> list[FileInfo]:
        """Get files for a shared session"""
        logger.info(f"Getting files for shared session {session_id}")
        session = await self._session_repository.find_by_id(session_id)
        if not session or not session.is_shared:
            logger.error(f"Shared session {session_id} not found or not shared")
            raise RuntimeError("Session not found")
        return session.files

    async def share_session(self, session_id: str, user_id: str) -> None:
        """Share a session, ensuring it belongs to the user"""
        logger.info(f"Sharing session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        await self._session_repository.update_shared_status(session_id, True)
        logger.info(f"Session {session_id} shared successfully")

    async def unshare_session(self, session_id: str, user_id: str) -> None:
        """Unshare a session, ensuring it belongs to the user"""
        logger.info(f"Unsharing session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        await self._session_repository.update_shared_status(session_id, False)
        logger.info(f"Session {session_id} unshared successfully")

    async def get_shared_session(self, session_id: str) -> Session | None:
        """Get a shared session by ID (no user authentication required)"""
        logger.info(f"Getting shared session {session_id}")
        session = await self._session_repository.find_by_id(session_id)
        if not session or not session.is_shared:
            logger.error(f"Shared session {session_id} not found or not shared")
            return None
        return session

    async def browse_url(self, session_id: str, user_id: str, url: str) -> AsyncGenerator[AgentEvent, None]:
        """Navigate browser directly to a URL from search results.

        This method uses the fast-path router to quickly navigate the browser
        to a specific URL, bypassing the full planning workflow.

        Args:
            session_id: Session ID
            user_id: User ID for ownership verification
            url: URL to navigate to

        Yields:
            Agent events for the navigation
        """
        logger.info(f"Browse URL request for session {session_id}: {url}")

        # Verify session ownership
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")

        # Delegate to domain service for fast-path browsing
        async for event in self._agent_domain_service.browse_url(session_id, url):
            yield event

    async def _get_or_create_sandbox(self, session: Session) -> Sandbox:
        sandbox = None
        if session.sandbox_id:
            sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            sandbox = await self._sandbox_cls.create()
            session.sandbox_id = sandbox.id
        return sandbox

    def _resolve_project_name(
        self,
        name: str | None,
        path: str | None,
        default_name: str,
    ) -> str:
        derived_name = name or (PurePosixPath(path).name if path else "")
        safe_name = PurePosixPath(derived_name).name if derived_name else ""
        return safe_name or default_name

    def _map_template_id(self, template_id: str, default_template: str) -> str:
        key = template_id.strip().lower()
        template_map = {
            "none": "none",
            "python": "python",
            "node": "nodejs",
            "nodejs": "nodejs",
            "web": "web",
            "web-static": "web",
            "fullstack": "fullstack",
        }
        return template_map.get(key, default_template or "none")

    def _sanitize_git_remote(self, git_remote: GitRemoteSpec | None) -> GitRemoteSpec | None:
        if not git_remote:
            return None
        return GitRemoteSpec(
            repo_url=git_remote.repo_url,
            remote_name=git_remote.remote_name,
            branch=git_remote.branch,
        )

    async def _write_manifest_files(
        self,
        sandbox: Sandbox,
        session_id: str,
        project_root: str,
        manifest_root: str | None,
        files: dict[str, str],
    ) -> tuple[int, int, list[WorkspaceWriteError]]:
        if not files:
            return 0, 0, []

        normalized_manifest_root = self._normalize_manifest_root(manifest_root)
        targets: dict[str, str] = {}
        for raw_path, content in files.items():
            resolved = self._resolve_manifest_file_target(
                project_root,
                raw_path,
                normalized_manifest_root,
            )
            if not resolved:
                continue
            targets[resolved] = content

        if not targets:
            return 0, 0, []

        # Ensure directories exist
        directories = {posixpath.dirname(path) for path in targets if posixpath.dirname(path)}
        for directory in sorted(directories):
            await sandbox.exec_command(
                session_id,
                "/",
                f"mkdir -p {shlex.quote(directory)}",
            )

        files_written = 0
        files_failed = 0
        errors: list[WorkspaceWriteError] = []
        for path, content in targets.items():
            result = await sandbox.file_write(path, content)
            if result.success:
                files_written += 1
            else:
                files_failed += 1
                errors.append(WorkspaceWriteError(path=path, message=result.message or "Failed to write file"))

        return files_written, files_failed, errors

    def _normalize_manifest_root(self, manifest_root: str | None) -> str | None:
        if not manifest_root:
            return None
        normalized = manifest_root.replace("\\", "/").rstrip("/")
        return posixpath.normpath(normalized)

    def _resolve_manifest_file_target(
        self,
        project_root: str,
        raw_path: str,
        manifest_root: str | None,
    ) -> str | None:
        if not raw_path:
            return None
        raw_path = raw_path.replace("\\", "/")
        normalized_path = posixpath.normpath(raw_path)
        if normalized_path.startswith("/"):
            if manifest_root and normalized_path.startswith(manifest_root.rstrip("/") + "/"):
                relative_path = normalized_path[len(manifest_root.rstrip("/")) + 1 :]
            else:
                relative_path = normalized_path.lstrip("/")
        else:
            relative_path = normalized_path

        relative_path = relative_path.lstrip("/")
        if not relative_path or relative_path == ".":
            return None
        return self._safe_join(project_root, relative_path)

    def _safe_join(self, base: str, relative_path: str) -> str:
        normalized_base = base.rstrip("/")
        joined = posixpath.normpath(posixpath.join(normalized_base, relative_path))
        if joined == normalized_base or joined.startswith(normalized_base + "/"):
            return joined
        raise ValueError("Resolved path escapes workspace root")

    def _format_env_content(self, env_vars: dict[str, str], secrets: dict[str, str]) -> str:
        if not env_vars and not secrets:
            return ""
        lines: list[str] = []
        for key, value in {**env_vars, **secrets}.items():
            lines.append(self._format_env_line(key, value))
        return "\n".join(lines) + "\n"

    def _format_env_line(self, key: str, value: str | None) -> str:
        safe_value = "" if value is None else str(value)
        needs_quotes = any(ch in safe_value for ch in [" ", "\t", "\n", '"', "'", "\\"])
        if needs_quotes:
            escaped = safe_value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
            return f'{key}="{escaped}"'
        return f"{key}={safe_value}"
