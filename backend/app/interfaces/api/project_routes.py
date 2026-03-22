"""API routes for project management."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.application.services.project_service import get_project_service
from app.domain.models.project import Project, ProjectStatus
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.project import (
    CreateProjectRequest,
    ProjectListItem,
    ProjectResponse,
    UpdateProjectRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_to_response(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        instructions=p.instructions,
        connector_ids=p.connector_ids,
        file_ids=p.file_ids,
        skill_ids=p.skill_ids,
        status=p.status,
        session_count=p.session_count,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _project_to_list_item(p: Project) -> ProjectListItem:
    return ProjectListItem(
        id=p.id,
        name=p.name,
        status=p.status,
        session_count=p.session_count,
        updated_at=p.updated_at,
    )


@router.post("", response_model=APIResponse[ProjectResponse])
async def create_project(
    request: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    service = get_project_service()
    project = await service.create_project(
        user_id=current_user.id,
        name=request.name,
        instructions=request.instructions,
        connector_ids=request.connector_ids,
    )
    return APIResponse.success(_project_to_response(project))


@router.get("", response_model=APIResponse[list[ProjectListItem]])
async def list_projects(
    status: ProjectStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[ProjectListItem]]:
    service = get_project_service()
    projects = await service.list_projects(
        user_id=current_user.id,
        status=status,
        limit=min(limit, 100),
        offset=offset,
    )
    return APIResponse.success([_project_to_list_item(p) for p in projects])


@router.get("/{project_id}", response_model=APIResponse[ProjectResponse])
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    service = get_project_service()
    project = await service.get_project(project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse.success(_project_to_response(project))


@router.patch("/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    service = get_project_service()
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    project = await service.update_project(project_id, current_user.id, updates)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse.success(_project_to_response(project))


@router.delete("/{project_id}", response_model=APIResponse[None])
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[None]:
    service = get_project_service()
    deleted = await service.delete_project(project_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse.success(None, msg="Project deleted")


@router.get("/{project_id}/sessions", response_model=APIResponse[list[dict]])
async def list_project_sessions(
    project_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[dict]]:
    """List sessions belonging to a project."""
    service = get_project_service()
    project = await service.get_project(project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    sessions = await service.list_project_sessions(project_id, current_user.id, limit, offset)
    return APIResponse.success(sessions)
