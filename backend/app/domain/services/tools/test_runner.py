"""
Test Runner Tool Implementation

Provides test execution, listing, and coverage capabilities for agents.
"""

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool


class TestRunnerTool(BaseTool):
    """Test runner tool class, providing test execution functions"""

    name: str = "test_runner"

    def __init__(self, sandbox: Sandbox, max_observe: int | None = None):
        """Initialize Test Runner tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
        """
        super().__init__(
            max_observe=max_observe,
            defaults=ToolDefaults(category="test"),
        )
        self.sandbox = sandbox

    @tool(
        name="test_run",
        description="Run tests in a project. Auto-detects test framework (pytest, unittest, jest, mocha). Returns pass/fail counts, failures details, and optional coverage.",
        parameters={
            "path": {"type": "string", "description": "Path to test file or directory"},
            "framework": {
                "type": "string",
                "description": "Test framework: 'auto' (detect), 'pytest', 'unittest', 'jest', 'mocha', 'npm_test'",
                "enum": ["auto", "pytest", "unittest", "jest", "mocha", "npm_test"],
            },
            "pattern": {
                "type": "string",
                "description": "Pattern to match test names (e.g., 'test_auth*' for pytest, 'auth' for jest)",
            },
            "coverage": {"type": "boolean", "description": "Collect code coverage during test run"},
            "timeout": {"type": "integer", "description": "Test timeout in seconds (10-1800)"},
            "verbose": {"type": "boolean", "description": "Include full test output in result"},
        },
        required=["path"],
    )
    async def test_run(
        self,
        path: str,
        framework: str = "auto",
        pattern: str | None = None,
        coverage: bool = False,
        timeout: int = 300,  # noqa: ASYNC109
        verbose: bool = False,
    ) -> ToolResult:
        """Run tests

        Args:
            path: Path to test file or directory
            framework: Test framework to use
            pattern: Pattern to match tests
            coverage: Collect coverage
            timeout: Test timeout
            verbose: Verbose output

        Returns:
            Test execution result
        """
        return await self.sandbox.test_run(path, framework, pattern, coverage, timeout, verbose)

    @tool(
        name="test_list",
        description="List available tests without executing them. Shows test names, files, and class names. Use to understand test structure before running.",
        parameters={
            "path": {"type": "string", "description": "Path to test file or directory"},
            "framework": {
                "type": "string",
                "description": "Test framework: 'auto' (detect), 'pytest', 'unittest', 'jest', 'mocha'",
                "enum": ["auto", "pytest", "unittest", "jest", "mocha"],
            },
        },
        required=["path"],
    )
    async def test_list(self, path: str, framework: str = "auto") -> ToolResult:
        """List available tests

        Args:
            path: Path to test file or directory
            framework: Test framework

        Returns:
            List of tests
        """
        return await self.sandbox.test_list(path, framework)

    @tool(
        name="test_coverage",
        description="Generate a code coverage report. Creates HTML, XML, or JSON report showing which lines are covered by tests.",
        parameters={
            "path": {"type": "string", "description": "Path to source code directory"},
            "output_format": {
                "type": "string",
                "description": "Report format: 'html', 'xml', 'json'",
                "enum": ["html", "xml", "json"],
            },
            "output_dir": {"type": "string", "description": "Output directory for report (optional)"},
        },
        required=["path"],
    )
    async def test_coverage(self, path: str, output_format: str = "html", output_dir: str | None = None) -> ToolResult:
        """Generate coverage report

        Args:
            path: Path to source code
            output_format: Report format
            output_dir: Output directory

        Returns:
            Coverage report result
        """
        return await self.sandbox.test_coverage(path, output_format, output_dir)
