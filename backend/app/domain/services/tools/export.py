"""
Export Tool Implementation

Provides file organization, archiving, and report generation capabilities.
"""
from typing import Optional, List
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult


class ExportTool(BaseTool):
    """Export tool class, providing file organization and export functions"""

    name: str = "export"

    def __init__(self, sandbox: Sandbox, max_observe: Optional[int] = None):
        """Initialize Export tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox

    @tool(
        name="export_organize",
        description="Organize files into appropriate workspace directories. Moves files to categorized folders (src, tests, docs, output) based on file type.",
        parameters={
            "session_id": {
                "type": "string",
                "description": "Session ID"
            },
            "source_path": {
                "type": "string",
                "description": "Path to file or directory to organize"
            },
            "target_category": {
                "type": "string",
                "description": "Target category: 'source', 'test', 'docs', 'config', 'output', 'other'",
                "enum": ["source", "test", "docs", "config", "output", "other"]
            }
        },
        required=["session_id", "source_path"]
    )
    async def export_organize(
        self,
        session_id: str,
        source_path: str,
        target_category: str = "other"
    ) -> ToolResult:
        """Organize files into workspace directories

        Args:
            session_id: Session ID
            source_path: Source file or directory
            target_category: Target category

        Returns:
            Organization result
        """
        return await self.sandbox.export_organize(session_id, source_path, target_category)

    @tool(
        name="export_archive",
        description="Create a ZIP archive of workspace files. Supports include/exclude patterns for selective archiving. Use for creating downloadable project exports.",
        parameters={
            "session_id": {
                "type": "string",
                "description": "Session ID"
            },
            "name": {
                "type": "string",
                "description": "Archive name (without .zip extension)"
            },
            "include_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Glob patterns to include (e.g., ['src/**', 'tests/**'])"
            },
            "exclude_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Glob patterns to exclude (e.g., ['node_modules/**', '__pycache__/**'])"
            },
            "base_path": {
                "type": "string",
                "description": "Base path for files (defaults to workspace root)"
            }
        },
        required=["session_id", "name"]
    )
    async def export_archive(
        self,
        session_id: str,
        name: str,
        include_patterns: List[str] = None,
        exclude_patterns: List[str] = None,
        base_path: str = None
    ) -> ToolResult:
        """Create ZIP archive of workspace

        Args:
            session_id: Session ID
            name: Archive name
            include_patterns: Patterns to include
            exclude_patterns: Patterns to exclude
            base_path: Base path for files

        Returns:
            Archive creation result
        """
        return await self.sandbox.export_archive(session_id, name, include_patterns, exclude_patterns, base_path)

    @tool(
        name="export_report",
        description="Generate a workspace report with project overview, structure, test results, and security analysis. Supports markdown, HTML, and JSON formats.",
        parameters={
            "session_id": {
                "type": "string",
                "description": "Session ID"
            },
            "report_type": {
                "type": "string",
                "description": "Report type: 'summary', 'test', 'security', 'full'",
                "enum": ["summary", "test", "security", "full"]
            },
            "output_format": {
                "type": "string",
                "description": "Output format: 'markdown', 'html', 'json'",
                "enum": ["markdown", "html", "json"]
            },
            "title": {
                "type": "string",
                "description": "Report title"
            }
        },
        required=["session_id"]
    )
    async def export_report(
        self,
        session_id: str,
        report_type: str = "summary",
        output_format: str = "markdown",
        title: str = "Workspace Report"
    ) -> ToolResult:
        """Generate workspace report

        Args:
            session_id: Session ID
            report_type: Type of report
            output_format: Output format
            title: Report title

        Returns:
            Report generation result
        """
        return await self.sandbox.export_report(session_id, report_type, output_format, title)

    @tool(
        name="export_list",
        description="List available exports (archives and reports) for a session. Shows files in the exports directory with size and creation time.",
        parameters={
            "session_id": {
                "type": "string",
                "description": "Session ID"
            }
        },
        required=["session_id"]
    )
    async def export_list(self, session_id: str) -> ToolResult:
        """List available exports

        Args:
            session_id: Session ID

        Returns:
            List of available exports
        """
        return await self.sandbox.export_list(session_id)
