"""
Export API Endpoints

Provides REST API for file organization, archiving, and report generation.
"""
from fastapi import APIRouter
from app.schemas.export import (
    OrganizeRequest, ArchiveRequest,
    ReportRequest, ExportListRequest
)
from app.schemas.response import Response
from app.services.export import export_service
from app.core.exceptions import BadRequestException

router = APIRouter()


@router.post("/organize", response_model=Response)
async def organize_files(request: OrganizeRequest):
    """
    Organize files into appropriate workspace directories.

    Moves files to categorized directories (src, tests, docs, output).
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")
    if not request.source_path:
        raise BadRequestException("Source path is required")

    result = await export_service.organize_files(
        session_id=request.session_id,
        source_path=request.source_path,
        target_category=request.target_category
    )

    return Response(
        success=result.success,
        message=result.message or "Files organized",
        data=result.model_dump(exclude={"message"})
    )


@router.post("/archive", response_model=Response)
async def create_archive(request: ArchiveRequest):
    """
    Create a ZIP archive of workspace files.

    Supports include/exclude patterns for selective archiving.
    Archives are stored in workspace/output/exports/.
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")
    if not request.name:
        raise BadRequestException("Archive name is required")

    result = await export_service.create_archive(
        session_id=request.session_id,
        name=request.name,
        include_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
        base_path=request.base_path
    )

    return Response(
        success=result.success,
        message=result.message or "Archive created",
        data=result.model_dump(exclude={"message"})
    )


@router.post("/report", response_model=Response)
async def generate_report(request: ReportRequest):
    """
    Generate a workspace report.

    Supports summary, test, security, and full report types.
    Output formats: markdown, html, json.
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")

    result = await export_service.generate_report(
        session_id=request.session_id,
        report_type=request.report_type,
        output_format=request.output_format,
        title=request.title,
        include_sections=request.include_sections
    )

    return Response(
        success=result.success,
        message=result.message or "Report generated",
        data=result.model_dump(exclude={"message"})
    )


@router.post("/list", response_model=Response)
async def list_exports(request: ExportListRequest):
    """
    List available exports (archives and reports).

    Returns all files in the exports directory with metadata.
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")

    result = await export_service.list_exports(
        session_id=request.session_id
    )

    return Response(
        success=True,
        message=f"Found {result.total_count} exports",
        data=result.model_dump()
    )
