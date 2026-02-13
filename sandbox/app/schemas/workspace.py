"""
Workspace request/response schemas for API endpoints
"""

from pydantic import BaseModel, Field
from typing import Optional
from app.models.workspace import WorkspaceTemplate


class WorkspaceInitRequest(BaseModel):
    """Request to initialize a new workspace"""

    session_id: str = Field(..., description="Unique session identifier")
    project_name: str = Field(default="project", description="Name of the project")
    template: Optional[WorkspaceTemplate] = Field(
        default=WorkspaceTemplate.NONE,
        description="Workspace template to use (none, python, nodejs, web, fullstack)",
    )


class WorkspaceInfoRequest(BaseModel):
    """Request to get workspace information"""

    session_id: str = Field(..., description="Session ID to get workspace info for")


class WorkspaceTreeRequest(BaseModel):
    """Request to get workspace directory tree"""

    session_id: str = Field(..., description="Session ID")
    depth: Optional[int] = Field(
        default=3, ge=1, le=10, description="Maximum depth of tree traversal (1-10)"
    )
    include_hidden: Optional[bool] = Field(
        default=False, description="Whether to include hidden files/directories"
    )


class WorkspaceCleanRequest(BaseModel):
    """Request to clean workspace"""

    session_id: str = Field(..., description="Session ID")
    preserve_config: Optional[bool] = Field(
        default=True, description="Whether to preserve .pythinker config directory"
    )
