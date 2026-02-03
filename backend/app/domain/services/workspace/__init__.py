"""Workspace management services."""

from app.domain.services.workspace.session_workspace_initializer import (
    SessionWorkspaceInitializer,
    get_session_workspace_initializer,
)
from app.domain.services.workspace.workspace_organizer import WorkspaceOrganizer
from app.domain.services.workspace.workspace_selector import WorkspaceSelector
from app.domain.services.workspace.workspace_templates import (
    WORKSPACE_TEMPLATES,
    WorkspaceTemplate,
    get_all_templates,
    get_template,
)

__all__ = [
    "WORKSPACE_TEMPLATES",
    "SessionWorkspaceInitializer",
    "WorkspaceOrganizer",
    "WorkspaceSelector",
    "WorkspaceTemplate",
    "get_all_templates",
    "get_session_workspace_initializer",
    "get_template",
]
