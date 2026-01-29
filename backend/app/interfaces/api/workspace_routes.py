"""Workspace template and structure API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.services.agent_service import AgentService
from app.domain.models.user import User
from app.domain.services.workspace import (
    get_all_templates,
    get_template,
)
from app.interfaces.dependencies import get_agent_service, get_current_user
from app.interfaces.schemas.base import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])


# Response schemas
class WorkspaceTemplateResponse(BaseModel):
    """Response schema for workspace template."""
    name: str
    description: str
    folders: dict[str, str]
    trigger_keywords: list[str]


class WorkspaceTemplateListResponse(BaseModel):
    """Response schema for list of workspace templates."""
    templates: list[WorkspaceTemplateResponse]


class SessionWorkspaceResponse(BaseModel):
    """Response schema for session workspace structure."""
    session_id: str
    workspace_structure: dict[str, str] | None
    workspace_root: str | None


@router.get("/templates", response_model=APIResponse[WorkspaceTemplateListResponse])
async def list_workspace_templates(
    current_user: User = Depends(get_current_user),
) -> APIResponse[WorkspaceTemplateListResponse]:
    """List all available workspace templates.

    Returns a list of all workspace templates with their descriptions,
    folder structures, and trigger keywords.
    """
    try:
        templates = get_all_templates()

        template_responses = [
            WorkspaceTemplateResponse(
                name=template.name,
                description=template.description,
                folders=template.folders,
                trigger_keywords=template.trigger_keywords,
            )
            for template in templates
        ]

        return APIResponse.success(
            WorkspaceTemplateListResponse(templates=template_responses)
        )
    except Exception as e:
        logger.error(f"Error listing workspace templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to list workspace templates")


@router.get("/templates/{template_name}", response_model=APIResponse[WorkspaceTemplateResponse])
async def get_workspace_template(
    template_name: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[WorkspaceTemplateResponse]:
    """Get details for a specific workspace template.

    Args:
        template_name: Name of the template (e.g., 'research', 'data_analysis')

    Returns:
        Template details including folders and trigger keywords.
    """
    try:
        template = get_template(template_name)

        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Workspace template '{template_name}' not found"
            )

        return APIResponse.success(
            WorkspaceTemplateResponse(
                name=template.name,
                description=template.description,
                folders=template.folders,
                trigger_keywords=template.trigger_keywords,
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workspace template '{template_name}': {e}")
        raise HTTPException(status_code=500, detail="Failed to get workspace template")


@router.get("/sessions/{session_id}", response_model=APIResponse[SessionWorkspaceResponse])
async def get_session_workspace(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[SessionWorkspaceResponse]:
    """Get workspace structure for a session.

    Args:
        session_id: ID of the session

    Returns:
        Session workspace structure with folder descriptions.
    """
    try:
        session = await agent_service.get_session(session_id, current_user.id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found"
            )

        # Determine workspace root
        workspace_root = None
        if session.workspace_structure:
            workspace_root = f"/workspace/{session_id}"

        return APIResponse.success(
            SessionWorkspaceResponse(
                session_id=session.id,
                workspace_structure=session.workspace_structure,
                workspace_root=workspace_root,
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workspace for session '{session_id}': {e}")
        raise HTTPException(status_code=500, detail="Failed to get session workspace")
