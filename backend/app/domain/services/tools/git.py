"""
Git Tool Implementation

Provides git operations for agents including repository cloning,
status checking, diff viewing, and commit history.
"""

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool


class GitTool(BaseTool):
    """Git tool class, providing git repository operations"""

    name: str = "git"

    def __init__(self, sandbox: Sandbox, max_observe: int | None = None):
        """Initialize Git tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
        """
        super().__init__(
            max_observe=max_observe,
            defaults=ToolDefaults(is_read_only=True, is_concurrency_safe=True, category="git"),
        )
        self.sandbox = sandbox

    @tool(
        name="git_clone",
        description="Clone a git repository to the workspace. Supports public repos and private repos with authentication token. URLs are validated against a whitelist (github.com, gitlab.com, bitbucket.org).",
        parameters={
            "url": {"type": "string", "description": "Repository URL (https://github.com/user/repo.git)"},
            "target_dir": {
                "type": "string",
                "description": "Target directory path (e.g., /workspace/session-id/src/repo)",
            },
            "branch": {"type": "string", "description": "Branch to clone (optional, defaults to default branch)"},
            "shallow": {
                "type": "boolean",
                "description": "Whether to do a shallow clone (depth=1). Faster but no history.",
            },
            "auth_token": {
                "type": "string",
                "description": "Authentication token for private repositories (ephemeral, not stored)",
            },
        },
        required=["url", "target_dir"],
    )
    async def git_clone(
        self, url: str, target_dir: str, branch: str | None = None, shallow: bool = True, auth_token: str | None = None
    ) -> ToolResult:
        """Clone a git repository

        Args:
            url: Repository URL
            target_dir: Target directory path
            branch: Branch to clone
            shallow: Whether to do a shallow clone
            auth_token: Authentication token for private repos

        Returns:
            Clone result with repo details
        """
        return await self.sandbox.git_clone(url, target_dir, branch, shallow, auth_token)

    @tool(
        name="git_status",
        description="Get the status of a git repository. Shows current branch, staged files, modified files, untracked files, and ahead/behind remote.",
        parameters={"repo_path": {"type": "string", "description": "Path to the git repository"}},
        required=["repo_path"],
    )
    async def git_status(self, repo_path: str) -> ToolResult:
        """Get git repository status

        Args:
            repo_path: Path to git repository

        Returns:
            Status information
        """
        return await self.sandbox.git_status(repo_path)

    @tool(
        name="git_diff",
        description="Show differences in a git repository. Can show working tree changes or staged changes. Optionally diff a specific file.",
        parameters={
            "repo_path": {"type": "string", "description": "Path to the git repository"},
            "staged": {"type": "boolean", "description": "Show staged changes instead of working tree changes"},
            "file_path": {"type": "string", "description": "Specific file to diff (relative to repo root)"},
        },
        required=["repo_path"],
    )
    async def git_diff(self, repo_path: str, staged: bool = False, file_path: str | None = None) -> ToolResult:
        """Get git diff

        Args:
            repo_path: Path to git repository
            staged: Show staged changes
            file_path: Specific file to diff

        Returns:
            Diff information
        """
        return await self.sandbox.git_diff(repo_path, staged, file_path)

    @tool(
        name="git_log",
        description="Show commit history of a git repository. Returns recent commits with hash, author, date, and message.",
        parameters={
            "repo_path": {"type": "string", "description": "Path to the git repository"},
            "limit": {"type": "integer", "description": "Maximum number of commits to return (1-100)"},
            "file_path": {"type": "string", "description": "Show history for a specific file only"},
        },
        required=["repo_path"],
    )
    async def git_log(self, repo_path: str, limit: int = 10, file_path: str | None = None) -> ToolResult:
        """Get git commit history

        Args:
            repo_path: Path to git repository
            limit: Maximum commits to return
            file_path: Specific file to show history for

        Returns:
            Commit history
        """
        return await self.sandbox.git_log(repo_path, limit, file_path)

    @tool(
        name="git_branches",
        description="List branches in a git repository. Shows current branch and all local/remote branches.",
        parameters={
            "repo_path": {"type": "string", "description": "Path to the git repository"},
            "show_remote": {"type": "boolean", "description": "Include remote branches in the list"},
        },
        required=["repo_path"],
    )
    async def git_branches(self, repo_path: str, show_remote: bool = True) -> ToolResult:
        """Get git branches

        Args:
            repo_path: Path to git repository
            show_remote: Include remote branches

        Returns:
            Branch information
        """
        return await self.sandbox.git_branches(repo_path, show_remote)
