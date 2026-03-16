"""Application-layer DTOs used by services and interfaces."""

from app.application.schemas.file import FileViewResponse
from app.application.schemas.session import ConsoleRecord, ShellViewResponse
from app.application.schemas.workspace import (
    GitRemoteSpec,
    WorkspaceManifest,
    WorkspaceManifestResponse,
    WorkspaceWriteError,
)

__all__ = [
    "ConsoleRecord",
    "FileViewResponse",
    "GitRemoteSpec",
    "ShellViewResponse",
    "WorkspaceManifest",
    "WorkspaceManifestResponse",
    "WorkspaceWriteError",
]
