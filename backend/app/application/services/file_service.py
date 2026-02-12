import io
import logging
import zipfile
from typing import Any, BinaryIO

from app.application.services.token_service import TokenService
from app.domain.external.file import FileStorage
from app.domain.models.file import FileInfo

# Set up logger
logger = logging.getLogger(__name__)


class FileService:
    def __init__(self, file_storage: FileStorage | None = None, token_service: TokenService | None = None):
        self._file_storage = file_storage
        self._token_service = token_service

    async def upload_file(
        self,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FileInfo:
        """Upload file"""
        logger.info(f"Upload file request: filename={filename}, user_id={user_id}, content_type={content_type}")
        if not self._file_storage:
            logger.error("File storage service not available")
            raise RuntimeError("File storage service not available")

        try:
            result = await self._file_storage.upload_file(file_data, filename, user_id, content_type, metadata)
            logger.info(f"File uploaded successfully: file_id={result.file_id}, user_id={user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to upload file for user {user_id}: {e!s}")
            raise

    async def download_file(self, file_id: str, user_id: str | None = None) -> tuple[BinaryIO, FileInfo]:
        """Download file"""
        logger.info(f"Download file request: file_id={file_id}, user_id={user_id}")
        if not self._file_storage:
            logger.error("File storage service not available")
            raise RuntimeError("File storage service not available")

        try:
            result = await self._file_storage.download_file(file_id, user_id)
            logger.info(f"File downloaded successfully: file_id={file_id}, user_id={user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to download file {file_id} for user {user_id}: {e!s}")
            raise

    async def delete_file(self, file_id: str, user_id: str) -> bool:
        """Delete file"""
        logger.info(f"Delete file request: file_id={file_id}, user_id={user_id}")
        if not self._file_storage:
            logger.error("File storage service not available")
            raise RuntimeError("File storage service not available")

        try:
            result = await self._file_storage.delete_file(file_id, user_id)
            if result:
                logger.info(f"File deleted successfully: file_id={file_id}, user_id={user_id}")
            else:
                logger.warning(f"File deletion failed or file not found: file_id={file_id}, user_id={user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to delete file {file_id} for user {user_id}: {e!s}")
            raise

    async def get_file_info(self, file_id: str, user_id: str | None = None) -> FileInfo | None:
        """Get file information"""
        logger.info(f"Get file info request: file_id={file_id}, user_id={user_id}")
        if not self._file_storage:
            logger.error("File storage service not available")
            raise RuntimeError("File storage service not available")

        try:
            result = await self._file_storage.get_file_info(file_id, user_id)
            if result:
                logger.info(f"File info retrieved successfully: file_id={file_id}, user_id={user_id}")
            else:
                logger.warning(f"File not found or access denied: file_id={file_id}, user_id={user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to get file info {file_id} for user {user_id}: {e!s}")
            raise

    async def enrich_with_file_url(self, file_info: FileInfo) -> FileInfo:
        """Enrich file information with file URL"""
        logger.info(f"Enrich file info request: file_info={file_info}")

        try:
            signed_url = await self.create_signed_url(file_info.file_id, file_info.user_id)
            file_info.file_url = signed_url
            return file_info
        except Exception as e:
            logger.error(f"Failed to enrich file info {file_info.file_id} with file URL: {e!s}")
            raise

    async def create_signed_url(self, file_id: str, user_id: str | None = None, expire_minutes: int = 30) -> str:
        """Create signed URL for file download"""
        logger.info(f"Create signed URL request: file_id={file_id}, user_id={user_id}, expire_minutes={expire_minutes}")

        if not self._token_service:
            logger.error("Token service not available")
            raise RuntimeError("Token service not available")

        # Validate expiration time (max 15 minutes)
        if expire_minutes > 30:
            expire_minutes = 30

        # Check if file exists and user has access
        file_info = await self.get_file_info(file_id, user_id)
        if not file_info:
            logger.warning(f"File not found or access denied for signed URL: file_id={file_id}, user_id={user_id}")
            raise FileNotFoundError("File not found")

        # Create signed URL for file download
        base_url = f"/api/v1/files/{file_id}"
        signed_url = self._token_service.create_signed_url(base_url=base_url, expire_minutes=expire_minutes)

        logger.info(f"Created signed URL for file download for user {user_id}, file {file_id}")

        return signed_url

    async def generate_upload_url(
        self, filename: str, user_id: str, content_type: str | None = None
    ) -> tuple[str, str]:
        """Generate a presigned URL for direct file upload.

        Returns:
            Tuple of (presigned_url, object_key)
        """
        if not self._file_storage:
            raise RuntimeError("File storage service not available")

        return await self._file_storage.generate_upload_url(filename, user_id, content_type)

    async def generate_download_url(self, file_id: str, user_id: str | None = None) -> str:
        """Generate a presigned URL for direct file download."""
        if not self._file_storage:
            raise RuntimeError("File storage service not available")

        return await self._file_storage.generate_download_url(file_id, user_id)

    async def create_zip_archive(self, file_ids: list[str], user_id: str | None = None) -> tuple[io.BytesIO, str]:
        """Create a zip archive containing multiple files

        Args:
            file_ids: List of file IDs to include in the archive
            user_id: User ID for access control

        Returns:
            Tuple of (zip file bytes, suggested filename)
        """
        logger.info(f"Creating zip archive for {len(file_ids)} files, user_id={user_id}")

        if not self._file_storage:
            logger.error("File storage service not available")
            raise RuntimeError("File storage service not available")

        # Create in-memory zip file
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            filenames_count: dict[str, int] = {}

            for file_id in file_ids:
                try:
                    file_data, file_info = await self._file_storage.download_file(file_id, user_id)

                    # Handle duplicate filenames by adding suffix
                    filename = file_info.filename
                    if filename in filenames_count:
                        filenames_count[filename] += 1
                        name_parts = filename.rsplit(".", 1)
                        if len(name_parts) > 1:
                            filename = f"{name_parts[0]}_{filenames_count[filename]}.{name_parts[1]}"
                        else:
                            filename = f"{filename}_{filenames_count[filename]}"
                    else:
                        filenames_count[filename] = 0

                    # Read file content and add to zip
                    content = file_data.read()
                    zip_file.writestr(filename, content)
                    logger.debug(f"Added file to zip: {filename}")

                except Exception as e:
                    logger.warning(f"Failed to add file {file_id} to zip: {e!s}")
                    continue

        zip_buffer.seek(0)

        # Generate archive filename
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"files_{timestamp}.zip"

        logger.info(f"Zip archive created successfully: {archive_name}, size={zip_buffer.getbuffer().nbytes} bytes")
        return zip_buffer, archive_name
