from typing import BinaryIO, Protocol

from app.domain.external.browser import Browser
from app.domain.models.tool_result import ToolResult


class Sandbox(Protocol):
    """Sandbox service gateway interface"""

    async def ensure_sandbox(self) -> None:
        """Ensure sandbox is ready"""
        ...

    async def ensure_framework(self, session_id: str) -> None:
        """Ensure sandbox framework is initialized for a session"""
        ...

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        """Execute command

        Args:
            session_id: Session ID
            exec_dir: Execution directory
            command: Command to execute

        Returns:
            Command execution result
        """
        ...

    async def view_shell(self, session_id: str, console: bool = False) -> ToolResult:
        """View shell status

        Args:
            session_id: Session ID
            console: Whether to return console records

        Returns:
            Shell status information
        """
        ...

    async def wait_for_process(self, session_id: str, seconds: int | None = None) -> ToolResult:
        """Wait for process

        Args:
            session_id: Session ID
            seconds: Wait seconds

        Returns:
            Wait result
        """
        ...

    async def write_to_process(self, session_id: str, input_text: str, press_enter: bool = True) -> ToolResult:
        """Write input to process

        Args:
            session_id: Session ID
            input_text: Input text
            press_enter: Whether to press enter

        Returns:
            Write result
        """
        ...

    async def kill_process(self, session_id: str) -> ToolResult:
        """Terminate process

        Args:
            session_id: Session ID

        Returns:
            Termination result
        """
        ...

    async def file_write(
        self,
        file: str,
        content: str,
        append: bool = False,
        leading_newline: bool = False,
        trailing_newline: bool = False,
        sudo: bool = False,
    ) -> ToolResult:
        """Write content to file

        Args:
            file: File path
            content: Content to write
            append: Whether to append content
            leading_newline: Whether to add newline before content
            trailing_newline: Whether to add newline after content
            sudo: Whether to use sudo privileges

        Returns:
            Write operation result
        """
        ...

    async def file_read(
        self, file: str, start_line: int | None = None, end_line: int | None = None, sudo: bool = False
    ) -> ToolResult:
        """Read file content

        Args:
            file: File path
            start_line: Start line number
            end_line: End line number
            sudo: Whether to use sudo privileges

        Returns:
            File content
        """
        ...

    async def file_exists(self, path: str) -> ToolResult:
        """Check if file exists

        Args:
            path: File path

        Returns:
            Whether file exists
        """
        ...

    async def file_delete(self, path: str) -> ToolResult:
        """Delete file

        Args:
            path: File path

        Returns:
            Delete operation result
        """
        ...

    async def file_list(self, path: str) -> ToolResult:
        """List directory contents

        Args:
            path: Directory path

        Returns:
            Directory content list
        """
        ...

    async def file_replace(self, file: str, old_str: str, new_str: str, sudo: bool = False) -> ToolResult:
        """Replace string in file

        Args:
            file: File path
            old_str: String to replace
            new_str: Replacement string
            sudo: Whether to use sudo privileges

        Returns:
            Replace operation result
        """
        ...

    async def file_search(self, file: str, regex: str, sudo: bool = False) -> ToolResult:
        """Search in file content

        Args:
            file: File path
            regex: Regular expression
            sudo: Whether to use sudo privileges

        Returns:
            Search result
        """
        ...

    async def file_find(self, path: str, glob_pattern: str) -> ToolResult:
        """Find files by name pattern

        Args:
            path: Search directory path
            glob_pattern: Glob matching pattern

        Returns:
            Found file list
        """
        ...

    async def file_upload(self, file_data: BinaryIO, path: str, filename: str | None = None) -> ToolResult:
        """Upload file to sandbox

        Args:
            file_data: File content as binary stream
            path: Target file path in sandbox
            filename: Original filename (optional)

        Returns:
            Upload operation result
        """
        ...

    async def file_download(self, path: str) -> BinaryIO:
        """Download file from sandbox

        Args:
            path: File path in sandbox

        Returns:
            File content as binary stream
        """
        ...

    # Workspace management methods
    async def workspace_init(
        self, session_id: str, project_name: str = "project", template: str = "none"
    ) -> ToolResult:
        """Initialize a workspace for a session

        Args:
            session_id: Unique session identifier
            project_name: Name of the project
            template: Workspace template (none, python, nodejs, web, fullstack)

        Returns:
            Initialization result
        """
        ...

    async def workspace_info(self, session_id: str) -> ToolResult:
        """Get workspace information

        Args:
            session_id: Session ID

        Returns:
            Workspace information
        """
        ...

    async def workspace_tree(self, session_id: str, depth: int = 3, include_hidden: bool = False) -> ToolResult:
        """Get workspace directory tree

        Args:
            session_id: Session ID
            depth: Maximum depth to traverse
            include_hidden: Whether to include hidden files

        Returns:
            Directory tree structure
        """
        ...

    async def workspace_clean(self, session_id: str, preserve_config: bool = True) -> ToolResult:
        """Clean workspace contents

        Args:
            session_id: Session ID
            preserve_config: Whether to preserve config

        Returns:
            Cleanup result
        """
        ...

    async def workspace_exists(self, session_id: str) -> ToolResult:
        """Check if workspace exists

        Args:
            session_id: Session ID

        Returns:
            Whether workspace exists
        """
        ...

    # Git operations
    async def git_clone(
        self, url: str, target_dir: str, branch: str | None = None, shallow: bool = True, auth_token: str | None = None
    ) -> ToolResult:
        """Clone a git repository

        Args:
            url: Repository URL
            target_dir: Target directory path
            branch: Branch to clone
            shallow: Whether to do shallow clone
            auth_token: Authentication token for private repos

        Returns:
            Clone result
        """
        ...

    async def git_status(self, repo_path: str) -> ToolResult:
        """Get git repository status

        Args:
            repo_path: Path to repository

        Returns:
            Repository status
        """
        ...

    async def git_diff(self, repo_path: str, staged: bool = False, file_path: str | None = None) -> ToolResult:
        """Get git diff

        Args:
            repo_path: Path to repository
            staged: Show staged changes
            file_path: Specific file to diff

        Returns:
            Diff result
        """
        ...

    async def git_log(self, repo_path: str, limit: int = 10, file_path: str | None = None) -> ToolResult:
        """Get git commit history

        Args:
            repo_path: Path to repository
            limit: Maximum commits
            file_path: Specific file

        Returns:
            Commit history
        """
        ...

    async def git_branches(self, repo_path: str, show_remote: bool = True) -> ToolResult:
        """Get git branches

        Args:
            repo_path: Path to repository
            show_remote: Include remote branches

        Returns:
            Branch information
        """
        ...

    # Code development operations
    async def code_format(self, file_path: str, formatter: str = "auto", check_only: bool = False) -> ToolResult:
        """Format a code file

        Args:
            file_path: Path to file
            formatter: Formatter to use
            check_only: Check without modifying

        Returns:
            Format result
        """
        ...

    async def code_lint(self, path: str, linter: str = "auto", fix: bool = False) -> ToolResult:
        """Lint code files

        Args:
            path: Path to file or directory
            linter: Linter to use
            fix: Auto-fix issues

        Returns:
            Lint result
        """
        ...

    async def code_analyze(self, path: str, analysis_type: str = "all") -> ToolResult:
        """Analyze code

        Args:
            path: Path to file or directory
            analysis_type: Type of analysis

        Returns:
            Analysis result
        """
        ...

    async def code_search(
        self, directory: str, pattern: str, file_glob: str = "*", context_lines: int = 2, max_results: int = 100
    ) -> ToolResult:
        """Search code files

        Args:
            directory: Directory to search
            pattern: Search pattern
            file_glob: File filter
            context_lines: Context lines
            max_results: Max results

        Returns:
            Search result
        """
        ...

    # Test execution operations
    async def test_run(
        self,
        path: str,
        framework: str = "auto",
        pattern: str | None = None,
        coverage: bool = False,
        timeout: int = 300,
        verbose: bool = False,
    ) -> ToolResult:
        """Run tests

        Args:
            path: Path to tests
            framework: Test framework
            pattern: Test pattern
            coverage: Collect coverage
            timeout: Timeout
            verbose: Verbose output

        Returns:
            Test result
        """
        ...

    async def test_list(self, path: str, framework: str = "auto") -> ToolResult:
        """List available tests

        Args:
            path: Path to tests
            framework: Test framework

        Returns:
            Test list
        """
        ...

    async def test_coverage(self, path: str, output_format: str = "html", output_dir: str | None = None) -> ToolResult:
        """Generate coverage report

        Args:
            path: Path to source code
            output_format: Report format
            output_dir: Output directory

        Returns:
            Coverage result
        """
        ...

    # Export operations
    async def export_organize(self, session_id: str, source_path: str, target_category: str = "other") -> ToolResult:
        """Organize files

        Args:
            session_id: Session ID
            source_path: Source path
            target_category: Category

        Returns:
            Organization result
        """
        ...

    async def export_archive(
        self,
        session_id: str,
        name: str,
        include_patterns: list | None = None,
        exclude_patterns: list | None = None,
        base_path: str | None = None,
    ) -> ToolResult:
        """Create archive

        Args:
            session_id: Session ID
            name: Archive name
            include_patterns: Include patterns
            exclude_patterns: Exclude patterns
            base_path: Base path

        Returns:
            Archive result
        """
        ...

    async def export_report(
        self,
        session_id: str,
        report_type: str = "summary",
        output_format: str = "markdown",
        title: str = "Workspace Report",
    ) -> ToolResult:
        """Generate report

        Args:
            session_id: Session ID
            report_type: Report type
            output_format: Output format
            title: Report title

        Returns:
            Report result
        """
        ...

    async def export_list(self, session_id: str) -> ToolResult:
        """List exports

        Args:
            session_id: Session ID

        Returns:
            Export list
        """
        ...

    async def get_screenshot(self, quality: int = 75, scale: float = 0.5, format: str = "jpeg"):
        """Capture screenshot of the sandbox desktop.

        Args:
            quality: JPEG quality (1-100)
            scale: Scale factor (0.1-1.0)
            format: Image format (jpeg or png)

        Returns:
            HTTP response with image bytes
        """
        ...

    async def destroy(self) -> bool:
        """Destroy current sandbox instance

        Returns:
            Whether destroyed successfully
        """
        ...

    async def pause(self) -> bool:
        """Pause container to reclaim CPU while preserving memory state.

        Returns:
            Whether paused successfully
        """
        ...

    async def unpause(self) -> bool:
        """Unpause a paused container, resuming all processes.

        Returns:
            Whether unpaused successfully
        """
        ...

    async def get_browser(self, clear_session: bool = False) -> Browser:
        """Get browser instance

        Args:
            clear_session: If True, clear all existing tabs for a fresh session

        Returns:
            Browser: Returns a configured browser instance for web automation
        """
        ...

    @property
    def id(self) -> str:
        """Sandbox ID"""
        ...

    @property
    def cdp_url(self) -> str:
        """CDP URL"""
        ...

    @property
    def vnc_url(self) -> str:
        """VNC URL"""
        ...

    @classmethod
    async def create(cls) -> "Sandbox":
        """Create a new sandbox instance"""
        ...

    @classmethod
    async def get(cls, id: str) -> "Sandbox":
        """Get sandbox by ID

        Args:
            id: Sandbox ID

        Returns:
            Sandbox instance
        """
        ...
