from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class GitRemoteSpec(BaseModel):
    repo_url: Optional[str] = None
    remote_name: Optional[str] = None
    branch: Optional[str] = None
    credentials: Optional[Dict[str, str]] = None


class WorkspaceManifest(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    template_id: Optional[str] = None
    capabilities: List[str] = []
    dev_command: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    port: Optional[int] = None
    env_vars: Dict[str, str] = Field(default_factory=dict)
    secrets: Dict[str, str] = Field(default_factory=dict)
    files: Dict[str, str] = Field(default_factory=dict)
    git_remote: Optional[GitRemoteSpec] = None


class WorkspaceWriteError(BaseModel):
    path: str
    message: str


class WorkspaceManifestResponse(BaseModel):
    session_id: str
    workspace_root: str
    project_root: str
    project_name: str
    project_path: Optional[str] = None
    template_id: Optional[str] = None
    template_used: Optional[str] = None
    capabilities: List[str] = []
    files_written: int = 0
    files_failed: int = 0
    write_errors: List[WorkspaceWriteError] = []
    env_var_keys: List[str] = []
    secret_keys: List[str] = []
    dev_command: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    port: Optional[int] = None
    git_remote: Optional[GitRemoteSpec] = None
    git_clone_success: Optional[bool] = None
    git_clone_message: Optional[str] = None
