import io
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

from minio.error import S3Error

from app.core.config import get_settings
from app.domain.external.file import FileStorage
from app.domain.models.file import FileInfo
from app.infrastructure.storage.minio_storage import MinIOStorage

logger = logging.getLogger(__name__)


class MinIOFileStorage(FileStorage):
    """MinIO S3-based file storage implementation.

    Object key format: {user_id}/{uuid}_{filename}
    User access control via S3 object metadata (x-amz-meta-user-id).
    """

    def __init__(self, minio_storage: MinIOStorage):
        self._minio = minio_storage
        self._settings = get_settings()

    @property
    def _bucket(self) -> str:
        return self._settings.minio_bucket_name

    def _make_object_key(self, user_id: str, filename: str) -> str:
        """Generate a unique object key namespaced by user."""
        unique_id = uuid.uuid4().hex[:12]
        safe_filename = filename.replace("/", "_").replace("\\", "_")
        return f"{user_id}/{unique_id}_{safe_filename}"

    async def upload_file(
        self,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FileInfo:
        """Upload file to MinIO."""
        try:
            client = self._minio.client
            object_key = self._make_object_key(user_id, filename)

            # Build S3 metadata (all values must be strings)
            s3_metadata = {
                "user-id": user_id,
                "original-filename": filename,
            }
            if content_type:
                s3_metadata["content-type"] = content_type
            if metadata:
                for k, v in metadata.items():
                    s3_metadata[k] = str(v)

            # Determine content length by seeking
            file_data.seek(0, 2)  # seek to end
            content_length = file_data.tell()
            file_data.seek(0)  # seek back to start

            result = client.put_object(
                self._bucket,
                object_key,
                file_data,
                length=content_length,
                content_type=content_type or "application/octet-stream",
                metadata=s3_metadata,
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
        """Download file from MinIO by object key."""
        try:
            client = self._minio.client

            # Get object stat to check metadata/ownership
            stat = client.stat_object(self._bucket, file_id)
            obj_metadata = stat.metadata or {}

            # Check user ownership
            file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
            if user_id is not None and file_user_id and file_user_id != user_id:
                raise PermissionError(f"Access denied: file {file_id} does not belong to user {user_id}")

            # Download object into BytesIO
            response = client.get_object(self._bucket, file_id)
            try:
                data = io.BytesIO(response.read())
            finally:
                response.close()
                response.release_conn()

            file_info = FileInfo(
                file_id=file_id,
                filename=obj_metadata.get("x-amz-meta-original-filename", file_id.split("/")[-1]),
                content_type=stat.content_type,
                size=stat.size,
                upload_date=stat.last_modified,
                metadata=dict(obj_metadata),
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
        """Delete file from MinIO."""
        try:
            client = self._minio.client

            # Check ownership before deletion
            stat = client.stat_object(self._bucket, file_id)
            obj_metadata = stat.metadata or {}
            file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
            if file_user_id and file_user_id != user_id:
                logger.warning("Delete access denied: file %s does not belong to user %s", file_id, user_id)
                return False

            client.remove_object(self._bucket, file_id)
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
        """Get file metadata from MinIO."""
        try:
            client = self._minio.client
            stat = client.stat_object(self._bucket, file_id)
            obj_metadata = stat.metadata or {}

            # Check ownership
            file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
            if user_id is not None and file_user_id and file_user_id != user_id:
                logger.warning("Access denied: file %s does not belong to user %s", file_id, user_id)
                return None

            return FileInfo(
                file_id=file_id,
                filename=obj_metadata.get("x-amz-meta-original-filename", file_id.split("/")[-1]),
                content_type=stat.content_type,
                size=stat.size,
                upload_date=stat.last_modified,
                metadata=dict(obj_metadata),
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
        """Generate a presigned PUT URL for direct upload to MinIO."""
        try:
            client = self._minio.client
            object_key = self._make_object_key(user_id, filename)
            expiry = timedelta(seconds=self._settings.minio_presigned_expiry_seconds)

            url = client.presigned_put_object(
                self._bucket,
                object_key,
                expires=expiry,
            )

            logger.info("Generated presigned upload URL for %s (key: %s)", filename, object_key)
            return url, object_key

        except Exception as e:
            logger.error("Failed to generate upload URL for %s: %s", filename, e)
            raise

    async def generate_download_url(self, file_id: str, user_id: str | None = None) -> str:
        """Generate a presigned GET URL for direct download from MinIO."""
        try:
            client = self._minio.client

            # Verify ownership if user_id provided
            if user_id is not None:
                stat = client.stat_object(self._bucket, file_id)
                obj_metadata = stat.metadata or {}
                file_user_id = obj_metadata.get("x-amz-meta-user-id", "")
                if file_user_id and file_user_id != user_id:
                    raise PermissionError(f"Access denied: file {file_id} does not belong to user {user_id}")

            expiry = timedelta(seconds=self._settings.minio_presigned_expiry_seconds)

            url = client.presigned_get_object(
                self._bucket,
                file_id,
                expires=expiry,
            )

            logger.info("Generated presigned download URL for %s", file_id)
            return url

        except PermissionError:
            raise
        except Exception as e:
            logger.error("Failed to generate download URL for %s: %s", file_id, e)
            raise
