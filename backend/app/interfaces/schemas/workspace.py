
from pydantic import BaseModel, Field


class GitRemoteSpec(BaseModel):
    repo_url: str | None = None
    remote_name: str | None = None
    branch: str | None = None
    credentials: dict[str, str] | None = None


class WorkspaceManifest(BaseModel):
    name: str | None = None
    path: str | None = None
    template_id: str | None = None
    capabilities: list[str] = []
    dev_command: str | None = None
    build_command: str | None = None
    test_command: str | None = None
    port: int | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    files: dict[str, str] = Field(default_factory=dict)
    git_remote: GitRemoteSpec | None = None


class WorkspaceWriteError(BaseModel):
    path: str
    message: str


class WorkspaceManifestResponse(BaseModel):
    session_id: str
    workspace_root: str
    project_root: str
    project_name: str
    project_path: str | None = None
    template_id: str | None = None
    template_used: str | None = None
    capabilities: list[str] = []
    files_written: int = 0
    files_failed: int = 0
    write_errors: list[WorkspaceWriteError] = []
    env_var_keys: list[str] = []
    secret_keys: list[str] = []
    dev_command: str | None = None
    build_command: str | None = None
    test_command: str | None = None
    port: int | None = None
    git_remote: GitRemoteSpec | None = None
    git_clone_success: bool | None = None
    git_clone_message: str | None = None
