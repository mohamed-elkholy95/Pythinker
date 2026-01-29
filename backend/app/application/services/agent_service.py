from typing import AsyncGenerator, Optional, List, TYPE_CHECKING, Dict, Tuple
import logging
from datetime import datetime
from pathlib import PurePosixPath
import posixpath
import shlex
from app.domain.models.session import Session
from app.domain.repositories.session_repository import SessionRepository

from app.interfaces.schemas.session import ShellViewResponse
from app.interfaces.schemas.file import FileViewResponse
from app.interfaces.schemas.workspace import (
    WorkspaceManifest,
    WorkspaceManifestResponse,
    WorkspaceWriteError,
    GitRemoteSpec,
)
from app.domain.services.agent_domain_service import AgentDomainService
from app.domain.models.event import AgentEvent
from typing import Type
from app.domain.models.agent import Agent
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.llm import LLM
from app.domain.external.file import FileStorage
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.external.task import Task
from app.domain.utils.json_parser import JsonParser
from app.domain.models.file import FileInfo
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.models.session import AgentMode
from app.core.config import get_settings

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
        sandbox_cls: Type[Sandbox],
        task_cls: Type[Task],
        json_parser: JsonParser,
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: Optional[SearchEngine] = None,
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
        return session

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
        message: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        event_id: Optional[str] = None,
        attachments: Optional[List[dict]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        logger.info(f"Starting chat with session {session_id}: {message[:50]}...")
        # Directly use the domain service's chat method, which will check if the session exists
        async for event in self._agent_domain_service.chat(session_id, user_id, message, timestamp, event_id, attachments):
            logger.debug(f"Received event: {event}")
            yield event
        logger.info(f"Chat with session {session_id} completed")
    
    async def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[Session]:
        """Get a session by ID, ensuring it belongs to the user"""
        logger.info(f"Getting session {session_id} for user {user_id}")
        if not user_id:
            session = await self._session_repository.find_by_id(session_id)
        else:
            session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
        return session
    
    async def get_all_sessions(self, user_id: str) -> List[Session]:
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

    async def resume_session(self, session_id: str, user_id: str) -> bool:
        """Resume a paused session after user takeover, ensuring it belongs to the user"""
        logger.info(f"Resuming session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise RuntimeError("Session not found")
        result = await self._agent_domain_service.resume_session(session_id)
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
        else:
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
            return FileViewResponse(
                content=f"[Binary file: {file_path}. Download to view.]",
                file=file_path
            )

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
        session.git_remote = (
            sanitized_git_remote.model_dump(exclude={"credentials"})
            if sanitized_git_remote
            else None
        )

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

    async def get_session_files(self, session_id: str, user_id: Optional[str] = None) -> List[FileInfo]:
        """Get files for a session, ensuring it belongs to the user"""
        logger.info(f"Getting files for session {session_id} for user {user_id}")
        session = await self.get_session(session_id, user_id)
        return session.files
    
    async def get_shared_session_files(self, session_id: str) -> List[FileInfo]:
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

    async def get_shared_session(self, session_id: str) -> Optional[Session]:
        """Get a shared session by ID (no user authentication required)"""
        logger.info(f"Getting shared session {session_id}")
        session = await self._session_repository.find_by_id(session_id)
        if not session or not session.is_shared:
            logger.error(f"Shared session {session_id} not found or not shared")
            return None
        return session

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
        name: Optional[str],
        path: Optional[str],
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

    def _sanitize_git_remote(self, git_remote: Optional[GitRemoteSpec]) -> Optional[GitRemoteSpec]:
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
        manifest_root: Optional[str],
        files: Dict[str, str],
    ) -> Tuple[int, int, List[WorkspaceWriteError]]:
        if not files:
            return 0, 0, []

        normalized_manifest_root = self._normalize_manifest_root(manifest_root)
        targets: Dict[str, str] = {}
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
        directories = {posixpath.dirname(path) for path in targets.keys() if posixpath.dirname(path)}
        for directory in sorted(directories):
            await sandbox.exec_command(
                session_id,
                "/",
                f"mkdir -p {shlex.quote(directory)}",
            )

        files_written = 0
        files_failed = 0
        errors: List[WorkspaceWriteError] = []
        for path, content in targets.items():
            result = await sandbox.file_write(path, content)
            if result.success:
                files_written += 1
            else:
                files_failed += 1
                errors.append(
                    WorkspaceWriteError(path=path, message=result.message or "Failed to write file")
                )

        return files_written, files_failed, errors

    def _normalize_manifest_root(self, manifest_root: Optional[str]) -> Optional[str]:
        if not manifest_root:
            return None
        normalized = manifest_root.replace("\\", "/").rstrip("/")
        return posixpath.normpath(normalized)

    def _resolve_manifest_file_target(
        self,
        project_root: str,
        raw_path: str,
        manifest_root: Optional[str],
    ) -> Optional[str]:
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

    def _format_env_content(self, env_vars: Dict[str, str], secrets: Dict[str, str]) -> str:
        if not env_vars and not secrets:
            return ""
        lines: List[str] = []
        for key, value in {**env_vars, **secrets}.items():
            lines.append(self._format_env_line(key, value))
        return "\n".join(lines) + "\n"

    def _format_env_line(self, key: str, value: Optional[str]) -> str:
        safe_value = "" if value is None else str(value)
        needs_quotes = any(ch in safe_value for ch in [" ", "\t", "\n", "\"", "'", "\\"])
        if needs_quotes:
            escaped = (
                safe_value.replace("\\", "\\\\")
                .replace("\n", "\\n")
                .replace("\"", "\\\"")
            )
            return f'{key}="{escaped}"'
        return f"{key}={safe_value}"
