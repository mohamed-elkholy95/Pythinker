import asyncio
import io
import logging
import secrets
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from typing import TypeVar

from minio import Minio
from minio.deleteobjects import DeleteObject
from minio.error import S3Error

from app.core.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _minio_retry(
    func: Callable[..., T],
    *args: object,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    operation: str = "unknown",
) -> T:
    """Retry a synchronous MinIO SDK call with exponential backoff + jitter.

    This runs inside a thread (via ``asyncio.to_thread``), so ``time.sleep``
    is acceptable and does not block the event loop.
    """
    from app.core.prometheus_metrics import minio_operation_failures_total, minio_operation_retries_total

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args)
        except (S3Error, OSError, TimeoutError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1)) + secrets.randbelow(int(base_delay * 1000) + 1) / 1000
                logger.warning(
                    "MinIO %s failed (attempt %d/%d), retrying in %.1fs: %s",
                    operation,
                    attempt,
                    max_attempts,
                    delay,
                    exc,
                )
                minio_operation_retries_total.inc({"operation": operation})
                time.sleep(delay)
            else:
                logger.error(
                    "MinIO %s failed after %d attempts: %s",
                    operation,
                    max_attempts,
                    exc,
                )
                minio_operation_failures_total.inc({"operation": operation})
    raise last_exc  # type: ignore[misc]


class MinIOStorage:
    """MinIO S3-compatible object storage client singleton.

    Follows the same patterns as QdrantStorage and RedisStorage:
    - Singleton via @lru_cache
    - initialize() / shutdown() lifecycle
    - Graceful error handling on startup

    All I/O methods are async, delegating blocking MinIO SDK calls to a
    thread-pool via ``asyncio.to_thread`` so the event loop is never blocked.
    """

    def __init__(self):
        self._client: Minio | None = None
        self._settings = get_settings()
        self._init_lock = asyncio.Lock()

    async def ensure_initialized(self) -> None:
        """Ensure MinIO client is initialized before use."""
        await self.initialize()

    async def initialize(self) -> None:
        """Initialize MinIO client and ensure buckets exist."""
        if self._client is not None:
            return

        # Serialized startup avoids concurrent initialization races when services
        # use MinIO outside FastAPI lifespan (e.g., gateway runner).
        async with self._init_lock:
            if self._client is not None:
                return

            try:
                self._client = Minio(
                    self._settings.minio_endpoint,
                    access_key=self._settings.minio_access_key,
                    secret_key=self._settings.minio_secret_key,
                    secure=self._settings.minio_use_ssl,
                    region=self._settings.minio_region,
                )

                # Ensure all buckets exist (blocking I/O → thread)
                for bucket in [
                    self._settings.minio_bucket_name,
                    self._settings.minio_screenshots_bucket,
                    self._settings.minio_thumbnails_bucket,
                ]:
                    exists = await asyncio.to_thread(self._client.bucket_exists, bucket)
                    if not exists:
                        await asyncio.to_thread(self._client.make_bucket, bucket, location=self._settings.minio_region)
                        logger.info("Created MinIO bucket '%s'", bucket)
                    else:
                        logger.info("MinIO bucket '%s' already exists", bucket)

                    # Enable bucket versioning if configured (Phase 6E)
                    if self._settings.minio_versioning_enabled:
                        try:
                            from minio.versioningconfig import VersioningConfig

                            await asyncio.to_thread(
                                self._client.set_bucket_versioning,
                                bucket,
                                VersioningConfig(status="Enabled"),
                            )
                            logger.info("Bucket versioning enabled for '%s'", bucket)
                        except Exception as e:
                            logger.warning("Failed to enable versioning on '%s': %s", bucket, e)

                logger.info(
                    "Successfully connected to MinIO at %s",
                    self._settings.minio_endpoint,
                )
            except S3Error as e:
                self._client = None
                logger.error("Failed to initialize MinIO: %s", e)
                raise
            except Exception as e:
                self._client = None
                logger.error("Failed to connect to MinIO: %s", e)
                raise

    async def shutdown(self) -> None:
        """Shutdown MinIO client."""
        if self._client is not None:
            self._client = None
            logger.info("Disconnected from MinIO")
        get_minio_storage.cache_clear()

    @property
    def client(self) -> Minio:
        """Return initialized MinIO client."""
        if self._client is None:
            raise RuntimeError("MinIO client not initialized. Call initialize() first.")
        return self._client

    # --- Screenshot storage methods (all async via to_thread) ---

    async def store_screenshot(
        self,
        image_data: bytes,
        object_key: str,
        content_type: str = "image/jpeg",
    ) -> str:
        """Store screenshot in MinIO screenshots bucket. Returns the object key."""
        await self.ensure_initialized()
        bucket = self._settings.minio_screenshots_bucket
        await asyncio.to_thread(
            _minio_retry,
            self.client.put_object,
            bucket,
            object_key,
            io.BytesIO(image_data),
            len(image_data),
            content_type,
            max_attempts=self._settings.minio_retry_max_attempts,
            base_delay=self._settings.minio_retry_base_delay,
            operation="store_screenshot",
        )
        logger.debug("Stored screenshot: %s (%d bytes)", object_key, len(image_data))
        return object_key

    async def store_thumbnail(
        self,
        image_data: bytes,
        object_key: str,
        content_type: str = "image/webp",
    ) -> str:
        """Store thumbnail in MinIO thumbnails bucket. Returns the object key."""
        await self.ensure_initialized()
        bucket = self._settings.minio_thumbnails_bucket
        await asyncio.to_thread(
            _minio_retry,
            self.client.put_object,
            bucket,
            object_key,
            io.BytesIO(image_data),
            len(image_data),
            content_type,
            max_attempts=self._settings.minio_retry_max_attempts,
            base_delay=self._settings.minio_retry_base_delay,
            operation="store_thumbnail",
        )
        logger.debug("Stored thumbnail: %s (%d bytes)", object_key, len(image_data))
        return object_key

    async def get_screenshot(self, object_key: str) -> bytes:
        """Retrieve screenshot bytes from MinIO screenshots bucket."""
        await self.ensure_initialized()
        bucket = self._settings.minio_screenshots_bucket
        return await asyncio.to_thread(self._get_object_bytes, bucket, object_key)

    async def get_thumbnail(self, object_key: str) -> bytes:
        """Retrieve thumbnail bytes from MinIO thumbnails bucket."""
        await self.ensure_initialized()
        bucket = self._settings.minio_thumbnails_bucket
        return await asyncio.to_thread(self._get_object_bytes, bucket, object_key)

    def _get_object_bytes(self, bucket: str, object_key: str) -> bytes:
        """Synchronous helper to read object bytes (runs in thread, with retry)."""

        def _do_get() -> bytes:
            response = self.client.get_object(bucket, object_key)
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
            return data

        data = _minio_retry(
            _do_get,
            max_attempts=self._settings.minio_retry_max_attempts,
            base_delay=self._settings.minio_retry_base_delay,
            operation="get_object",
        )
        logger.debug("Retrieved object: %s/%s", bucket, object_key)
        return data

    def _get_object_range_sync(self, bucket: str, object_key: str, offset: int, length: int) -> bytes:
        """Synchronous helper to read a byte range from an object (runs in thread)."""

        def _do_range_get() -> bytes:
            response = self.client.get_object(bucket, object_key, offset=offset, length=length)
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
            return data

        return _minio_retry(
            _do_range_get,
            max_attempts=self._settings.minio_retry_max_attempts,
            base_delay=self._settings.minio_retry_base_delay,
            operation="get_object_range",
        )

    async def get_object_range(self, bucket: str, object_key: str, offset: int, length: int) -> bytes:
        """Retrieve a byte range from an object (non-blocking).

        Uses HTTP Range GET to avoid loading entire objects into memory.
        Useful for large files where only a portion is needed.
        """
        await self.ensure_initialized()
        return await asyncio.to_thread(self._get_object_range_sync, bucket, object_key, offset, length)

    async def delete_screenshots_by_session(self, session_id: str) -> int:
        """Delete all screenshots and thumbnails for a session prefix."""
        await self.ensure_initialized()
        return await asyncio.to_thread(self._delete_by_session_sync, session_id)

    def _delete_by_session_sync(self, session_id: str) -> int:
        """Synchronous helper for session deletion (runs in thread)."""
        count = 0
        for bucket in [
            self._settings.minio_screenshots_bucket,
            self._settings.minio_thumbnails_bucket,
        ]:
            objects = self.client.list_objects(bucket, prefix=f"{session_id}/")
            delete_list = [DeleteObject(obj.object_name) for obj in objects]
            if delete_list:
                errors = list(self.client.remove_objects(bucket, delete_list))
                if errors:
                    for err in errors:
                        logger.warning("Failed to delete %s: %s", err.name, err.message)
                count += len(delete_list)
        logger.debug("Deleted %d screenshot objects for session %s", count, session_id)
        return count


_minio_init_lock = threading.Lock()


@lru_cache
def get_minio_storage() -> MinIOStorage:
    """Get the MinIO storage instance (thread-safe singleton)."""
    with _minio_init_lock:
        return MinIOStorage()
