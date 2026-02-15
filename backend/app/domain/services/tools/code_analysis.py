"""Code Analysis Tools - Document Segmentation & Implementation Tracking

Provides agents with capabilities to:
1. Segment long documents into manageable chunks
2. Track code implementation progress across files
3. Validate code completeness

Context7 validated: Tool interface pattern, Pydantic v2, singleton usage.
"""

import logging

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import tool

logger = logging.getLogger(__name__)


class CodeAnalysisTool:
    """Tools for code analysis: segmentation and completeness tracking.

    Context7 validated: Tool class pattern with @tool decorators.
    """

    def __init__(self, sandbox: Sandbox):
        """Initialize code analysis tools.

        Args:
            sandbox: Sandbox instance for file operations
        """
        self.sandbox = sandbox

    @tool(
        name="segment_document",
        description=(
            "Segment a long document/code file into manageable chunks with boundary preservation. "
            "Useful for processing large files without losing context. "
            "Automatically detects document type (Python, Markdown, JSON, Text) and respects "
            "function/class boundaries (Python) or heading boundaries (Markdown)."
        ),
        parameters={
            "file": {"type": "string", "description": "Absolute path to the file to segment"},
            "max_chunk_lines": {
                "type": "integer",
                "description": "(Optional) Maximum lines per chunk (default: 200)",
            },
            "overlap_lines": {
                "type": "integer",
                "description": "(Optional) Context overlap between chunks (default: 10)",
            },
            "strategy": {
                "type": "string",
                "description": (
                    "(Optional) Chunking strategy: 'semantic' (respects boundaries, default), "
                    "'fixed_size' (simple line-based), or 'hybrid' (semantic with fallback)"
                ),
            },
        },
        required=["file"],
    )
    async def segment_document(
        self,
        file: str,
        max_chunk_lines: int | None = 200,
        overlap_lines: int | None = 10,
        strategy: str | None = "semantic",
    ) -> ToolResult:
        """Segment a document into chunks with boundary preservation.

        Args:
            file: Absolute path to the file
            max_chunk_lines: Maximum lines per chunk
            overlap_lines: Context overlap between chunks
            strategy: Chunking strategy (semantic/fixed_size/hybrid)

        Returns:
            ToolResult with chunk metadata

        Context7 validated: Async tool pattern, error handling.
        """
        try:
            from app.domain.services.agents.document_segmenter import (
                ChunkingStrategy,
                SegmentationConfig,
                get_document_segmenter,
            )

            # Read file content
            file_result = await self.sandbox.file_read(file=file)
            if not file_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to read file: {file_result.message}",
                )

            content = file_result.message

            # Parse strategy
            strategy_map = {
                "semantic": ChunkingStrategy.SEMANTIC,
                "fixed_size": ChunkingStrategy.FIXED_SIZE,
                "hybrid": ChunkingStrategy.HYBRID,
            }
            chunk_strategy = strategy_map.get(strategy or "semantic", ChunkingStrategy.SEMANTIC)

            # Configure segmenter
            config = SegmentationConfig(
                max_chunk_lines=max_chunk_lines or 200,
                overlap_lines=overlap_lines or 10,
                strategy=chunk_strategy,
            )

            segmenter = get_document_segmenter(config)

            # Segment document
            result = segmenter.segment(content)

            # Format chunks for output
            chunks_info = [
                {
                    "index": chunk.chunk_index + 1,
                    "total": chunk.total_chunks,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "line_count": chunk.end_line - chunk.start_line + 1,
                    "type": chunk.chunk_type,
                    "content_preview": chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content,
                }
                for chunk in result.chunks
            ]

            output = {
                "file": file,
                "document_type": result.document_type.value,
                "total_lines": result.total_lines,
                "total_chunks": len(result.chunks),
                "boundaries_preserved": result.boundaries_preserved,
                "strategy_used": result.strategy_used.value,
                "chunks": chunks_info,
            }

            message = (
                f"Segmented {file} into {len(result.chunks)} chunks "
                f"({result.document_type.value}, {result.total_lines} lines, "
                f"{result.boundaries_preserved} boundaries preserved)"
            )

            return ToolResult(success=True, message=message, data=output)

        except Exception as e:
            logger.error(f"Document segmentation failed: {e}", exc_info=True)
            return ToolResult(success=False, message=f"Segmentation error: {e!s}")

    @tool(
        name="track_implementation",
        description=(
            "Track code implementation completeness across one or more files. "
            "Detects incomplete implementations (TODO, FIXME, NotImplementedError, empty functions) "
            "and generates a completion checklist. Useful for validating multi-file code generation."
        ),
        parameters={
            "files": {
                "type": "array",
                "description": "List of absolute file paths to analyze",
                "items": {"type": "string"},
            },
            "check_todos": {
                "type": "boolean",
                "description": "(Optional) Check for TODO markers (default: true)",
            },
            "check_fixmes": {
                "type": "boolean",
                "description": "(Optional) Check for FIXME markers (default: true)",
            },
            "check_empty_functions": {
                "type": "boolean",
                "description": "(Optional) Check for empty function bodies (default: true)",
            },
        },
        required=["files"],
    )
    async def track_implementation(
        self,
        files: list[str],
        check_todos: bool | None = True,
        check_fixmes: bool | None = True,
        check_empty_functions: bool | None = True,
    ) -> ToolResult:
        """Track implementation completeness across multiple files.

        Args:
            files: List of file paths to analyze
            check_todos: Whether to check for TODO markers
            check_fixmes: Whether to check for FIXME markers
            check_empty_functions: Whether to check for empty functions

        Returns:
            ToolResult with completeness report

        Context7 validated: Multi-file analysis, comprehensive reporting.
        """
        try:
            from app.domain.services.agents.implementation_tracker import (
                ImplementationConfig,
                get_implementation_tracker,
            )

            # Configure tracker
            config = ImplementationConfig(
                check_todos=check_todos if check_todos is not None else True,
                check_fixmes=check_fixmes if check_fixmes is not None else True,
                check_empty_functions=check_empty_functions if check_empty_functions is not None else True,
            )

            tracker = get_implementation_tracker(config)

            # Read all files
            file_contents: dict[str, str] = {}
            for file_path in files:
                file_result = await self.sandbox.file_read(file=file_path)
                if file_result.success:
                    file_contents[file_path] = file_result.message
                else:
                    logger.warning(f"Failed to read {file_path}: {file_result.message}")

            if not file_contents:
                return ToolResult(
                    success=False,
                    message="No files could be read",
                )

            # Track implementation
            report = tracker.track_multiple(file_contents)

            # Format output
            file_summaries = [
                {
                    "file": file_status.file_path,
                    "status": file_status.status.value,
                    "completeness": f"{file_status.completeness_score:.0%}",
                    "issues": len(file_status.issues),
                    "functions": f"{file_status.complete_functions}/{file_status.total_functions}",
                    "classes": f"{file_status.complete_classes}/{file_status.total_classes}",
                }
                for file_status in report.files
            ]

            # High priority issues
            high_priority_details = [
                {
                    "file": issue.file_path,
                    "line": issue.line_number,
                    "reason": issue.reason.value,
                    "snippet": issue.code_snippet,
                    "suggestion": issue.suggestion,
                }
                for issue in report.high_priority_issues[:5]  # Top 5
            ]

            output = {
                "overall_status": report.overall_status.value,
                "overall_completeness": f"{report.completeness_score:.0%}",
                "total_issues": report.total_issues,
                "high_priority_issues": len(report.high_priority_issues),
                "files_analyzed": len(report.files),
                "file_summaries": file_summaries,
                "high_priority_details": high_priority_details,
                "completion_checklist": report.completion_checklist,
            }

            # Generate summary message
            complete_count = sum(1 for f in report.files if f.status.value == "complete")
            message = (
                f"Implementation Status: {report.overall_status.value.upper()} "
                f"({report.completeness_score:.0%} complete)\n"
                f"Files: {complete_count}/{len(report.files)} complete, "
                f"{report.total_issues} total issues, "
                f"{len(report.high_priority_issues)} high priority\n\n"
                f"Completion Checklist:\n" + "\n".join(report.completion_checklist[:10])
            )

            return ToolResult(success=True, message=message, data=output)

        except Exception as e:
            logger.error(f"Implementation tracking failed: {e}", exc_info=True)
            return ToolResult(success=False, message=f"Tracking error: {e!s}")


def create_code_analysis_tool(sandbox: Sandbox) -> CodeAnalysisTool:
    """Factory function to create CodeAnalysisTool.

    Args:
        sandbox: Sandbox instance

    Returns:
        CodeAnalysisTool instance

    Context7 validated: Factory pattern for tool creation.
    """
    return CodeAnalysisTool(sandbox)
