"""
Code Development Tool Implementation

Provides code formatting, linting, analysis, and search capabilities.
"""

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool


class CodeDevTool(BaseTool):
    """Code development tool class, providing formatting, linting, and analysis functions"""

    name: str = "code_dev"

    def __init__(self, sandbox: Sandbox, max_observe: int | None = None):
        """Initialize Code Development tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox

    @tool(
        name="code_format",
        description="Format a code file using the appropriate formatter. Auto-detects formatter from file extension. Supports: black (Python), prettier (JS/TS/JSON/CSS/HTML/MD).",
        parameters={
            "file_path": {"type": "string", "description": "Path to the file to format"},
            "formatter": {
                "type": "string",
                "description": "Formatter to use: 'auto' (detect), 'black', 'isort', 'autopep8', 'prettier'",
                "enum": ["auto", "black", "isort", "autopep8", "prettier"],
            },
            "check_only": {
                "type": "boolean",
                "description": "Check formatting without modifying the file. Returns diff of what would change.",
            },
        },
        required=["file_path"],
    )
    async def code_format(self, file_path: str, formatter: str = "auto", check_only: bool = False) -> ToolResult:
        """Format a code file

        Args:
            file_path: Path to file to format
            formatter: Formatter to use
            check_only: Check without modifying

        Returns:
            Formatting result
        """
        return await self.sandbox.code_format(file_path, formatter, check_only)

    @tool(
        name="code_lint",
        description="Lint code files to find issues and style violations. Auto-detects linter from file type. Supports: flake8, pylint, mypy (Python), eslint (JS/TS).",
        parameters={
            "path": {"type": "string", "description": "Path to file or directory to lint"},
            "linter": {
                "type": "string",
                "description": "Linter to use: 'auto' (detect), 'flake8', 'pylint', 'mypy', 'eslint'",
                "enum": ["auto", "flake8", "pylint", "mypy", "eslint"],
            },
            "fix": {"type": "boolean", "description": "Automatically fix issues where possible (eslint only)"},
        },
        required=["path"],
    )
    async def code_lint(self, path: str, linter: str = "auto", fix: bool = False) -> ToolResult:
        """Lint code files

        Args:
            path: Path to file or directory
            linter: Linter to use
            fix: Auto-fix issues

        Returns:
            Linting result with issues found
        """
        return await self.sandbox.code_lint(path, linter, fix)

    @tool(
        name="code_analyze",
        description="Analyze code for security vulnerabilities and complexity issues. Uses bandit for Python security analysis.",
        parameters={
            "path": {"type": "string", "description": "Path to file or directory to analyze"},
            "analysis_type": {
                "type": "string",
                "description": "Type of analysis: 'security', 'complexity', or 'all'",
                "enum": ["security", "complexity", "all"],
            },
        },
        required=["path"],
    )
    async def code_analyze(self, path: str, analysis_type: str = "all") -> ToolResult:
        """Analyze code for security and complexity

        Args:
            path: Path to file or directory
            analysis_type: Type of analysis

        Returns:
            Analysis result with issues and scores
        """
        return await self.sandbox.code_analyze(path, analysis_type)

    @tool(
        name="code_search",
        description="Search for pattern in code files using ripgrep. Supports regex patterns and returns matches with context.",
        parameters={
            "directory": {"type": "string", "description": "Directory to search in"},
            "pattern": {"type": "string", "description": "Search pattern (regex supported)"},
            "file_glob": {"type": "string", "description": "Glob pattern to filter files (e.g., '*.py', '*.js')"},
            "context_lines": {"type": "integer", "description": "Number of context lines before/after match (0-10)"},
            "max_results": {"type": "integer", "description": "Maximum number of results (1-1000)"},
        },
        required=["directory", "pattern"],
    )
    async def code_search(
        self, directory: str, pattern: str, file_glob: str = "*", context_lines: int = 2, max_results: int = 100
    ) -> ToolResult:
        """Search for pattern in code files

        Args:
            directory: Directory to search
            pattern: Search pattern
            file_glob: File filter
            context_lines: Context lines
            max_results: Max results

        Returns:
            Search results with matches
        """
        return await self.sandbox.code_search(directory, pattern, file_glob, context_lines, max_results)
