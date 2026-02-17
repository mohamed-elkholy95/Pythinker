"""
MinIO Object Storage Adapter - S3-compatible storage for snapshots.

Implements ObjectStorage protocol for SnapshotManager.

All I/O methods are async, delegating blocking MinIO SDK calls to
a thread pool via ``asyncio.to_thread`` so the event loop is never blocked.
"""

import asyncio
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


class MinIOStorage:
    """
    MinIO storage adapter for sandbox snapshots.

    Uses MinIO's S3-compatible API for object storage.
    All public async methods delegate blocking SDK calls to
    ``asyncio.to_thread`` to avoid blocking the event loop.

    Lifecycle:
        1. Construct with ``MinIOStorage(...)`` -- creates the Minio client
           but does **not** perform any network I/O.
        2. Call ``await initialize()`` to ensure the bucket exists (async-safe).
        3. Use ``upload``, ``download``, ``delete``, ``exists``, ``list_objects``.
        4. Call ``await shutdown()`` for clean teardown.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "sandbox-snapshots",
        secure: bool = False,
    ):
        """
        Initialize MinIO storage configuration (no network I/O).

        The Minio SDK client is created eagerly (it does not connect on
        construction), but bucket verification is deferred to ``initialize()``.

        Args:
            endpoint: MinIO endpoint (e.g., "localhost:9000")
            access_key: Access key ID
            secret_key: Secret access key
            bucket_name: Bucket name for snapshots
            secure: Use HTTPS (default: False for local dev)
        """
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.secure = secure
        self._client = None
        self._initialized = False

        # Lazy import to avoid dependency errors if MinIO not installed
        try:
            from minio import Minio

            self._client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )
        except ImportError:
            logger.warning("minio package not installed, snapshot storage unavailable")
        except Exception as e:
            logger.error("Failed to create MinIO client: %s", e, exc_info=True)

    @property
    def client(self):
        """Return the underlying Minio client, or raise if unavailable."""
        if self._client is None:
            raise RuntimeError("MinIO client not initialized")
        return self._client

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Ensure the snapshot bucket exists (async-safe).

        Must be called once after construction before any I/O operations.
        Idempotent -- safe to call multiple times.
        """
        if self._initialized:
            return

        if self._client is None:
            logger.warning("MinIO client unavailable, skipping initialization")
            return

        try:
            exists = await asyncio.to_thread(self._client.bucket_exists, self.bucket_name)
            if not exists:
                await asyncio.to_thread(self._client.make_bucket, self.bucket_name)
                logger.info("Created MinIO bucket: %s", self.bucket_name)
            else:
                logger.info("MinIO bucket '%s' already exists", self.bucket_name)
            self._initialized = True
        except Exception as e:
            logger.error(
                "Failed to initialize MinIO bucket '%s': %s",
                self.bucket_name,
                e,
                exc_info=True,
            )
            raise

    async def shutdown(self) -> None:
        """Clean shutdown -- release resources."""
        self._client = None
        self._initialized = False
        logger.info("MinIO snapshot storage shut down")

    # ------------------------------------------------------------------
    # Synchronous helpers (run inside thread pool)
    # ------------------------------------------------------------------

    def _upload_sync(
        self,
        key: str,
        data: bytes,
        metadata: dict[str, str] | None,
    ) -> None:
        """Synchronous upload -- runs in a worker thread."""
        data_stream = BytesIO(data)
        self.client.put_object(
            bucket_name=self.bucket_name,
            object_name=key,
            data=data_stream,
            length=len(data),
            metadata=metadata or {},
        )

    def _download_sync(self, key: str) -> bytes:
        """Synchronous download -- runs in a worker thread."""
        response = self.client.get_object(self.bucket_name, key)
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        return data

    def _delete_sync(self, key: str) -> None:
        """Synchronous delete -- runs in a worker thread."""
        self.client.remove_object(self.bucket_name, key)

    def _exists_sync(self, key: str) -> bool:
        """Synchronous existence check -- runs in a worker thread."""
        try:
            self.client.stat_object(self.bucket_name, key)
            return True
        except Exception:
            return False

    def _list_objects_sync(self, prefix: str) -> list[str]:
        """Synchronous object listing -- runs in a worker thread."""
        objects = self.client.list_objects(self.bucket_name, prefix=prefix)
        return [obj.object_name for obj in objects]

    # ------------------------------------------------------------------
    # Async public API (ObjectStorage protocol)
    # ------------------------------------------------------------------

    async def upload(
        self,
        key: str,
        data: bytes,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """
        Upload object to MinIO (non-blocking).

        Args:
            key: Object key (path)
            data: Object data
            metadata: Optional metadata dict
        """
        if self._client is None:
            raise RuntimeError("MinIO client not initialized")

        try:
            await asyncio.to_thread(self._upload_sync, key, data, metadata)
            logger.debug("Uploaded %.1fMB to %s", len(data) / 1024 / 1024, key)
        except Exception as e:
            logger.error("Failed to upload %s: %s", key, e, exc_info=True)
            raise

    async def download(self, key: str) -> bytes:
        """
        Download object from MinIO (non-blocking).

        Args:
            key: Object key (path)

        Returns:
            Object data as bytes
        """
        if self._client is None:
            raise RuntimeError("MinIO client not initialized")

        try:
            data = await asyncio.to_thread(self._download_sync, key)
            logger.debug("Downloaded %.1fMB from %s", len(data) / 1024 / 1024, key)
            return data
        except Exception as e:
            logger.error("Failed to download %s: %s", key, e, exc_info=True)
            raise

    async def delete(self, key: str) -> None:
        """
        Delete object from MinIO (non-blocking).

        Args:
            key: Object key (path)
        """
        if self._client is None:
            raise RuntimeError("MinIO client not initialized")

        try:
            await asyncio.to_thread(self._delete_sync, key)
            logger.debug("Deleted %s", key)
        except Exception as e:
            logger.error("Failed to delete %s: %s", key, e, exc_info=True)
            raise

    async def exists(self, key: str) -> bool:
        """
        Check if object exists in MinIO (non-blocking).

        Args:
            key: Object key (path)

        Returns:
            True if object exists, False otherwise
        """
        if self._client is None:
            raise RuntimeError("MinIO client not initialized")

        return await asyncio.to_thread(self._exists_sync, key)

    async def list_objects(self, prefix: str = "") -> list[str]:
        """
        List objects with prefix (non-blocking).

        Args:
            prefix: Object key prefix

        Returns:
            List of object keys
        """
        if self._client is None:
            raise RuntimeError("MinIO client not initialized")

        try:
            return await asyncio.to_thread(self._list_objects_sync, prefix)
        except Exception as e:
            logger.error("Failed to list objects with prefix %s: %s", prefix, e)
            return []
