import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.domain.models.file import FileInfo

logger = logging.getLogger(__name__)


class FileViewRequest(BaseModel):
    """File view request schema"""
    file: str


class FileViewResponse(BaseModel):
    """File view response schema"""
    content: str
    file: str


class FileInfoResponse(BaseModel):
    """File info response schema"""
    file_id: str
    filename: str
    content_type: str | None
    size: int
    upload_date: datetime | None = None
    metadata: dict[str, Any] | None
    file_url: str | None

    @staticmethod
    async def from_file_info(file_info: FileInfo) -> Optional["FileInfoResponse"]:
        """
        Convert a FileInfo domain model to a FileInfoResponse schema.

        Args:
            file_info: The FileInfo domain object to convert

        Returns:
            FileInfoResponse if conversion is successful, None if the FileInfo
            is invalid (missing file_id or filename)

        Note:
            Returns None instead of raising an exception when file_info has
            invalid data, allowing callers to filter out invalid attachments
            gracefully.
        """
        # Validate required fields before attempting conversion
        if not file_info:
            logger.warning("from_file_info called with None file_info")
            return None

        if not file_info.file_id:
            logger.warning(
                f"FileInfo missing file_id: filename={file_info.filename}, "
                f"file_path={file_info.file_path}"
            )
            return None

        if not file_info.filename:
            logger.warning(
                f"FileInfo missing filename: file_id={file_info.file_id}, "
                f"file_path={file_info.file_path}"
            )
            return None

        try:
            from app.interfaces.dependencies import get_file_service
            file_service = get_file_service()
            file_url = await file_service.create_signed_url(file_info.file_id)

            return FileInfoResponse(
                file_id=file_info.file_id,
                filename=file_info.filename,
                content_type=file_info.content_type,
                size=file_info.size or 0,
                upload_date=file_info.upload_date,
                metadata=file_info.metadata,
                file_url=file_url
            )
        except FileNotFoundError:
            logger.warning(
                f"File not found when creating signed URL: file_id={file_info.file_id}, "
                f"filename={file_info.filename}"
            )
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error converting FileInfo to response: "
                f"file_id={file_info.file_id}, error={e}"
            )
            return None
