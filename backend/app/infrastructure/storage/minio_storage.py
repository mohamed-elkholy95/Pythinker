import asyncio
import io
import logging
import threading
from functools import lru_cache

from minio import Minio
from minio.deleteobjects import DeleteObject
from minio.error import S3Error

from app.core.config import get_settings

logger = logging.getLogger(__name__)


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

    async def initialize(self) -> None:
        """Initialize MinIO client and ensure buckets exist."""
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
        bucket = self._settings.minio_screenshots_bucket
        await asyncio.to_thread(
            self.client.put_object,
            bucket,
            object_key,
            io.BytesIO(image_data),
            length=len(image_data),
            content_type=content_type,
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
        bucket = self._settings.minio_thumbnails_bucket
        await asyncio.to_thread(
            self.client.put_object,
            bucket,
            object_key,
            io.BytesIO(image_data),
            length=len(image_data),
            content_type=content_type,
        )
        logger.debug("Stored thumbnail: %s (%d bytes)", object_key, len(image_data))
        return object_key

    async def get_screenshot(self, object_key: str) -> bytes:
        """Retrieve screenshot bytes from MinIO screenshots bucket."""
        bucket = self._settings.minio_screenshots_bucket
        return await asyncio.to_thread(self._get_object_bytes, bucket, object_key)

    async def get_thumbnail(self, object_key: str) -> bytes:
        """Retrieve thumbnail bytes from MinIO thumbnails bucket."""
        bucket = self._settings.minio_thumbnails_bucket
        return await asyncio.to_thread(self._get_object_bytes, bucket, object_key)

    def _get_object_bytes(self, bucket: str, object_key: str) -> bytes:
        """Synchronous helper to read object bytes (runs in thread)."""
        response = self.client.get_object(bucket, object_key)
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        logger.debug("Retrieved object: %s/%s", bucket, object_key)
        return data

    async def delete_screenshots_by_session(self, session_id: str) -> int:
        """Delete all screenshots and thumbnails for a session prefix."""
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
