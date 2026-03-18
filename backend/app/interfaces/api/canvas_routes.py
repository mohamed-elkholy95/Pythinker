"""API routes for canvas project management."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.application.services.canvas_service import get_canvas_service
from app.domain.models.canvas import CanvasPage, CanvasProject
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.canvas import (
    AIEditRequest,
    CreateProjectRequest,
    DeleteProjectResponse,
    EditImageRequest,
    ElementResponse,
    GenerateImageRequest,
    ImageResponse,
    PageResponse,
    ProjectListResponse,
    ProjectResponse,
    RemoveBackgroundRequest,
    UpdateProjectRequest,
    VersionListResponse,
    VersionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canvas", tags=["canvas"])


def _project_to_response(p: CanvasProject) -> ProjectResponse:
    pages = []
    for page in p.pages:
        elements = [
            ElementResponse(
                id=el.id,
                type=el.type.value if hasattr(el.type, "value") else str(el.type),
                name=el.name,
                x=el.x,
                y=el.y,
                width=el.width,
                height=el.height,
                rotation=el.rotation,
                opacity=el.opacity,
                visible=el.visible,
                locked=el.locked,
                z_index=el.z_index,
                fill=el.fill,
                stroke=el.stroke,
                shadow=el.shadow,
                corner_radius=el.corner_radius,
                text=el.text,
                text_style=el.text_style,
                src=el.src,
                points=el.points,
                children=el.children,
                scale_x=el.scale_x,
                scale_y=el.scale_y,
            )
            for el in page.elements
        ]
        pages.append(
            PageResponse(
                id=page.id,
                name=page.name,
                width=page.width,
                height=page.height,
                background=page.background,
                elements=elements,
                sort_order=page.sort_order,
            )
        )
    return ProjectResponse(
        id=p.id,
        user_id=p.user_id,
        session_id=p.session_id,
        name=p.name,
        description=p.description,
        pages=pages,
        width=p.width,
        height=p.height,
        background=p.background,
        thumbnail=p.thumbnail,
        version=p.version,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# --- Project endpoints ---


@router.post("/projects", response_model=APIResponse[ProjectResponse])
async def create_project(
    request: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    """Create a new canvas project."""
    service = get_canvas_service()
    project = await service.create_project(
        user_id=current_user.id,
        name=request.name,
        width=request.width,
        height=request.height,
        background=request.background,
        session_id=request.session_id,
    )
    return APIResponse(data=_project_to_response(project))


@router.get("/projects", response_model=APIResponse[ProjectListResponse])
async def list_projects(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectListResponse]:
    """List user's canvas projects."""
    service = get_canvas_service()
    projects = await service.list_projects(current_user.id, skip=skip, limit=limit)
    return APIResponse(
        data=ProjectListResponse(
            projects=[_project_to_response(p) for p in projects],
            total=len(projects),
        )
    )


@router.get("/projects/{project_id}", response_model=APIResponse[ProjectResponse])
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    """Get a specific canvas project."""
    service = get_canvas_service()
    project = await service.get_project(project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse(data=_project_to_response(project))


@router.get("/sessions/{session_id}/project", response_model=APIResponse[ProjectResponse])
async def get_session_project(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    """Get the most recently updated canvas project attached to a session."""
    service = get_canvas_service()
    project = await service.get_project_by_session_id(session_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse(data=_project_to_response(project))


@router.put("/projects/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    """Update a canvas project (full state save)."""
    service = get_canvas_service()
    existing = await service.get_project(project_id)
    if not existing or existing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Apply updates
    if request.name is not None:
        existing.name = request.name
    if request.width is not None:
        existing.width = request.width
    if request.height is not None:
        existing.height = request.height
    if request.background is not None:
        existing.background = request.background
    if request.thumbnail is not None:
        existing.thumbnail = request.thumbnail
    if request.pages is not None:
        existing.pages = [CanvasPage.model_validate(p) for p in request.pages]

    updated = await service.update_project(project_id, existing)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse(data=_project_to_response(updated))


@router.delete("/projects/{project_id}", response_model=APIResponse[DeleteProjectResponse])
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[DeleteProjectResponse]:
    """Delete a canvas project."""
    service = get_canvas_service()
    existing = await service.get_project(project_id)
    if not existing or existing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    deleted = await service.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse(data=DeleteProjectResponse(deleted=True))


# --- Version endpoints ---


@router.get(
    "/projects/{project_id}/versions",
    response_model=APIResponse[VersionListResponse],
)
async def get_versions(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[VersionListResponse]:
    """Get version history for a project."""
    service = get_canvas_service()
    existing = await service.get_project(project_id)
    if not existing or existing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    versions = await service.get_versions(project_id)
    return APIResponse(
        data=VersionListResponse(
            versions=[
                VersionResponse(
                    id=v.id,
                    project_id=v.project_id,
                    version=v.version,
                    name=v.name,
                    created_at=v.created_at,
                )
                for v in versions
            ],
            total=len(versions),
        )
    )


@router.post(
    "/projects/{project_id}/versions/{version}/restore",
    response_model=APIResponse[ProjectResponse],
)
async def restore_version(
    project_id: str,
    version: int,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    """Restore a project to a previous version."""
    service = get_canvas_service()
    existing = await service.get_project(project_id)
    if not existing or existing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    restored = await service.restore_version(project_id, version)
    if not restored:
        raise HTTPException(status_code=404, detail="Version not found")
    return APIResponse(data=_project_to_response(restored))


# --- Image generation endpoints ---


@router.post("/generate-image", response_model=APIResponse[ImageResponse])
async def generate_image(
    request: GenerateImageRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImageResponse]:
    """Generate an image from a text prompt using FLUX 2 Pro."""
    service = get_canvas_service()
    urls = await service.generate_image(
        prompt=request.prompt,
        width=request.width,
        height=request.height,
    )
    return APIResponse(data=ImageResponse(urls=urls))


@router.post("/edit-image", response_model=APIResponse[ImageResponse])
async def edit_image(
    request: EditImageRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImageResponse]:
    """Edit an image using natural language instruction."""
    service = get_canvas_service()
    urls = await service.edit_image(request.image_url, request.instruction)
    return APIResponse(data=ImageResponse(urls=urls))


@router.post("/remove-background", response_model=APIResponse[ImageResponse])
async def remove_background(
    request: RemoveBackgroundRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImageResponse]:
    """Remove background from an image."""
    service = get_canvas_service()
    urls = await service.remove_background(request.image_url)
    return APIResponse(data=ImageResponse(urls=urls))


# --- AI edit endpoint ---


@router.post(
    "/projects/{project_id}/ai-edit",
    response_model=APIResponse[ProjectResponse],
)
async def ai_edit(
    project_id: str,
    request: AIEditRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ProjectResponse]:
    """Apply a natural language edit to a canvas project."""
    service = get_canvas_service()
    existing = await service.get_project(project_id)
    if not existing or existing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await service.apply_ai_edit(project_id, request.instruction)
    if not result:
        raise HTTPException(status_code=500, detail="AI edit failed")
    return APIResponse(data=_project_to_response(result))
