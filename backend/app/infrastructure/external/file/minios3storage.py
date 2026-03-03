import asyncio
import io
import logging
import uuid
from datetime import UTC, datetime, timedelta
from inspect import isawaitable
from typing import Any, BinaryIO, ClassVar

from minio.error import S3Error

from app.core.config import get_settings
from app.domain.external.file import FileStorage
from app.domain.models.file import FileInfo
from app.infrastructure.storage.minio_storage import MinIOStorage, _minio_retry

logger = logging.getLogger(__name__)


class MinIOFileStorage(FileStorage):
    """MinIO S3-based file storage implementation.

    Object key format: {user_id}/{uuid}_{filename}
    User access control via S3 object metadata (x-amz-meta-user-id).

    All I/O methods delegate blocking MinIO SDK calls to a thread pool
    via ``asyncio.to_thread`` so the event loop is never blocked.
    """

    _RESERVED_S3_HEADERS: ClassVar[set[str]] = {
        "authorization",
        "content-length",
        "content-type",
        "host",
        "x-amz-content-sha256",
        "x-amz-date",
    }

    def __init__(self, minio_storage: MinIOStorage):
        self._minio = minio_storage
        self._settings = get_settings()

    async def _ensure_minio_ready(self) -> None:
        """Ensure MinIO client is initialized before any storage operation."""
        try:
            _ = self._minio.client
            return
        except Exception:
            init = getattr(self._minio, "initialize", None)
            if init is None:
                raise
            result = init()
            if isawaitable(result):
                await result

    @property
    def _bucket(self) -> str:
        return self._settings.minio_bucket_name

    def _make_object_key(self, user_id: str, filename: str) -> str:
        """Generate a unique object key namespaced by user."""
        unique_id = uuid.uuid4().hex[:12]
        safe_filename = filename.replace("/", "_").replace("\\", "_")
        return f"{user_id}/{unique_id}_{safe_filename}"

    def _normalize_metadata_key(self, key: str) -> str | None:
        """Normalize metadata key to avoid collisions with signed S3 headers."""
        normalized = key.strip()
        if not normalized:
            return None

        lowered = normalized.lower()
        if lowered.startswith("x-amz-meta-"):
            normalized = normalized[11:]
            lowered = normalized.lower()

        if lowered in self._RESERVED_S3_HEADERS:
            logger.warning("Ignoring reserved S3 metadata key '%s' to prevent header-signature conflicts", key)
            return None

        return normalized

    @staticmethod
    def _sanitize_metadata_value(value: str) -> str:
        """Strip non-ASCII characters from S3 metadata values.

        MinIO (and S3) metadata is transmitted via HTTP headers which only
        support US-ASCII visible characters.  Emoji and other Unicode code
        points cause ``ValueError`` deep in the SDK signing layer.
        """
        return value.encode("ascii", errors="ignore").decode("ascii")

    # ------------------------------------------------------------------
    # Synchronous helpers (run inside thread pool via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _download_file_sync(
        self, bucket: str, file_id: str
    ) -> tuple[io.BytesIO, dict[str, str], str | None, int | None, datetime | None]:
        """Synchronous download with retry -- returns raw data + stat info."""
        client = self._minio.client

        stat = _minio_retry(
            client.stat_object,
            bucket,
            file_id,
            max_attempts=self._settings.minio_retry_max_attempts,
            base_delay=self._settings.minio_retry_base_delay,
            operation="download_stat",
        )
        obj_metadata = stat.metadata or {}

        def _do_get() -> io.BytesIO:
            response = client.get_object(bucket, file_id)
            try:
                return io.BytesIO(response.read())
            finally:
                response.close()
                response.release_conn()

        data = _minio_retry(
            _do_get,
            max_attempts=self._settings.minio_retry_max_attempts,
            base_delay=self._settings.minio_retry_base_delay,
            operation="download_get",
        )
        return data, dict(obj_metadata), stat.content_type, stat.size, stat.last_modified

    def _delete_file_sync(self, bucket: str, file_id: str) -> dict[str, str]:
        """Synchronous stat for ownership check (with retry)."""
        client = self._minio.client

        stat = _minio_retry(
            client.stat_object,
            bucket,
            file_id,
            max_attempts=self._settings.minio_retry_max_attempts,
            base_delay=self._settings.minio_retry_base_delay,
            operation="delete_stat",
        )
        obj_metadata = stat.metadata or {}
        return dict(obj_metadata)

    def _remove_object_sync(self, bucket: str, file_id: str) -> None:
        """Synchronous object removal -- runs in thread pool."""
        self._minio.client.remove_object(bucket, file_id)

    def _stat_object_sync(
        self, bucket: str, file_id: str
    ) -> tuple[dict[str, str], str | None, int | None, datetime | None]:
        """Synchronous stat -- returns metadata, content_type, size, last_modified."""
        client = self._minio.client
        stat = client.stat_object(bucket, file_id)
        obj_metadata = stat.metadata or {}
        return dict(obj_metadata), stat.content_type, stat.size, stat.last_modified

    def _presigned_put_sync(self, bucket: str, object_key: str, expiry: timedelta) -> str:
        """Synchronous presigned PUT URL generation -- runs in thread pool."""
        return self._minio.client.presigned_put_object(bucket, object_key, expires=expiry)

    def _presigned_get_sync(self, bucket: str, file_id: str, expiry: timedelta) -> str:
        """Synchronous presigned GET URL generation -- runs in thread pool."""
        return self._minio.client.presigned_get_object(bucket, file_id, expires=expiry)

    # ------------------------------------------------------------------
    # Async public API (FileStorage protocol)
    # ------------------------------------------------------------------

    async def upload_file(
        self,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FileInfo:
        """Upload file to MinIO (non-blocking)."""
        try:
            await self._ensure_minio_ready()
            client = self._minio.client
            object_key = self._make_object_key(user_id, filename)

            # Build S3 metadata (all values must be US-ASCII strings per RFC 7230)
            s3_metadata = {
                "user-id": user_id,
                "original-filename": self._sanitize_metadata_value(filename),
            }
            if metadata:
                for k, v in metadata.items():
                    normalized_key = self._normalize_metadata_key(str(k))
                    if normalized_key:
                        s3_metadata[normalized_key] = self._sanitize_metadata_value(str(v))

            # Determine content length by seeking
            file_data.seek(0, 2)  # seek to end
            content_length = file_data.tell()
            file_data.seek(0)  # seek back to start

            # Use multipart upload for large files (SDK auto-chunks when length=-1)
            threshold = self._settings.minio_multipart_threshold_bytes
            effective_content_type = content_type or "application/octet-stream"
            if content_length > threshold:
                part_size = self._settings.minio_multipart_part_size

                def _do_multipart_upload() -> object:
                    file_data.seek(0)
                    return client.put_object(
                        self._bucket,
                        object_key,
                        file_data,
                        length=-1,
                        content_type=effective_content_type,
                        metadata=s3_metadata,
                        part_size=part_size,
                    )

                result = await asyncio.to_thread(
                    _minio_retry,
                    _do_multipart_upload,
                    max_attempts=self._settings.minio_retry_max_attempts,
                    base_delay=self._settings.minio_retry_base_delay,
                    operation="upload_multipart",
                )
            else:

                def _do_upload() -> object:
                    file_data.seek(0)
                    return client.put_object(
                        self._bucket,
                        object_key,
                        file_data,
                        length=content_length,
                        content_type=effective_content_type,
                        metadata=s3_metadata,
                    )

                result = await asyncio.to_thread(
                    _minio_retry,
                    _do_upload,
                    max_attempts=self._settings.minio_retry_max_attempts,
                    base_delay=self._settings.minio_retry_base_delay,
                    operation="upload_file",
                )

            logger.info(
                "File uploaded to MinIO: %s (key: %s, etag: %s) for user %s",
                filename,
                object_key,
                result.etag,
                user_id,
            )

            return FileInfo(
                file_id=object_key,
                filename=filename,
                size=content_length,
                content_type=content_type,
                upload_date=datetime.now(UTC),
                metadata=s3_metadata,
                user_id=user_id,
            )

        except Exception as e:
            logger.error("Failed to upload file %s for user %s: %s", filename, user_id, e)
            raise

    async def download_file(self, file_id: str, user_id: str | None = None) -> tuple[BinaryIO, FileInfo]:
        """Download file from MinIO by object key (non-blocking)."""
        try:
            await self._ensure_minio_ready()
            # Run all blocking I/O in thread pool
            data, obj_metadata, content_type, size, last_modified = await asyncio.to_thread(
                self._download_file_sync, self._bucket, file_id
            )

            # Check user ownership (non-blocking, pure logic)
            file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
            if user_id is not None and file_user_id and file_user_id != user_id:
                raise PermissionError(f"Access denied: file {file_id} does not belong to user {user_id}")

            file_info = FileInfo(
                file_id=file_id,
                filename=obj_metadata.get("x-amz-meta-original-filename", file_id.split("/")[-1]),
                content_type=content_type,
                size=size,
                upload_date=last_modified,
                metadata=obj_metadata,
                user_id=file_user_id,
            )

            return data, file_info

        except (FileNotFoundError, PermissionError):
            raise
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {file_id}") from e
            logger.error("Failed to download file %s for user %s: %s", file_id, user_id, e)
            raise
        except Exception as e:
            logger.error("Failed to download file %s for user %s: %s", file_id, user_id, e)
            raise

    async def delete_file(self, file_id: str, user_id: str) -> bool:
        """Delete file from MinIO (non-blocking)."""
        try:
            await self._ensure_minio_ready()
            # Stat object in thread pool to check ownership
            obj_metadata = await asyncio.to_thread(self._delete_file_sync, self._bucket, file_id)
            file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
            if file_user_id and file_user_id != user_id:
                logger.warning("Delete access denied: file %s does not belong to user %s", file_id, user_id)
                return False

            # Remove object in thread pool
            await asyncio.to_thread(self._remove_object_sync, self._bucket, file_id)
            logger.info("File deleted from MinIO: %s by user %s", file_id, user_id)
            return True

        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error("Failed to delete file %s for user %s: %s", file_id, user_id, e)
            return False
        except Exception as e:
            logger.error("Failed to delete file %s for user %s: %s", file_id, user_id, e)
            return False

    async def get_file_info(self, file_id: str, user_id: str | None = None) -> FileInfo | None:
        """Get file metadata from MinIO (non-blocking)."""
        try:
            await self._ensure_minio_ready()
            # Stat object in thread pool
            obj_metadata, content_type, size, last_modified = await asyncio.to_thread(
                self._stat_object_sync, self._bucket, file_id
            )

            # Check ownership (non-blocking, pure logic)
            file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
            if user_id is not None and file_user_id and file_user_id != user_id:
                logger.warning("Access denied: file %s does not belong to user %s", file_id, user_id)
                return None

            return FileInfo(
                file_id=file_id,
                filename=obj_metadata.get("x-amz-meta-original-filename", file_id.split("/")[-1]),
                content_type=content_type,
                size=size,
                upload_date=last_modified,
                metadata=obj_metadata,
                user_id=file_user_id,
            )

        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            logger.error("Failed to get file info %s for user %s: %s", file_id, user_id, e)
            return None
        except Exception as e:
            logger.error("Failed to get file info %s for user %s: %s", file_id, user_id, e)
            return None

    async def generate_upload_url(
        self, filename: str, user_id: str, content_type: str | None = None
    ) -> tuple[str, str]:
        """Generate a presigned PUT URL for direct upload to MinIO (non-blocking)."""
        try:
            await self._ensure_minio_ready()
            object_key = self._make_object_key(user_id, filename)
            expiry = timedelta(seconds=self._settings.minio_presigned_expiry_seconds)

            url = await asyncio.to_thread(self._presigned_put_sync, self._bucket, object_key, expiry)

            logger.info("Generated presigned upload URL for %s (key: %s)", filename, object_key)
            return url, object_key

        except Exception as e:
            logger.error("Failed to generate upload URL for %s: %s", filename, e)
            raise

    async def generate_download_url(self, file_id: str, user_id: str | None = None) -> str:
        """Generate a presigned GET URL for direct download from MinIO (non-blocking)."""
        try:
            await self._ensure_minio_ready()
            # Verify ownership if user_id provided (blocking I/O in thread pool)
            if user_id is not None:
                obj_metadata, _, _, _ = await asyncio.to_thread(self._stat_object_sync, self._bucket, file_id)
                file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
                if file_user_id and file_user_id != user_id:
                    raise PermissionError(f"Access denied: file {file_id} does not belong to user {user_id}")

            expiry = timedelta(seconds=self._settings.minio_presigned_expiry_seconds)

            url = await asyncio.to_thread(self._presigned_get_sync, self._bucket, file_id, expiry)

            logger.info("Generated presigned download URL for %s", file_id)
            return url

        except PermissionError:
            raise
        except Exception as e:
            logger.error("Failed to generate download URL for %s: %s", file_id, e)
            raise

    async def download_file_range(self, file_id: str, offset: int, length: int) -> bytes:
        """Download a byte range from a file (non-blocking).

        Uses HTTP Range GET to avoid loading entire objects into memory.
        Useful for streaming large files or resumable downloads.
        """
        from app.infrastructure.storage.minio_storage import get_minio_storage

        storage = get_minio_storage()
        await storage.ensure_initialized()
        return await storage.get_object_range(self._bucket, file_id, offset, length)
