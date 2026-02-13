"""
Workspace business model definitions
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class WorkspaceTemplate(str, Enum):
    """Available workspace templates"""

    NONE = "none"
    PYTHON = "python"
    NODEJS = "nodejs"
    WEB = "web"
    FULLSTACK = "fullstack"


class WorkspaceStatus(str, Enum):
    """Workspace status states"""

    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"


class WorkspaceConfig(BaseModel):
    """Workspace configuration stored in .pythinker/config.json"""

    session_id: str = Field(..., description="Session ID that owns this workspace")
    project_name: str = Field(..., description="Project name")
    template: WorkspaceTemplate = Field(
        default=WorkspaceTemplate.NONE, description="Workspace template used"
    )
    created_at: str = Field(..., description="Creation timestamp")
    python_version: Optional[str] = Field(
        None, description="Python version if applicable"
    )
    node_version: Optional[str] = Field(
        None, description="Node.js version if applicable"
    )
    git_repo: Optional[str] = Field(None, description="Git repository URL if cloned")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class WorkspaceInitResult(BaseModel):
    """Result of workspace initialization"""

    session_id: str = Field(..., description="Session ID")
    workspace_path: str = Field(..., description="Absolute path to workspace")
    project_name: str = Field(..., description="Project name")
    template: str = Field(..., description="Template used")
    status: str = Field(..., description="Initialization status")
    directories_created: List[str] = Field(
        default_factory=list, description="List of created directories"
    )
    files_created: List[str] = Field(
        default_factory=list, description="List of created files"
    )
    message: Optional[str] = Field(None, description="Additional status message")


class WorkspaceInfo(BaseModel):
    """Workspace information result"""

    session_id: str = Field(..., description="Session ID")
    workspace_path: str = Field(..., description="Absolute path to workspace")
    project_name: str = Field(..., description="Project name")
    template: str = Field(..., description="Template used")
    created_at: str = Field(..., description="Creation timestamp")
    status: str = Field(..., description="Current status")
    size_bytes: int = Field(default=0, description="Total workspace size in bytes")
    file_count: int = Field(default=0, description="Number of files in workspace")
    git_repo: Optional[str] = Field(None, description="Git repository URL if cloned")
    python_version: Optional[str] = Field(
        None, description="Python version if applicable"
    )
    node_version: Optional[str] = Field(
        None, description="Node.js version if applicable"
    )


class DirectoryEntry(BaseModel):
    """Entry in directory tree"""

    name: str = Field(..., description="File or directory name")
    type: str = Field(..., description="Type: 'file' or 'directory'")
    size: Optional[int] = Field(None, description="File size in bytes (for files)")
    children: Optional[List["DirectoryEntry"]] = Field(
        None, description="Child entries (for directories)"
    )


class WorkspaceTreeResult(BaseModel):
    """Result of workspace tree operation"""

    session_id: str = Field(..., description="Session ID")
    workspace_path: str = Field(..., description="Workspace root path")
    tree: DirectoryEntry = Field(..., description="Directory tree structure")
    total_files: int = Field(default=0, description="Total number of files")
    total_directories: int = Field(default=0, description="Total number of directories")
    total_size_bytes: int = Field(default=0, description="Total size of all files")


# Enable forward references for recursive model
DirectoryEntry.model_rebuild()
