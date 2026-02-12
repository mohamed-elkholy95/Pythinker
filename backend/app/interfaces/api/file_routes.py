import logging

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.application.errors.exceptions import BadRequestError, NotFoundError
from app.application.services.file_service import FileService
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user, get_file_service, get_optional_current_user, verify_signature
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.file import FileInfoResponse
from app.interfaces.schemas.resource import AccessTokenRequest, SignedUrlResponse


class BatchDownloadRequest(BaseModel):
    """Request body for batch file download as zip"""

    file_ids: list[str]


class PresignedUploadRequest(BaseModel):
    """Request body for generating a presigned upload URL"""

    filename: str
    content_type: str | None = None


class PresignedUploadResponse(BaseModel):
    """Response for presigned upload URL"""

    upload_url: str
    object_key: str


class PresignedDownloadResponse(BaseModel):
    """Response for presigned download URL"""

    download_url: str


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=APIResponse[FileInfoResponse])
async def upload_file(
    file: UploadFile = File(...),
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse[FileInfoResponse]:
    """Upload file"""
    # Upload file
    result = await file_service.upload_file(
        file_data=file.file, filename=file.filename, user_id=current_user.id, content_type=file.content_type
    )

    return APIResponse.success(await FileInfoResponse.from_file_info(result))


@router.get("/{file_id}")
async def download_file_with_signature(
    file_id: str,
    file_service: FileService = Depends(get_file_service),
    signature: str = Depends(verify_signature),
):
    """Download file with optional access token"""

    # Download file (authentication is handled by middleware for non-token requests)
    try:
        file_data, file_info = await file_service.download_file(file_id)
    except FileNotFoundError as e:
        raise NotFoundError("File not found") from e
    except PermissionError as e:
        raise NotFoundError("File not found") from e  # Don't reveal if file exists but user has no access

    # Encode filename properly for Content-Disposition header
    # Use URL encoding for non-ASCII characters to ensure latin-1 compatibility
    import urllib.parse

    encoded_filename = urllib.parse.quote(file_info.filename, safe="")

    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}

    return StreamingResponse(
        file_data, media_type=file_info.content_type or "application/octet-stream", headers=headers
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_optional_current_user),
):
    """Download file with optional access token"""

    # Download file (authentication is handled by middleware for non-token requests)
    try:
        file_data, file_info = await file_service.download_file(file_id, current_user.id if current_user else None)
    except FileNotFoundError as e:
        raise NotFoundError("File not found") from e
    except PermissionError as e:
        raise NotFoundError("File not found") from e  # Don't reveal if file exists but user has no access

    # Encode filename properly for Content-Disposition header
    # Use URL encoding for non-ASCII characters to ensure latin-1 compatibility
    import urllib.parse

    encoded_filename = urllib.parse.quote(file_info.filename, safe="")

    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}

    return StreamingResponse(
        file_data, media_type=file_info.content_type or "application/octet-stream", headers=headers
    )


@router.delete("/{file_id}", response_model=APIResponse[None])
async def delete_file(
    file_id: str, file_service: FileService = Depends(get_file_service), current_user: User = Depends(get_current_user)
) -> APIResponse[None]:
    """Delete file"""
    success = await file_service.delete_file(file_id, current_user.id)
    if not success:
        raise NotFoundError("File not found")
    return APIResponse.success()


@router.get("/{file_id}/info", response_model=APIResponse[FileInfoResponse])
async def get_file_info(
    file_id: str, file_service: FileService = Depends(get_file_service), current_user: User = Depends(get_current_user)
) -> APIResponse[FileInfoResponse]:
    """Get file information"""
    file_info = await file_service.get_file_info(file_id, current_user.id)
    if not file_info:
        raise NotFoundError("File not found")

    return APIResponse.success(await FileInfoResponse.from_file_info(file_info))


@router.post("/{file_id}/signed-url", response_model=APIResponse[SignedUrlResponse])
async def create_file_signed_url(
    file_id: str,
    request_data: AccessTokenRequest,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[SignedUrlResponse]:
    """Generate signed URL for file download

    This endpoint creates a signed URL that allows temporary access to download
    a specific file without requiring authentication headers.
    """

    try:
        # Create signed URL using file service
        signed_url = await file_service.create_signed_url(
            file_id=file_id, user_id=current_user.id, expire_minutes=request_data.expire_minutes
        )

        return APIResponse.success(
            SignedUrlResponse(
                signed_url=signed_url,
                expires_in=request_data.expire_minutes * 60,
            )
        )
    except FileNotFoundError as e:
        raise NotFoundError("File not found") from e


@router.post("/presigned-upload", response_model=APIResponse[PresignedUploadResponse])
async def create_presigned_upload_url(
    request_data: PresignedUploadRequest,
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse[PresignedUploadResponse]:
    """Generate a presigned URL for direct file upload to MinIO.

    The client can PUT the file directly to the returned URL without
    proxying through the backend.
    """
    try:
        upload_url, object_key = await file_service.generate_upload_url(
            filename=request_data.filename,
            user_id=current_user.id,
            content_type=request_data.content_type,
        )
    except NotImplementedError as e:
        raise BadRequestError("Presigned URLs are not supported by the current storage backend") from e
    return APIResponse.success(PresignedUploadResponse(upload_url=upload_url, object_key=object_key))


@router.get("/{file_id}/presigned-download", response_model=APIResponse[PresignedDownloadResponse])
async def create_presigned_download_url(
    file_id: str,
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse[PresignedDownloadResponse]:
    """Generate a presigned URL for direct file download from MinIO."""
    try:
        download_url = await file_service.generate_download_url(
            file_id=file_id,
            user_id=current_user.id,
        )
    except NotImplementedError as e:
        raise BadRequestError("Presigned URLs are not supported by the current storage backend") from e
    except PermissionError as e:
        raise NotFoundError("File not found") from e
    return APIResponse.success(PresignedDownloadResponse(download_url=download_url))


@router.post("/batch/download")
async def batch_download_files(
    request_data: BatchDownloadRequest,
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_user),
):
    """Download multiple files as a zip archive"""

    if not request_data.file_ids:
        raise NotFoundError("No files specified")

    try:
        zip_buffer, archive_name = await file_service.create_zip_archive(
            file_ids=request_data.file_ids, user_id=current_user.id
        )

        import urllib.parse

        encoded_filename = urllib.parse.quote(archive_name, safe="")

        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}

        return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)
    except Exception as e:
        logger.error(f"Failed to create zip archive: {e!s}")
        raise NotFoundError("Failed to create archive") from e
