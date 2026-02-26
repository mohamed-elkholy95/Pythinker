"""File synchronization between sandbox and persistent storage.

Handles downloading files from sandbox containers, uploading to
GridFS/MinIO storage, registering files with sessions, and workspace
sweeping for deliverable discovery.

Usage:
    fsm = FileSyncManager(
        agent_id=agent_id,
        session_id=session_id,
        user_id=user_id,
        sandbox=sandbox,
        file_storage=file_storage,
        session_repository=session_repository,
    )
    file_info = await fsm.sync_file_to_storage("/workspace/report.md")
    swept = await fsm.sweep_workspace_files()
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, ClassVar

import httpx

from app.domain.models.event import MessageEvent, ReportEvent
from app.domain.models.file import FileInfo

if TYPE_CHECKING:
    from app.domain.external.file import FileStorage
    from app.domain.external.sandbox import Sandbox
    from app.domain.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)

# Type alias for events that contain attachments requiring storage sync
EventWithAttachments = MessageEvent | ReportEvent

# ── File sweep constants — extensions worth delivering to users ────────
DELIVERABLE_EXTENSIONS = {
    # Documents
    ".md",
    ".txt",
    ".pdf",
    ".docx",
    ".doc",
    ".rtf",
    ".csv",
    ".tsv",
    # Code
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".scss",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".sh",
    ".bash",
    ".zsh",
    # Data
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    # Images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    # Other
    ".sql",
    ".graphql",
    ".proto",
    ".dockerfile",
    ".makefile",
}

SKIP_DIRECTORIES = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".cache",
    ".npm",
    ".local",
    ".config",
    "snap",
    ".pnpm-store",
    ".pki",
}

MAX_SYNC_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_SWEEP_FILES = 50


class FileSyncManager:
    """Manages file synchronization between sandbox and persistent storage.

    Responsibilities:
    - Download files from sandbox, upload to GridFS/MinIO
    - Retry logic for sandbox-write race conditions
    - Reverse sync (storage → sandbox) for user uploads
    - Workspace sweeping to discover and sync deliverable files
    - Event attachment syncing (concurrent batch operations)
    """

    # Extension-based MIME type fallback map
    _EXTENSION_MIME_MAP: ClassVar[dict[str, str]] = {
        ".html": "text/html",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
        ".md": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".xml": "application/xml",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
    }

    def __init__(
        self,
        *,
        agent_id: str,
        session_id: str,
        user_id: str,
        sandbox: Sandbox,
        file_storage: FileStorage,
        session_repository: SessionRepository,
    ) -> None:
        self._agent_id = agent_id
        self._session_id = session_id
        self._user_id = user_id
        self._sandbox = sandbox
        self._file_storage = file_storage
        self._session_repository = session_repository

    # ── MIME Inference ─────────────────────────────────────────────────

    def infer_content_type(self, file_path: str, existing_content_type: str | None = None) -> str | None:
        """Infer MIME type from file extension if not already known.

        Args:
            file_path: Path to file.
            existing_content_type: Already-known content type.

        Returns:
            Content type string, or None if cannot be determined.
        """
        if existing_content_type:
            return existing_content_type
        _, ext = os.path.splitext(file_path.lower())
        return self._EXTENSION_MIME_MAP.get(ext)

    # ── Sync: Sandbox → Storage ───────────────────────────────────────

    async def sync_file_to_storage(self, file_path: str, content_type: str | None = None) -> FileInfo | None:
        """Download a file from sandbox and upload to persistent storage.

        1. Validates file_path
        2. Downloads from sandbox
        3. Removes existing file (handles updates)
        4. Infers MIME type from extension if not provided
        5. Uploads to storage and registers with session

        Args:
            file_path: Path in sandbox (e.g., /home/ubuntu/report.md).
            content_type: Optional MIME type.

        Returns:
            FileInfo with valid file_id, or None on failure.
        """
        if not file_path or not file_path.strip():
            logger.warning("Agent %s: Cannot sync file with empty path", self._agent_id)
            return None

        try:
            existing_file = await self._session_repository.get_file_by_path(self._session_id, file_path)
            file_data = await self._sandbox.file_download(file_path)

            if file_data is None:
                logger.warning(
                    "Agent %s: File download returned None for '%s'",
                    self._agent_id,
                    file_path,
                )
                return None

            if file_data.getbuffer().nbytes == 0:
                logger.warning(
                    "Agent %s: File '%s' is empty (0 bytes)",
                    self._agent_id,
                    file_path,
                )

            # Remove existing file if present (handle updates)
            if existing_file and existing_file.file_id:
                logger.debug(
                    "Agent %s: Removing existing file for path '%s' (file_id=%s)",
                    self._agent_id,
                    file_path,
                    existing_file.file_id,
                )
                await self._session_repository.remove_file(self._session_id, existing_file.file_id)

            file_name = file_path.split("/")[-1] or "unnamed_file"

            resolved_content_type = self.infer_content_type(file_path, content_type)
            if resolved_content_type:
                logger.debug(
                    "Agent %s: Uploading '%s' with content_type='%s'",
                    self._agent_id,
                    file_name,
                    resolved_content_type,
                )

            file_info = await self._file_storage.upload_file(
                file_data,
                file_name,
                self._user_id,
                content_type=resolved_content_type,
            )

            if not file_info:
                logger.error(
                    "Agent %s: File storage returned None for '%s'",
                    self._agent_id,
                    file_path,
                )
                return None
            if not file_info.file_id:
                logger.error(
                    "Agent %s: Uploaded file has no file_id for '%s'",
                    self._agent_id,
                    file_path,
                )
                return None

            file_info.file_path = file_path
            await self._session_repository.add_file(self._session_id, file_info)

            logger.debug(
                "Agent %s: Successfully synced file '%s' -> file_id=%s, size=%d bytes",
                self._agent_id,
                file_path,
                file_info.file_id,
                file_data.getbuffer().nbytes,
            )
            return file_info

        except FileNotFoundError as e:
            logger.warning(
                "Agent %s: File not found in sandbox: '%s' - %s",
                self._agent_id,
                file_path,
                e,
            )
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    "Agent %s: File not found in sandbox (404): '%s'",
                    self._agent_id,
                    file_path,
                )
            else:
                logger.error(
                    "Agent %s: Failed to sync file '%s': HTTP %s",
                    self._agent_id,
                    file_path,
                    e.response.status_code,
                )
            return None
        except Exception as e:
            logger.exception(
                "Agent %s: Failed to sync file '%s': %s",
                self._agent_id,
                file_path,
                e,
            )
            return None

    async def sync_file_to_storage_with_retry(
        self,
        file_path: str,
        content_type: str | None = None,
        max_attempts: int = 3,
        initial_delay_seconds: float = 0.2,
    ) -> FileInfo | None:
        """Sync file to storage with short retries for sandbox-write race windows."""
        if max_attempts < 1:
            max_attempts = 1

        delay = initial_delay_seconds
        for attempt in range(1, max_attempts + 1):
            file_info = await self.sync_file_to_storage(file_path, content_type=content_type)
            if file_info is not None:
                return file_info

            if attempt < max_attempts:
                logger.debug(
                    "Agent %s: Retrying file sync for '%s' (attempt %s/%s after %.2fs)",
                    self._agent_id,
                    file_path,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2

        return None

    # ── Sync: Storage → Sandbox ───────────────────────────────────────

    async def sync_file_to_sandbox(self, file_id: str) -> FileInfo | None:
        """Download file from storage and upload to sandbox."""
        try:
            file_data, file_info = await self._file_storage.download_file(file_id, self._user_id)
            file_path = "/home/ubuntu/upload/" + file_info.filename
            result = await self._sandbox.file_upload(file_data, file_path)
            if result.success:
                file_info.file_path = file_path
                return file_info
        except Exception as e:
            logger.exception("Agent %s failed to sync file: %s", self._agent_id, e)
        return None

    # ── Workspace Sweeping ────────────────────────────────────────────

    async def sweep_workspace_files(self) -> list[FileInfo]:
        """Discover and sync deliverable files in the session workspace.

        Runs a find command scoped to ``/workspace/<session_id>`` and syncs
        any files not already tracked in session.files.

        Returns:
            List of newly synced FileInfo objects.
        """
        try:
            workspace_root = f"/workspace/{self._session_id}"

            prune_clauses = " -o ".join(f'-name "{d}"' for d in sorted(SKIP_DIRECTORIES))
            ext_clauses = " -o ".join(f'-name "*{ext}"' for ext in sorted(DELIVERABLE_EXTENSIONS))
            find_cmd = (
                f"find {workspace_root} "
                f"\\( {prune_clauses} \\) -prune -o "
                f"\\( -type f \\( {ext_clauses} \\) "
                f"-size -{MAX_SYNC_FILE_SIZE}c -print \\) "
                f"2>/dev/null | head -n {MAX_SWEEP_FILES}"
            )

            result = await self._sandbox.exec_command("sweep", workspace_root, find_cmd)
            if not result.success:
                logger.warning(
                    "Agent %s: File sweep find command failed: %s",
                    self._agent_id,
                    result.message,
                )
                return []

            output = (result.data or {}).get("output", "")
            if not output or not output.strip():
                logger.debug("Agent %s: File sweep found no files", self._agent_id)
                return []

            discovered_paths = [p.strip() for p in output.strip().split("\n") if p.strip()]
            discovered_paths = [p for p in discovered_paths if p.startswith(f"{workspace_root}/")]
            if not discovered_paths:
                return []

            session = await self._session_repository.find_by_id(self._session_id)
            existing_paths: set[str] = set()
            if session and session.files:
                for f in session.files:
                    if f.file_path:
                        existing_paths.add(f.file_path)

            new_paths = [p for p in discovered_paths if p not in existing_paths]
            if not new_paths:
                logger.debug(
                    "Agent %s: File sweep — all %d files already tracked",
                    self._agent_id,
                    len(discovered_paths),
                )
                return []

            logger.info(
                "Agent %s: File sweep found %d untracked files (of %d total)",
                self._agent_id,
                len(new_paths),
                len(discovered_paths),
            )

            sync_tasks = [self.sync_file_to_storage(p) for p in new_paths[:MAX_SWEEP_FILES]]
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            synced: list[FileInfo] = []
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    logger.warning(
                        "Agent %s: Failed to sweep-sync '%s': %s",
                        self._agent_id,
                        new_paths[i],
                        res,
                    )
                elif res is not None:
                    synced.append(res)

            logger.info(
                "Agent %s: File sweep synced %d/%d files",
                self._agent_id,
                len(synced),
                len(new_paths),
            )
            return synced

        except Exception as e:
            logger.exception("Agent %s: File sweep failed: %s", self._agent_id, e)
            return []

    # ── Event Attachment Syncing ──────────────────────────────────────

    async def sync_event_attachments_to_storage(self, event: EventWithAttachments) -> None:
        """Sync event attachments to storage and update the event.

        Filters invalid/missing file_path, syncs valid ones concurrently,
        and updates event.attachments with resolved FileInfo objects.
        """
        synced_attachments: list[FileInfo] = []
        event_type = event.type

        try:
            if not event.attachments:
                logger.debug(
                    "Agent %s: %s event has no attachments to sync",
                    self._agent_id,
                    event_type,
                )
                return

            valid_attachments = []
            for attachment in event.attachments:
                if attachment.file_path and attachment.file_path.strip():
                    valid_attachments.append(attachment)
                else:
                    logger.warning(
                        "Agent %s: Skipping attachment with invalid file_path: file_id=%s, filename=%s",
                        self._agent_id,
                        attachment.file_id,
                        attachment.filename,
                    )

            if not valid_attachments:
                logger.debug(
                    "Agent %s: No valid attachments to sync for %s event",
                    self._agent_id,
                    event_type,
                )
                event.attachments = []
                return

            logger.info(
                "Agent %s: Syncing %d attachments for %s event to storage",
                self._agent_id,
                len(valid_attachments),
                event_type,
            )

            sync_tasks = [
                self.sync_file_to_storage(attachment.file_path, content_type=attachment.content_type)
                for attachment in valid_attachments
            ]
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            for i, result in enumerate(results):
                file_path = valid_attachments[i].file_path
                if isinstance(result, Exception):
                    logger.warning(
                        "Agent %s: Failed to sync attachment '%s': %s",
                        self._agent_id,
                        file_path,
                        result,
                    )
                elif result is None:
                    logger.warning(
                        "Agent %s: Sync returned None for attachment '%s'",
                        self._agent_id,
                        file_path,
                    )
                elif not result.file_id:
                    logger.warning(
                        "Agent %s: Synced attachment '%s' has no file_id",
                        self._agent_id,
                        file_path,
                    )
                else:
                    synced_attachments.append(result)
                    logger.debug(
                        "Agent %s: Successfully synced attachment '%s' -> file_id=%s",
                        self._agent_id,
                        file_path,
                        result.file_id,
                    )

            logger.info(
                "Agent %s: Successfully synced %d/%d attachments for %s event",
                self._agent_id,
                len(synced_attachments),
                len(valid_attachments),
                event_type,
            )

        except Exception as e:
            logger.exception(
                "Agent %s: Unexpected error syncing attachments for %s event: %s",
                self._agent_id,
                event_type,
                e,
            )

        event.attachments = synced_attachments

    async def sync_message_attachments_to_sandbox(self, event: MessageEvent) -> None:
        """Sync message attachments from storage to sandbox."""
        attachments: list[FileInfo] = []
        try:
            if event.attachments:
                sync_tasks = [self.sync_file_to_sandbox(attachment.file_id) for attachment in event.attachments]
                results = await asyncio.gather(*sync_tasks, return_exceptions=True)

                add_file_tasks = []
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning("Sandbox sync failed: %s", result)
                    elif result:
                        attachments.append(result)
                        add_file_tasks.append(self._session_repository.add_file(self._session_id, result))

                if add_file_tasks:
                    await asyncio.gather(*add_file_tasks, return_exceptions=True)

            event.attachments = attachments
        except Exception as e:
            logger.exception(
                "Agent %s failed to sync attachments to event: %s",
                self._agent_id,
                e,
            )
