"""
Workspace API Endpoints

Provides REST API for workspace management operations.
"""
from fastapi import APIRouter
from app.schemas.workspace import (
    WorkspaceInitRequest, WorkspaceInfoRequest,
    WorkspaceTreeRequest, WorkspaceCleanRequest
)
from app.schemas.response import Response
from app.services.workspace import workspace_service
from app.core.exceptions import BadRequestException

router = APIRouter()


@router.post("/init", response_model=Response)
async def init_workspace(request: WorkspaceInitRequest):
    """
    Initialize a new workspace for a session.

    Creates the workspace directory structure with optional template.
    Templates: none, python, nodejs, web, fullstack
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")

    result = await workspace_service.init_workspace(
        session_id=request.session_id,
        project_name=request.project_name,
        template=request.template
    )

    return Response(
        success=True,
        message=f"Workspace initialized with {request.template.value} template",
        data=result.model_dump()
    )


@router.post("/info", response_model=Response)
async def get_workspace_info(request: WorkspaceInfoRequest):
    """
    Get information about an existing workspace.

    Returns workspace details including size, file count, and configuration.
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")

    result = await workspace_service.get_workspace_info(
        session_id=request.session_id
    )

    return Response(
        success=True,
        message="Workspace info retrieved successfully",
        data=result.model_dump()
    )


@router.post("/tree", response_model=Response)
async def get_workspace_tree(request: WorkspaceTreeRequest):
    """
    Get directory tree of workspace.

    Returns hierarchical structure of files and directories.
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")

    result = await workspace_service.get_workspace_tree(
        session_id=request.session_id,
        depth=request.depth,
        include_hidden=request.include_hidden
    )

    return Response(
        success=True,
        message="Workspace tree retrieved successfully",
        data=result.model_dump()
    )


@router.post("/clean", response_model=Response)
async def clean_workspace(request: WorkspaceCleanRequest):
    """
    Clean workspace contents.

    Removes all files and directories from workspace.
    Optionally preserves .pythinker config directory.
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")

    result = await workspace_service.clean_workspace(
        session_id=request.session_id,
        preserve_config=request.preserve_config
    )

    return Response(
        success=True,
        message="Workspace cleaned successfully",
        data=result
    )


@router.post("/exists", response_model=Response)
async def workspace_exists(request: WorkspaceInfoRequest):
    """
    Check if a workspace exists for a session.
    """
    if not request.session_id:
        raise BadRequestException("Session ID is required")

    exists = await workspace_service.workspace_exists(
        session_id=request.session_id
    )

    return Response(
        success=True,
        message="Workspace existence checked",
        data={"exists": exists, "session_id": request.session_id}
    )
