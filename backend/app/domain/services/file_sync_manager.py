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
import hashlib
import logging
import os
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from app.domain.exceptions.base import SessionNotFoundException
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

# Pattern for auto-generated exec temp files from code_execute tool.
# These are execution wrappers (exec_{hex}.{ext}) that should have been
# cleaned up but sometimes survive due to race conditions or sandbox restarts.
_EXEC_TEMP_FILE_RE = re.compile(r"^exec_[a-f0-9]{6,}\.(py|sh|js|ts|sql)$")

# Minimum symmetric basename similarity ratio for fuzzy dedup.
# Intentionally high to avoid dropping distinct deliverables.
_DEDUP_SIMILARITY_THRESHOLD = 0.90

# Minimum token overlap for fuzzy dedup (after removing quality keywords).
_DEDUP_MIN_TOKEN_JACCARD = 0.75

# Only dedup files whose stem matches one of these artifact patterns.
# Other files (code, configs, data) pass through untouched to avoid data loss.
_ARTIFACT_STEMS = re.compile(
    r"(?i)^(?:(?:final|complete|full|merged|consolidated)[-_ ]*)?"
    r"(report|analysis|summary|output|result|findings|review|notes|draft|writeup)"
)

# Basenames containing these keywords are preferred when picking a winner.
_QUALITY_KEYWORDS = ("final", "complete", "full", "merged", "consolidated")


def _pick_best(cluster_indices: list[int], basenames: list[str]) -> int:
    """Pick the best file index from a similarity cluster.

    Priority: (1) contains a quality keyword like "final", (2) longest basename
    (most descriptive — e.g. "final_research_report" over "report").
    """
    for idx in cluster_indices:
        lower = basenames[idx].lower()
        if any(kw in lower for kw in _QUALITY_KEYWORDS):
            return idx
    return max(cluster_indices, key=lambda idx: len(basenames[idx]))


def _numeric_tokens(name: str) -> set[str]:
    """Extract numeric tokens from a basename (e.g. report_q2_2026 -> {2, 2026})."""
    return set(re.findall(r"\d+", name))


def _artifact_tokens(name: str) -> set[str]:
    """Extract lowercase word tokens from basename for semantic comparison."""
    return set(re.findall(r"[a-z]+", name.lower()))


def _semantic_tokens(name: str) -> set[str]:
    """Artifact tokens with quality markers removed.

    This treats ``report`` and ``final_report`` as equivalent content while
    preserving distinctions like ``analysis_backend`` vs ``analysis_frontend``.
    """
    return {t for t in _artifact_tokens(name) if t not in _QUALITY_KEYWORDS}


def _token_jaccard(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity for token sets."""
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _symmetric_ratio(a: str, b: str) -> float:
    """Symmetric SequenceMatcher ratio.

    Python docs note ratio() can depend on argument order, so use max(a,b)/(b,a)
    to avoid directional false positives/negatives.
    """
    return max(
        SequenceMatcher(None, a, b).ratio(),
        SequenceMatcher(None, b, a).ratio(),
    )


def _should_cluster_basenames(name_a: str, name_b: str) -> bool:
    """Whether two artifact basenames should be deduplicated."""
    # Preserve distinct sequence/versioned outputs such as report_q1 vs report_q2.
    # Also protects versioned files (report_2026) from being deduped with
    # unversioned ones (report) — different numeric token sets always skip.
    if _numeric_tokens(name_a) != _numeric_tokens(name_b):
        return False

    sem_a = _semantic_tokens(name_a)
    sem_b = _semantic_tokens(name_b)

    # Strong rule: same semantic tokens (after removing quality words) => duplicate.
    if sem_a and sem_a == sem_b:
        return True

    # Fallback fuzzy rule: high character similarity + strong token overlap.
    return (
        _symmetric_ratio(name_a, name_b) >= _DEDUP_SIMILARITY_THRESHOLD
        and _token_jaccard(sem_a, sem_b) >= _DEDUP_MIN_TOKEN_JACCARD
    )


def _dedup_similar_files(paths: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Remove near-duplicate artifact filenames in the same directory.

    Only files whose basename matches ``_ARTIFACT_STEMS`` (report*, analysis*,
    etc.) are candidates for dedup.  All other files pass through untouched.

    Within each ``(directory, extension)`` group, clusters basenames with
    ``SequenceMatcher`` ratio >= threshold and keeps the best file per cluster
    (quality keywords > longest basename).

    Returns:
        A tuple of (kept_paths, dropped_pairs) where dropped_pairs is a list
        of ``(dropped_path, kept_path)`` for telemetry.
    """
    if len(paths) <= 1:
        return paths, []

    # Split into dedup candidates vs. passthrough
    candidates: list[str] = []
    passthrough: list[str] = []
    for p in paths:
        stem = os.path.splitext(os.path.basename(p))[0]
        if _ARTIFACT_STEMS.match(stem):
            candidates.append(p)
        else:
            passthrough.append(p)

    if len(candidates) <= 1:
        return passthrough + candidates, []

    # Group candidates by (directory, extension)
    groups: dict[tuple[str, str], list[str]] = {}
    for p in candidates:
        directory = os.path.dirname(p)
        _, ext = os.path.splitext(p)
        groups.setdefault((directory, ext), []).append(p)

    kept: list[str] = list(passthrough)
    dropped_pairs: list[tuple[str, str]] = []

    for group_paths in groups.values():
        if len(group_paths) <= 1:
            kept.extend(group_paths)
            continue

        used = [False] * len(group_paths)
        basenames = [os.path.splitext(os.path.basename(p))[0] for p in group_paths]

        for i in range(len(group_paths)):
            if used[i]:
                continue
            cluster = [i]
            for j in range(i + 1, len(group_paths)):
                if used[j]:
                    continue
                if _should_cluster_basenames(basenames[i], basenames[j]):
                    cluster.append(j)
                    used[j] = True
            used[i] = True

            best = _pick_best(cluster, basenames)
            kept.append(group_paths[best])
            dropped_pairs.extend((group_paths[idx], group_paths[best]) for idx in cluster if idx != best)

    return kept, dropped_pairs


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
        self._delivery_scope_id: str | None = None
        self._workspace_root: str | None = None

    def set_delivery_scope(self, scope_id: str | None, workspace_root: str | None) -> None:
        """Scope future sweeps and synced metadata to the active delivery root."""
        self._delivery_scope_id = scope_id
        self._workspace_root = workspace_root.rstrip("/") if workspace_root else None

    def _get_workspace_root(self) -> str:
        """Return the active workspace root for sweeping and file tagging."""
        return self._workspace_root or f"/workspace/{self._session_id}"

    def _augment_sync_metadata(
        self,
        file_path: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Merge delivery-scope and report metadata into synced files."""
        merged = dict(metadata or {})

        if self._delivery_scope_id and self._workspace_root:
            merged.update(
                {
                    "delivery_scope": self._delivery_scope_id,
                    "delivery_root": self._workspace_root,
                }
            )

        if self._is_report_artifact(file_path):
            merged["is_report"] = True

        return merged or None

    @staticmethod
    def _is_report_artifact(file_path: str) -> bool:
        """Identify report artifacts that should keep report-specific metadata."""
        basename = os.path.basename(file_path)
        return "/output/reports/" in file_path or basename.startswith("report-") or basename.startswith("full-report-")

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

    async def sync_file_to_storage(
        self,
        file_path: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FileInfo | None:
        """Download a file from sandbox and upload to persistent storage.

        1. Validates file_path
        2. Downloads from sandbox
        3. Removes existing file (handles updates)
        4. Infers MIME type from extension if not provided
        5. Uploads to storage and registers with session

        Args:
            file_path: Path in sandbox (e.g., /home/ubuntu/report.md).
            content_type: Optional MIME type.
            metadata: Optional metadata to preserve (e.g., is_report, title).

        Returns:
            FileInfo with valid file_id, or None on failure.
        """
        if not file_path or not file_path.strip():
            logger.warning("Agent %s: Cannot sync file with empty path", self._agent_id)
            return None

        metadata = self._augment_sync_metadata(file_path, metadata)

        try:
            file_data = await self._sandbox.file_download(file_path)

            if file_data is None:
                logger.warning(
                    "Agent %s: File download returned None for '%s'",
                    self._agent_id,
                    file_path,
                )
                return None

            try:
                existing_file = await self._session_repository.get_file_by_path(self._session_id, file_path)
            except SessionNotFoundException:
                logger.info(
                    "Agent %s: Session %s no longer exists, skipping sync for '%s'",
                    self._agent_id,
                    self._session_id,
                    file_path,
                )
                return None

            new_size = file_data.getbuffer().nbytes
            if new_size == 0:
                logger.error(
                    "Agent %s: Rejecting upload for empty file '%s' (0 bytes)",
                    self._agent_id,
                    file_path,
                )
                return None

            # Content-hash dedup: skip re-upload when content is unchanged
            content_md5 = hashlib.md5(file_data.getbuffer()).hexdigest()  # noqa: S324
            if existing_file and existing_file.file_id and existing_file.metadata:
                existing_md5 = existing_file.metadata.get("content_md5")
                existing_size = existing_file.size
                if existing_md5 == content_md5 and existing_size == new_size:
                    logger.debug(
                        "Agent %s: File '%s' unchanged (md5=%s, size=%d), skipping re-upload",
                        self._agent_id,
                        file_path,
                        content_md5,
                        new_size,
                    )
                    # Merge any new metadata into existing file
                    if metadata:
                        existing_file.metadata = {**(existing_file.metadata or {}), **metadata}
                        try:
                            await self._session_repository.add_file(self._session_id, existing_file)
                        except SessionNotFoundException:
                            logger.info(
                                "Agent %s: Session %s disappeared while updating metadata for '%s'",
                                self._agent_id,
                                self._session_id,
                                file_path,
                            )
                            return None
                    return existing_file

            # Remove existing file if present (handle updates)
            if existing_file and existing_file.file_id:
                logger.debug(
                    "Agent %s: Removing existing file for path '%s' (file_id=%s)",
                    self._agent_id,
                    file_path,
                    existing_file.file_id,
                )
                try:
                    await self._session_repository.remove_file(self._session_id, existing_file.file_id)
                except SessionNotFoundException:
                    logger.info(
                        "Agent %s: Session %s disappeared before replacing '%s'",
                        self._agent_id,
                        self._session_id,
                        file_path,
                    )
                    return None

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
                metadata=metadata,
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
            file_info.size = new_size
            # Store content hash for future dedup checks
            file_info.metadata = {
                **(file_info.metadata or {}),
                **(metadata or {}),
                "content_md5": content_md5,
            }
            try:
                await self._session_repository.add_file(self._session_id, file_info)
            except SessionNotFoundException:
                logger.info(
                    "Agent %s: Session %s disappeared after upload for '%s', deleting orphaned file_id=%s",
                    self._agent_id,
                    self._session_id,
                    file_path,
                    file_info.file_id,
                )
                try:
                    await self._file_storage.delete_file(file_info.file_id, self._user_id)
                except Exception:
                    logger.debug(
                        "Agent %s: Failed to delete orphaned file '%s' after session loss",
                        self._agent_id,
                        file_info.file_id,
                        exc_info=True,
                    )
                return None

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
        metadata: dict[str, Any] | None = None,
        max_attempts: int = 3,
        initial_delay_seconds: float = 0.2,
    ) -> FileInfo | None:
        """Sync file to storage with short retries for sandbox-write race windows."""
        if max_attempts < 1:
            max_attempts = 1

        delay = initial_delay_seconds
        for attempt in range(1, max_attempts + 1):
            file_info = await self.sync_file_to_storage(file_path, content_type=content_type, metadata=metadata)
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
            workspace_root = self._get_workspace_root()

            # Check if workspace directory exists before running find.
            # The sweep can fire before a session's workspace has been bootstrapped;
            # running find on a non-existent dir triggers auto-creation in the sandbox
            # shell service, which is wasteful and pollutes logs.
            dir_check = await self._sandbox.exec_command(
                "sweep_check", workspace_root, f"test -d {workspace_root} && echo exists"
            )
            dir_exists = (dir_check.data or {}).get("output", "").strip() == "exists"
            if not dir_exists:
                logger.debug(
                    "Agent %s: Workspace %s does not exist yet, skipping sweep",
                    self._agent_id,
                    workspace_root,
                )
                return []

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

            # Filter out orphaned exec temp files (exec_{hex}.py etc.)
            pre_filter_count = len(discovered_paths)
            discovered_paths = [p for p in discovered_paths if not _EXEC_TEMP_FILE_RE.match(os.path.basename(p))]
            if len(discovered_paths) < pre_filter_count:
                logger.debug(
                    "Agent %s: Filtered %d exec temp files from sweep",
                    self._agent_id,
                    pre_filter_count - len(discovered_paths),
                )

            if not discovered_paths:
                return []

            session = await self._session_repository.find_by_id_with_files(self._session_id)
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

            # Deduplicate similar artifact filenames in the same directory.
            # Only targets known artifact patterns (report*, analysis*, etc.)
            # to avoid accidentally dropping unrelated deliverables.
            # Gated by feature_sweep_dedup_enabled (default True).
            from app.core.config import get_settings

            pre_dedup_count = len(new_paths)
            dropped_pairs: list[tuple[str, str]] = []
            if getattr(get_settings(), "feature_sweep_dedup_enabled", True):
                new_paths, dropped_pairs = _dedup_similar_files(new_paths)
            if dropped_pairs:
                for dropped, kept_as in dropped_pairs:
                    logger.info(
                        "Agent %s: Dedup dropped '%s' (kept '%s')",
                        self._agent_id,
                        os.path.basename(dropped),
                        os.path.basename(kept_as),
                    )
                logger.info(
                    "Agent %s: Deduped %d similar artifact files (kept %d of %d)",
                    self._agent_id,
                    pre_dedup_count - len(new_paths),
                    len(new_paths),
                    pre_dedup_count,
                )

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
            already_uploaded = []
            for attachment in event.attachments:
                if attachment.file_path and attachment.file_path.strip():
                    if attachment.file_id:
                        # Already uploaded to storage (e.g., PDF generated in memory).
                        # Preserve as-is — no need to re-download from sandbox.
                        already_uploaded.append(attachment)
                    else:
                        valid_attachments.append(attachment)
                else:
                    logger.warning(
                        "Agent %s: Skipping attachment with invalid file_path: file_id=%s, filename=%s",
                        self._agent_id,
                        attachment.file_id,
                        attachment.filename,
                    )

            if not valid_attachments and not already_uploaded:
                logger.debug(
                    "Agent %s: No valid attachments to sync for %s event",
                    self._agent_id,
                    event_type,
                )
                event.attachments = []
                return

            if already_uploaded:
                logger.info(
                    "Agent %s: Preserving %d already-uploaded attachments for %s event",
                    self._agent_id,
                    len(already_uploaded),
                    event_type,
                )
                synced_attachments.extend(already_uploaded)

            if valid_attachments:
                logger.info(
                    "Agent %s: Syncing %d attachments for %s event to storage",
                    self._agent_id,
                    len(valid_attachments),
                    event_type,
                )

                sync_tasks = [
                    self.sync_file_to_storage(
                        attachment.file_path,
                        content_type=attachment.content_type,
                        metadata=attachment.metadata,
                    )
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
                "Agent %s: Total attachments for %s event: %d synced + %d pre-uploaded",
                self._agent_id,
                event_type,
                len(synced_attachments) - len(already_uploaded),
                len(already_uploaded),
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
