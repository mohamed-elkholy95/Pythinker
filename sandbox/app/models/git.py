"""
Git business model definitions
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class GitCloneResult(BaseModel):
    """Result of git clone operation"""
    success: bool = Field(..., description="Whether clone succeeded")
    repo_path: str = Field(..., description="Path to cloned repository")
    repo_url: str = Field(..., description="Repository URL")
    branch: str = Field(default="main", description="Cloned branch")
    commit_hash: Optional[str] = Field(None, description="HEAD commit hash")
    commit_message: Optional[str] = Field(None, description="HEAD commit message")
    shallow: bool = Field(default=False, description="Whether shallow clone was used")
    files_count: int = Field(default=0, description="Number of files cloned")
    message: Optional[str] = Field(None, description="Additional status message")


class GitStatusResult(BaseModel):
    """Result of git status operation"""
    branch: str = Field(..., description="Current branch name")
    clean: bool = Field(..., description="Whether working tree is clean")
    ahead: int = Field(default=0, description="Commits ahead of remote")
    behind: int = Field(default=0, description="Commits behind remote")
    staged: List[str] = Field(default_factory=list, description="Staged files")
    modified: List[str] = Field(default_factory=list, description="Modified files")
    untracked: List[str] = Field(default_factory=list, description="Untracked files")
    deleted: List[str] = Field(default_factory=list, description="Deleted files")


class GitDiffResult(BaseModel):
    """Result of git diff operation"""
    files_changed: int = Field(default=0, description="Number of files changed")
    insertions: int = Field(default=0, description="Lines added")
    deletions: int = Field(default=0, description="Lines deleted")
    diff_output: str = Field(default="", description="Diff output text")
    staged: bool = Field(default=False, description="Whether showing staged changes")


class GitLogEntry(BaseModel):
    """Single git log entry"""
    commit_hash: str = Field(..., description="Commit hash")
    author: str = Field(..., description="Author name")
    author_email: str = Field(default="", description="Author email")
    date: str = Field(..., description="Commit date")
    message: str = Field(..., description="Commit message")


class GitLogResult(BaseModel):
    """Result of git log operation"""
    commits: List[GitLogEntry] = Field(default_factory=list, description="List of commits")
    total_count: int = Field(default=0, description="Total number of commits returned")


class GitBranchResult(BaseModel):
    """Result of git branch operation"""
    current: str = Field(..., description="Current branch name")
    local: List[str] = Field(default_factory=list, description="Local branches")
    remote: List[str] = Field(default_factory=list, description="Remote branches")
