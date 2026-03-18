"""
Git request/response schemas for API endpoints
"""

from pydantic import BaseModel, Field
from typing import Optional


class GitCloneRequest(BaseModel):
    """Request to clone a git repository"""

    url: str = Field(..., description="Repository URL to clone")
    target_dir: str = Field(..., description="Target directory path")
    branch: Optional[str] = Field(
        None, description="Branch to clone (default: default branch)"
    )
    shallow: Optional[bool] = Field(
        True, description="Whether to do a shallow clone (depth=1)"
    )
    auth_token: Optional[str] = Field(
        None, description="Authentication token for private repos"
    )


class GitStatusRequest(BaseModel):
    """Request to get git status"""

    repo_path: str = Field(..., description="Path to git repository")


class GitDiffRequest(BaseModel):
    """Request to get git diff"""

    repo_path: str = Field(..., description="Path to git repository")
    staged: Optional[bool] = Field(
        False, description="Show staged changes instead of working tree"
    )
    file_path: Optional[str] = Field(None, description="Specific file to diff")


class GitLogRequest(BaseModel):
    """Request to get git log"""

    repo_path: str = Field(..., description="Path to git repository")
    limit: Optional[int] = Field(
        10, ge=1, le=100, description="Maximum number of commits to return"
    )
    file_path: Optional[str] = Field(
        None, description="Specific file to show history for"
    )


class GitBranchRequest(BaseModel):
    """Request to get git branches"""

    repo_path: str = Field(..., description="Path to git repository")
    show_remote: Optional[bool] = Field(True, description="Include remote branches")
