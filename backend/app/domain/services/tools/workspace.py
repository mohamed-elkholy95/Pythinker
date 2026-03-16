"""
Workspace Tool Implementation

Provides workspace management capabilities for agents including
initialization, info retrieval, and directory tree operations.
"""

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool


class WorkspaceTool(BaseTool):
    """Workspace tool class, providing workspace management functions"""

    name: str = "workspace"

    def __init__(self, sandbox: Sandbox, max_observe: int | None = None):
        """Initialize Workspace tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox

    @tool(
        name="workspace_init",
        description="Initialize a new workspace for the current session. Creates directory structure with optional template (python, nodejs, web, fullstack). Use at the start of a project.",
        parameters={
            "session_id": {"type": "string", "description": "Unique session identifier"},
            "project_name": {"type": "string", "description": "Name of the project (used in generated files)"},
            "template": {
                "type": "string",
                "description": "Workspace template: 'none' (basic), 'python', 'nodejs', 'web', or 'fullstack'",
                "enum": ["none", "python", "nodejs", "web", "fullstack"],
            },
        },
        required=["session_id"],
    )
    async def workspace_init(
        self, session_id: str, project_name: str = "project", template: str = "none"
    ) -> ToolResult:
        """Initialize a new workspace

        Args:
            session_id: Unique session identifier
            project_name: Name of the project
            template: Workspace template to use

        Returns:
            Initialization result with created directories and files
        """
        return await self.sandbox.workspace_init(session_id, project_name, template)

    @tool(
        name="workspace_info",
        description="Get information about the current workspace including size, file count, and configuration. Use to check workspace status.",
        parameters={"session_id": {"type": "string", "description": "Session ID to get workspace info for"}},
        required=["session_id"],
    )
    async def workspace_info(self, session_id: str) -> ToolResult:
        """Get workspace information

        Args:
            session_id: Session ID

        Returns:
            Workspace information including size, file count, and config
        """
        return await self.sandbox.workspace_info(session_id)

    @tool(
        name="workspace_tree",
        description="Display the directory tree structure of the workspace. Shows files and folders hierarchically. Use to understand project structure.",
        parameters={
            "session_id": {"type": "string", "description": "Session ID"},
            "depth": {"type": "integer", "description": "Maximum depth of tree traversal (1-10)"},
            "include_hidden": {"type": "boolean", "description": "Whether to include hidden files/directories"},
        },
        required=["session_id"],
    )
    async def workspace_tree(self, session_id: str, depth: int = 3, include_hidden: bool = False) -> ToolResult:
        """Get workspace directory tree

        Args:
            session_id: Session ID
            depth: Maximum depth to traverse (1-10)
            include_hidden: Whether to include hidden files

        Returns:
            Directory tree structure
        """
        return await self.sandbox.workspace_tree(session_id, depth, include_hidden)

    @tool(
        name="workspace_clean",
        description="Clean the workspace by removing all files and directories. Optionally preserves configuration. Use with caution.",
        parameters={
            "session_id": {"type": "string", "description": "Session ID"},
            "preserve_config": {"type": "boolean", "description": "Whether to preserve .pythinker config directory"},
        },
        required=["session_id"],
    )
    async def workspace_clean(self, session_id: str, preserve_config: bool = True) -> ToolResult:
        """Clean workspace contents

        Args:
            session_id: Session ID
            preserve_config: Whether to preserve config directory

        Returns:
            Cleanup result
        """
        return await self.sandbox.workspace_clean(session_id, preserve_config)

    @tool(
        name="workspace_exists",
        description="Check if a workspace exists for a session. Use before operations that require an existing workspace.",
        parameters={"session_id": {"type": "string", "description": "Session ID to check"}},
        required=["session_id"],
    )
    async def workspace_exists(self, session_id: str) -> ToolResult:
        """Check if workspace exists

        Args:
            session_id: Session ID to check

        Returns:
            Whether the workspace exists
        """
        return await self.sandbox.workspace_exists(session_id)
