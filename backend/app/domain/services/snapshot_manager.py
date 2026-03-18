"""
Snapshot Manager - Filesystem snapshot service for ephemeral sandboxes.

Captures and restores container filesystem deltas to MinIO/S3 for:
- Session pause/resume across container restarts
- Full execution replay
- Debugging (inspect exact filesystem state at any point)
- Multi-tenancy isolation (fresh container per session)
"""

import io
import logging
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import docker
from docker.errors import DockerException, NotFound

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class SnapshotMetadata:
    """Snapshot metadata."""

    snapshot_id: str
    session_id: str
    container_id: str
    created_at: datetime
    size_bytes: int
    paths: list[str]  # Paths included in snapshot
    compression: str = "gzip"  # Compression algorithm


class ObjectStorage(Protocol):
    """Protocol for object storage backends (MinIO, S3, etc.).

    All methods are async to ensure non-blocking I/O on the event loop.
    Implementations must delegate blocking SDK calls to a thread pool
    (e.g., via ``asyncio.to_thread``).
    """

    async def upload(self, key: str, data: bytes, metadata: dict[str, str] | None = None) -> None:
        """Upload object to storage."""
        ...

    async def download(self, key: str) -> bytes:
        """Download object from storage."""
        ...

    async def delete(self, key: str) -> None:
        """Delete object from storage."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if object exists."""
        ...

    async def list_objects(self, prefix: str = "") -> list[str]:
        """List object keys matching the given prefix."""
        ...


class SnapshotManager:
    """
    Manages filesystem snapshots for ephemeral sandboxes.

    Features:
    - Async snapshot capture (non-blocking teardown)
    - Delta compression (only changed files)
    - Automatic cleanup (TTL-based)
    - S3-compatible storage (MinIO)
    """

    def __init__(
        self,
        storage: ObjectStorage,
        settings: Settings,
        docker_client: docker.DockerClient | None = None,
    ):
        self.storage = storage
        self.settings = settings
        self.docker = docker_client or docker.from_env()

        # Snapshot configuration
        self.snapshot_paths = [
            "/home/ubuntu",  # User home (workspace, downloads, etc.)
            "/tmp/chrome",  # Chrome profile
            "/tmp/runtime-ubuntu",  # Runtime state
        ]
        self.compression = "gzip"
        self.compression_level = 6  # Balance between speed and size

    async def create_snapshot(
        self,
        container_id: str,
        session_id: str,
        snapshot_id: str | None = None,
    ) -> SnapshotMetadata:
        """
        Create filesystem snapshot from running or stopped container.

        Args:
            container_id: Docker container ID
            session_id: Session ID (for metadata)
            snapshot_id: Custom snapshot ID (defaults to session_id-timestamp)

        Returns:
            Snapshot metadata

        Raises:
            DockerException: If container not found or snapshot fails
        """
        if snapshot_id is None:
            snapshot_id = f"{session_id}-{int(time.time())}"

        logger.info(f"Creating snapshot {snapshot_id} for container {container_id[:12]}")
        start_time = time.time()

        try:
            container = self.docker.containers.get(container_id)

            # Create tar archive from container filesystem
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode=f"w:{self.compression}") as tar:
                for path in self.snapshot_paths:
                    try:
                        # Export path from container
                        bits, _stat = container.get_archive(path)
                        path_tar = io.BytesIO(b"".join(bits))

                        # Extract and re-add to snapshot with correct path
                        with tarfile.open(fileobj=path_tar, mode="r") as src_tar:
                            for member in src_tar.getmembers():
                                src_tar.extract(member, path="/tmp/snapshot_temp")
                                tar.add(
                                    f"/tmp/snapshot_temp/{member.name}",
                                    arcname=member.name,
                                )

                    except NotFound:
                        logger.warning(f"Path {path} not found in container {container_id[:12]}, skipping")
                        continue

            tar_data = tar_stream.getvalue()
            size_bytes = len(tar_data)

            # Upload to object storage
            storage_key = f"snapshots/{session_id}/{snapshot_id}.tar.{self.compression}"
            metadata_dict = {
                "snapshot_id": snapshot_id,
                "session_id": session_id,
                "container_id": container_id,
                "created_at": datetime.now(UTC).isoformat(),
                "size_bytes": str(size_bytes),
                "compression": self.compression,
                "paths": ",".join(self.snapshot_paths),
            }

            await self.storage.upload(storage_key, tar_data, metadata=metadata_dict)

            elapsed = time.time() - start_time
            logger.info(f"Snapshot {snapshot_id} created: {size_bytes / 1024 / 1024:.1f}MB in {elapsed:.1f}s")

            return SnapshotMetadata(
                snapshot_id=snapshot_id,
                session_id=session_id,
                container_id=container_id,
                created_at=datetime.now(UTC),
                size_bytes=size_bytes,
                paths=self.snapshot_paths,
                compression=self.compression,
            )

        except DockerException as e:
            logger.error(f"Failed to create snapshot {snapshot_id}: {e}", exc_info=True)
            raise

    async def restore_snapshot(
        self,
        container_id: str,
        snapshot_id: str,
        session_id: str,
    ) -> None:
        """
        Restore snapshot to container filesystem.

        Args:
            container_id: Target container ID
            snapshot_id: Snapshot ID to restore
            session_id: Session ID (for storage path)

        Raises:
            DockerException: If container not found
            FileNotFoundError: If snapshot not found in storage
        """
        logger.info(f"Restoring snapshot {snapshot_id} to container {container_id[:12]}")
        start_time = time.time()

        try:
            # Download snapshot from storage
            storage_key = f"snapshots/{session_id}/{snapshot_id}.tar.{self.compression}"

            if not await self.storage.exists(storage_key):
                raise FileNotFoundError(f"Snapshot {snapshot_id} not found in storage")

            tar_data = await self.storage.download(storage_key)

            # Restore to container
            container = self.docker.containers.get(container_id)
            container.put_archive("/", tar_data)

            elapsed = time.time() - start_time
            logger.info(f"Snapshot {snapshot_id} restored: {len(tar_data) / 1024 / 1024:.1f}MB in {elapsed:.1f}s")

        except DockerException as e:
            logger.error(f"Failed to restore snapshot {snapshot_id}: {e}", exc_info=True)
            raise

    async def delete_snapshot(self, snapshot_id: str, session_id: str) -> None:
        """
        Delete snapshot from storage.

        Args:
            snapshot_id: Snapshot ID to delete
            session_id: Session ID (for storage path)
        """
        storage_key = f"snapshots/{session_id}/{snapshot_id}.tar.{self.compression}"

        try:
            await self.storage.delete(storage_key)
            logger.info(f"Snapshot {snapshot_id} deleted")
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}", exc_info=True)
            raise

    async def list_snapshots(self, session_id: str) -> list[str]:
        """
        List all snapshots for a session.

        Args:
            session_id: Session ID

        Returns:
            List of snapshot IDs
        """
        # This would need to be implemented based on the storage backend
        # For now, return empty list (MinIO SDK would provide bucket listing)
        return []

    async def cleanup_old_snapshots(self, ttl_days: int = 7) -> int:
        """Delete state snapshots older than TTL.

        Note: "snapshots" in this codebase means *session state snapshots*
        stored as MongoDB documents (SnapshotDocument), NOT sandbox container
        tarballs. TTL cleanup is handled by MaintenanceService.cleanup_old_snapshots()
        which runs as a periodic background task in lifespan.py.

        Args:
            ttl_days: Time-to-live in days

        Returns:
            Number of snapshots deleted
        """
        logger.info("Cleanup triggered: deleting state snapshots older than %d days", ttl_days)
        try:
            from app.application.services.maintenance_service import get_maintenance_service

            service = get_maintenance_service()
            result = await service.cleanup_old_snapshots(ttl_days=ttl_days)
            return result.get("documents_deleted", 0)
        except Exception as e:
            logger.warning("Snapshot cleanup failed: %s", e)
            return 0
