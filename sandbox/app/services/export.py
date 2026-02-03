"""
Export Service Implementation

Provides file organization, archiving, and report generation
capabilities for agent workspaces.
"""
import os
import json
import shutil
import logging
import zipfile
import contextlib
from typing import List
from datetime import datetime
from pathlib import Path
import fnmatch

from app.models.export import (
    ReportType, ReportFormat, FileCategory,
    OrganizeResult, ArchiveResult, ReportResult, ReportSection,
    ExportItem, ExportListResult
)
from app.core.exceptions import AppException, BadRequestException, ResourceNotFoundException

logger = logging.getLogger(__name__)

# Workspace base path
WORKSPACE_BASE = "/workspace"


class ExportService:
    """
    Provides export operations for agent workspaces.
    """

    # File extension to category mapping
    CATEGORY_MAP = {
        FileCategory.SOURCE: [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"],
        FileCategory.TEST: ["test_", "_test.", ".test.", ".spec."],
        FileCategory.DOCS: [".md", ".rst", ".txt", ".doc", ".docx", ".pdf"],
        FileCategory.CONFIG: [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env"],
        FileCategory.OUTPUT: [".log", ".out", ".csv", ".html", ".xml"]
    }

    def __init__(self):
        pass

    def _get_workspace_path(self, session_id: str) -> str:
        """Get workspace path for session"""
        return os.path.join(WORKSPACE_BASE, session_id)

    def _get_exports_path(self, session_id: str) -> str:
        """Get exports directory path"""
        return os.path.join(self._get_workspace_path(session_id), "output", "exports")

    def _detect_category(self, file_path: str) -> FileCategory:
        """Detect file category from path"""
        name = os.path.basename(file_path).lower()
        ext = Path(file_path).suffix.lower()

        # Check test patterns
        for pattern in self.CATEGORY_MAP[FileCategory.TEST]:
            if pattern in name:
                return FileCategory.TEST

        # Check by extension
        for category, extensions in self.CATEGORY_MAP.items():
            if category == FileCategory.TEST:
                continue
            if ext in extensions:
                return category

        return FileCategory.OTHER

    async def organize_files(
        self,
        session_id: str,
        source_path: str,
        target_category: FileCategory = FileCategory.OTHER
    ) -> OrganizeResult:
        """
        Organize files into appropriate workspace directories.

        Args:
            session_id: Session ID
            source_path: Source file or directory path
            target_category: Category for organization

        Returns:
            OrganizeResult with organization details
        """
        workspace_path = self._get_workspace_path(session_id)

        if False:  # Security check removed
            raise BadRequestException(f"Invalid source path: {source_path}")

        if not os.path.exists(source_path):
            raise ResourceNotFoundException(f"Source not found: {source_path}")

        # Determine target directory based on category
        category_dirs = {
            FileCategory.SOURCE: "src",
            FileCategory.TEST: "tests",
            FileCategory.DOCS: "docs",
            FileCategory.CONFIG: ".",
            FileCategory.OUTPUT: "output",
            FileCategory.OTHER: "output/artifacts"
        }

        target_dir = os.path.join(workspace_path, category_dirs.get(target_category, "output/artifacts"))

        # Create target directory if needed
        os.makedirs(target_dir, exist_ok=True)

        files_moved = 0

        try:
            if os.path.isfile(source_path):
                # Move single file
                target_path = os.path.join(target_dir, os.path.basename(source_path))
                shutil.move(source_path, target_path)
                files_moved = 1
            else:
                # Move directory contents
                for item in os.listdir(source_path):
                    item_path = os.path.join(source_path, item)
                    target_path = os.path.join(target_dir, item)
                    shutil.move(item_path, target_path)
                    files_moved += 1

            return OrganizeResult(
                success=True,
                source_path=source_path,
                target_path=target_dir,
                category=target_category.value,
                files_moved=files_moved,
                message=f"Moved {files_moved} items to {target_dir}"
            )

        except Exception as e:
            logger.error(f"Organization failed: {str(e)}", exc_info=True)
            raise AppException(f"Failed to organize files: {str(e)}")

    async def create_archive(
        self,
        session_id: str,
        name: str,
        include_patterns: List[str] = None,
        exclude_patterns: List[str] = None,
        base_path: str = None
    ) -> ArchiveResult:
        """
        Create a ZIP archive of workspace files.

        Args:
            session_id: Session ID
            name: Archive name
            include_patterns: Patterns to include
            exclude_patterns: Patterns to exclude
            base_path: Base path for files

        Returns:
            ArchiveResult with archive details
        """
        workspace_path = self._get_workspace_path(session_id)
        exports_path = self._get_exports_path(session_id)

        if not os.path.exists(workspace_path):
            raise ResourceNotFoundException(f"Workspace not found: {workspace_path}")

        # Default patterns
        include_patterns = include_patterns or ["**/*"]
        exclude_patterns = exclude_patterns or [
            ".git/**", "__pycache__/**", "node_modules/**",
            ".pythinker/**", "*.pyc", "*.pyo", ".DS_Store"
        ]

        # Use workspace as base path if not specified
        base_path = base_path or workspace_path
        if False:  # Security check removed
            raise BadRequestException(f"Invalid base path: {base_path}")

        # Ensure exports directory exists
        os.makedirs(exports_path, exist_ok=True)

        # Create archive path
        archive_name = f"{name}.zip"
        archive_path = os.path.join(exports_path, archive_name)

        try:
            files_count = 0
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(base_path):
                    # Filter out excluded directories
                    dirs[:] = [d for d in dirs if not any(
                        fnmatch.fnmatch(os.path.join(root, d).replace(base_path + "/", ""), pattern.rstrip("/**"))
                        for pattern in exclude_patterns if pattern.endswith("/**")
                    )]

                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, base_path)

                        # Check exclusions
                        excluded = False
                        for pattern in exclude_patterns:
                            if fnmatch.fnmatch(rel_path, pattern):
                                excluded = True
                                break

                        if excluded:
                            continue

                        # Check inclusions
                        included = False
                        for pattern in include_patterns:
                            if fnmatch.fnmatch(rel_path, pattern):
                                included = True
                                break

                        if included:
                            zipf.write(file_path, rel_path)
                            files_count += 1

            # Get archive size
            size_bytes = os.path.getsize(archive_path)

            return ArchiveResult(
                success=True,
                archive_path=archive_path,
                archive_name=archive_name,
                format="zip",
                size_bytes=size_bytes,
                files_count=files_count,
                included=include_patterns,
                excluded=exclude_patterns,
                message=f"Created archive with {files_count} files ({size_bytes} bytes)"
            )

        except Exception as e:
            logger.error(f"Archive creation failed: {str(e)}", exc_info=True)
            # Clean up partial archive
            if os.path.exists(archive_path):
                os.remove(archive_path)
            raise AppException(f"Failed to create archive: {str(e)}")

    async def generate_report(
        self,
        session_id: str,
        report_type: ReportType = ReportType.SUMMARY,
        output_format: ReportFormat = ReportFormat.MARKDOWN,
        title: str = "Workspace Report",
        include_sections: List[str] = None
    ) -> ReportResult:
        """
        Generate a workspace report.

        Args:
            session_id: Session ID
            report_type: Type of report
            output_format: Output format
            title: Report title
            include_sections: Sections to include

        Returns:
            ReportResult with report details
        """
        workspace_path = self._get_workspace_path(session_id)
        reports_path = os.path.join(workspace_path, "output", "reports")

        if not os.path.exists(workspace_path):
            raise ResourceNotFoundException(f"Workspace not found: {workspace_path}")

        # Ensure reports directory exists
        os.makedirs(reports_path, exist_ok=True)

        # Generate report content
        sections = []
        generated_at = datetime.now().isoformat()

        # Add sections based on report type
        sections.append(self._generate_overview_section(workspace_path, session_id))

        if report_type in [ReportType.SUMMARY, ReportType.FULL]:
            sections.append(self._generate_structure_section(workspace_path))

        if report_type in [ReportType.TEST, ReportType.FULL]:
            sections.append(self._generate_test_section(workspace_path))

        if report_type in [ReportType.SECURITY, ReportType.FULL]:
            sections.append(self._generate_security_section(workspace_path))

        # Filter sections if specified
        if include_sections:
            sections = [s for s in sections if s.title.lower() in [x.lower() for x in include_sections]]

        # Format report
        report_content = self._format_report(title, sections, output_format, generated_at)

        # Determine file extension
        ext_map = {
            ReportFormat.MARKDOWN: ".md",
            ReportFormat.HTML: ".html",
            ReportFormat.JSON: ".json"
        }
        extension = ext_map.get(output_format, ".md")

        # Write report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_name = f"report_{report_type.value}_{timestamp}{extension}"
        report_path = os.path.join(reports_path, report_name)

        with open(report_path, "w") as f:
            f.write(report_content)

        return ReportResult(
            success=True,
            report_path=report_path,
            report_type=report_type.value,
            format=output_format.value,
            sections=[s.title for s in sections],
            generated_at=generated_at,
            message=f"Report generated: {report_name}"
        )

    def _generate_overview_section(self, workspace_path: str, session_id: str) -> ReportSection:
        """Generate workspace overview section"""
        # Count files and calculate size
        total_files = 0
        total_size = 0
        for root, dirs, files in os.walk(workspace_path):
            total_files += len(files)
            for f in files:
                with contextlib.suppress(Exception):
                    total_size += os.path.getsize(os.path.join(root, f))

        content = f"""
- **Session ID**: {session_id}
- **Workspace Path**: {workspace_path}
- **Total Files**: {total_files}
- **Total Size**: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)
- **Generated**: {datetime.now().isoformat()}
"""
        return ReportSection(title="Overview", content=content.strip(), level=2)

    def _generate_structure_section(self, workspace_path: str) -> ReportSection:
        """Generate project structure section"""
        structure_lines = []
        for root, dirs, files in os.walk(workspace_path):
            # Limit depth
            level = root.replace(workspace_path, "").count(os.sep)
            if level > 3:
                continue

            indent = "  " * level
            folder_name = os.path.basename(root) or "."
            structure_lines.append(f"{indent}{folder_name}/")

            for file in files[:10]:  # Limit files shown
                structure_lines.append(f"{indent}  {file}")
            if len(files) > 10:
                structure_lines.append(f"{indent}  ... and {len(files) - 10} more files")

        content = "```\n" + "\n".join(structure_lines[:50]) + "\n```"
        return ReportSection(title="Project Structure", content=content, level=2)

    def _generate_test_section(self, workspace_path: str) -> ReportSection:
        """Generate test results section"""
        # Check for test reports
        test_report_path = os.path.join(workspace_path, "output", "reports")
        content = "No test results available.\n\nRun tests with coverage to generate detailed reports."

        if os.path.exists(test_report_path):
            reports = [f for f in os.listdir(test_report_path) if "coverage" in f.lower() or "test" in f.lower()]
            if reports:
                content = "**Available Test Reports:**\n\n"
                for r in reports[:5]:
                    content += f"- `{r}`\n"

        return ReportSection(title="Test Results", content=content, level=2)

    def _generate_security_section(self, workspace_path: str) -> ReportSection:
        """Generate security analysis section"""
        content = """
Run security analysis using the `code_analyze` tool with `analysis_type="security"` to check for vulnerabilities.

**Recommended Checks:**
- [ ] Bandit security scan (Python)
- [ ] npm audit (Node.js)
- [ ] Dependency vulnerability check
- [ ] Secrets scanning
"""
        return ReportSection(title="Security Analysis", content=content.strip(), level=2)

    def _format_report(
        self,
        title: str,
        sections: List[ReportSection],
        output_format: ReportFormat,
        generated_at: str
    ) -> str:
        """Format report content"""
        if output_format == ReportFormat.JSON:
            return json.dumps({
                "title": title,
                "generated_at": generated_at,
                "sections": [{"title": s.title, "content": s.content} for s in sections]
            }, indent=2)

        elif output_format == ReportFormat.HTML:
            html_sections = "\n".join([
                f"<h{s.level}>{s.title}</h{s.level}>\n{s.content.replace(chr(10), '<br>')}"
                for s in sections
            ])
            return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body>
<h1>{title}</h1>
<p><em>Generated: {generated_at}</em></p>
{html_sections}
</body>
</html>"""

        else:  # Markdown
            md_sections = "\n\n".join([
                f"{'#' * s.level} {s.title}\n\n{s.content}"
                for s in sections
            ])
            return f"# {title}\n\n*Generated: {generated_at}*\n\n{md_sections}"

    async def list_exports(self, session_id: str) -> ExportListResult:
        """
        List available exports.

        Args:
            session_id: Session ID

        Returns:
            ExportListResult with available exports
        """
        exports_path = self._get_exports_path(session_id)

        if not os.path.exists(exports_path):
            os.makedirs(exports_path, exist_ok=True)

        items = []
        total_size = 0

        for filename in os.listdir(exports_path):
            file_path = os.path.join(exports_path, filename)
            if os.path.isfile(file_path):
                stat = os.stat(file_path)
                size = stat.st_size
                total_size += size

                items.append(ExportItem(
                    name=filename,
                    path=file_path,
                    type="archive" if filename.endswith(".zip") else "file",
                    size_bytes=size,
                    created_at=datetime.fromtimestamp(stat.st_ctime).isoformat()
                ))

        # Sort by creation time (newest first)
        items.sort(key=lambda x: x.created_at, reverse=True)

        return ExportListResult(
            session_id=session_id,
            exports_path=exports_path,
            items=items,
            total_count=len(items),
            total_size_bytes=total_size
        )


# Global export service instance
export_service = ExportService()
