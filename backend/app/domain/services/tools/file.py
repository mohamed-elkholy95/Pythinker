import asyncio
import base64
import contextlib
import logging
import mimetypes
import re
import shlex
import time
from pathlib import Path

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)

# Supported image extensions for multimodal viewing
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

# Supported document extensions for viewing
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}

# Chart/data file extensions
DATA_EXTENSIONS = {".csv", ".json", ".xml", ".yaml", ".yml"}

_RECENT_WRITE_TTL_SECONDS = 300.0
_RECENT_WRITE_MAX_ENTRIES = 256
_SAME_FILE_WRITE_WINDOW_SECONDS = 180.0
_SAME_FILE_WRITE_WARN_THRESHOLD = 3
_REPORT_SANITIZE_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
_PLACEHOLDER_LINE_RE = re.compile(r"^\s*\[(?:\.\.\.|…)\]\s*$")
_LEADING_META_LINE_RE = re.compile(
    r"^\s*(?:"
    r"I see the issue"
    r"|I(?:'ll| will| have| am going to|'m going to) (?:now )?(?:write|save|create|prepare|compile|generate)"
    r"|Let me (?:now )?(?:write|save|create|prepare|compile|generate)"
    r"|Writing (?:the |this )?(?:report|content|file) to"
    r"|Saving (?:to|the) file"
    r")\b",
    re.IGNORECASE,
)
_DELIVERY_NOTE_RE = re.compile(
    r"^\s*>?\s*\*\*Note:\*\*\s*The model'?s output was cut off before completion\.[^\n]*(?:\n[^\n]*){0,2}\n?",
    re.IGNORECASE | re.MULTILINE,
)
_TRAILING_META_RE = re.compile(
    r"\n+(?:I see the issue|I(?:'ll| will| need to| should) (?:now )?save|"
    r"Let me (?:now )?save|Writing (?:the |this )?(?:report|content|file) to|"
    r"Saving (?:to|the) file|Note: The model(?:'s)? output was cut|"
    r"The (?:output|response|generation) was (?:cut|interrupted|truncated))"
    r"[^\n]*(?:\n[^\n]*)*$",
    re.IGNORECASE,
)


def _dedup_leading_lines(content: str) -> str:
    """Remove consecutive duplicate lines at the start of file content.

    LLMs sometimes repeat the title/header line when generating file content.
    This strips those duplicates while preserving the rest of the file.
    """
    if not content:
        return content

    lines = content.split("\n")
    if len(lines) < 2:
        return content

    # Check how many leading lines are identical to the first line
    first_line = lines[0].strip()
    if not first_line:
        return content

    dedup_end = 1
    while dedup_end < len(lines) and lines[dedup_end].strip() == first_line:
        dedup_end += 1

    if dedup_end > 1:
        # Keep only the first occurrence
        return "\n".join(lines[:1] + lines[dedup_end:])

    return content


def _should_sanitize_report_artifacts(file_path: str) -> bool:
    """Limit aggressive content sanitation to report-style text files."""
    return Path(file_path).suffix.lower() in _REPORT_SANITIZE_SUFFIXES


def _sanitize_written_content(file_path: str, content: str) -> str:
    """Remove common LLM write artifacts before persisting to disk."""
    if not content:
        return content

    cleaned = content.replace("\r\n", "\n")
    lines = [line for line in cleaned.split("\n") if not _PLACEHOLDER_LINE_RE.match(line)]
    cleaned = "\n".join(lines)

    if _should_sanitize_report_artifacts(file_path):
        report_lines = cleaned.split("\n")
        while report_lines and _LEADING_META_LINE_RE.match(report_lines[0]):
            report_lines.pop(0)
        cleaned = "\n".join(report_lines)
        cleaned = _DELIVERY_NOTE_RE.sub("", cleaned)
        cleaned = _TRAILING_META_RE.sub("", cleaned)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip("\n")


class FileTool(BaseTool):
    """File tool class, providing file operation functions.

    Enhanced with multimodal file viewing capabilities per Pythinker pattern.
    """

    name: str = "file"

    def __init__(self, sandbox: Sandbox, max_observe: int | None = None, session_id: str | None = None):
        """Initialize file tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 8000)
            session_id: Optional session ID for shell command execution (needed for PDF text extraction)
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox
        self._session_id = session_id
        # Paths written during this session — used to gate read-after-write retries.
        self._recently_written: dict[str, float] = {}
        # Byte sizes of recent writes — used to detect content regression.
        self._recent_write_sizes: dict[str, int] = {}
        # Same-file write history — used to detect overwrite loops.
        self._write_history: dict[str, list[float]] = {}
        # Paths blocked from file_write due to overwrite loop enforcement.
        self._overwrite_blocked_until: dict[str, float] = {}

    def _check_content_regression(self, path: str, new_content: str) -> str | None:
        """Return a warning string if new content is significantly smaller.

        Only checks non-trivial files (>500 bytes previous size) and flags
        when content shrinks by >40%. This catches cases where file_write
        (overwrite) loses content that file_str_replace (patch) would preserve.
        """
        new_size = len(new_content.encode("utf-8"))
        prev_size = self._recent_write_sizes.get(path)

        if prev_size is not None and prev_size > 500:
            shrink_ratio = new_size / prev_size
            if shrink_ratio < 0.5:
                error = (
                    f"ERROR: file_write to '{path}' would shrink content from "
                    f"{prev_size:,} to {new_size:,} bytes ({shrink_ratio:.0%}). "
                    f"Write BLOCKED. Use file_str_replace to patch instead."
                )
                logger.error(error)
                self._recent_write_sizes[path] = prev_size  # Don't update — preserve old size
                return error
            if shrink_ratio < 0.6:
                warning = (
                    f"WARNING: file_write to '{path}' shrinks content from "
                    f"{prev_size:,} to {new_size:,} bytes ({shrink_ratio:.0%}). "
                    f"Consider using file_str_replace to patch instead of overwrite."
                )
                logger.warning(warning)
                self._recent_write_sizes[path] = new_size
                return warning

        self._recent_write_sizes[path] = new_size
        return None

    def _prune_recent_writes(self) -> None:
        """Keep the write-tracking map bounded and fresh."""
        now = time.monotonic()
        expired = [path for path, ts in self._recently_written.items() if now - ts > _RECENT_WRITE_TTL_SECONDS]
        for path in expired:
            self._recently_written.pop(path, None)
            self._recent_write_sizes.pop(path, None)
            self._write_history.pop(path, None)

        overflow = len(self._recently_written) - _RECENT_WRITE_MAX_ENTRIES
        if overflow > 0:
            # Drop oldest entries first.
            for path, _ in sorted(self._recently_written.items(), key=lambda item: item[1])[:overflow]:
                self._recently_written.pop(path, None)
                self._recent_write_sizes.pop(path, None)
                self._write_history.pop(path, None)

    def _check_repetitive_overwrites(self, path: str, *, append: bool) -> str | None:
        """Return a warning/error when same file is overwritten repeatedly.

        After the 3rd overwrite within the window, blocks file_write for 120 seconds.
        """
        if append:
            return None

        now = time.monotonic()

        # Check if path is currently blocked
        blocked_until = self._overwrite_blocked_until.get(path, 0.0)
        if now < blocked_until:
            remaining = blocked_until - now
            return (
                f"ERROR: file_write BLOCKED for '{path}' for {remaining:.0f}s due to overwrite loop. "
                f"Use file_str_replace for incremental edits instead."
            )

        history = self._write_history.get(path, [])
        history = [ts for ts in history if now - ts <= _SAME_FILE_WRITE_WINDOW_SECONDS]
        history.append(now)
        self._write_history[path] = history

        if len(history) < _SAME_FILE_WRITE_WARN_THRESHOLD:
            return None

        # Block after 3rd overwrite for 120 seconds
        self._overwrite_blocked_until[path] = now + 120.0

        warning = (
            f"ERROR: file_write overwrite loop detected for '{path}' "
            f"({len(history)} overwrites within {_SAME_FILE_WRITE_WINDOW_SECONDS:.0f}s). "
            f"file_write is BLOCKED for 120s. Use file_str_replace for incremental edits."
        )
        logger.warning(warning)
        return warning

    @tool(
        name="file_read",
        description="Read file content. Use for checking file contents, analyzing logs, or reading configuration files.",
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to read"},
            "start_line": {"type": "integer", "description": "(Optional) Starting line to read from, 0-based"},
            "end_line": {"type": "integer", "description": "(Optional) Ending line number (exclusive)"},
            "sudo": {"type": "boolean", "description": "(Optional) Whether to use sudo privileges"},
        },
        required=["file"],
    )
    async def file_read(
        self, file: str, start_line: int | None = None, end_line: int | None = None, sudo: bool | None = False
    ) -> ToolResult:
        """Read file content

        Args:
            file: Absolute path of the file to read
            start_line: (Optional) Starting line, 0-based
            end_line: (Optional) Ending line (exclusive)
            sudo: (Optional) Whether to use sudo privileges

        Returns:
            File content
        """
        self._prune_recent_writes()
        result = await self.sandbox.file_read(file=file, start_line=start_line, end_line=end_line, sudo=sudo)

        # Handle short read-after-write races in sandbox file APIs.
        # Only retry when the path was recently written in this session —
        # avoids ~200ms wasted latency on intentional "does this file exist?" probes.
        if result.message and not result.success and file in self._recently_written:
            error_lower = result.message.lower()
            is_not_found = "404" in result.message or "not found" in error_lower or "no such file" in error_lower
            if is_not_found:
                for backoff in (0.05, 0.15):
                    await asyncio.sleep(backoff)
                    retry = await self.sandbox.file_read(
                        file=file,
                        start_line=start_line,
                        end_line=end_line,
                        sudo=sudo,
                    )
                    if retry.success:
                        result = retry
                        break

        # Handle structured error messages so the agent can make branch decisions
        if result.message and not result.success:
            error_lower = result.message.lower()
            if "404" in result.message or "not found" in error_lower or "no such file" in error_lower:
                result.message = f"File not found: {file}"
            elif "decode" in error_lower or "codec" in error_lower or "encoding" in error_lower:
                # Retry hint for binary/non-UTF-8 files
                result.message += " (Hint: This may be a binary file or use non-UTF-8 encoding.)"
        return result

    @tool(
        name="file_write",
        description="Overwrite or append content to a file. Use for creating new files, appending content, or modifying existing files.",
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to write to"},
            "content": {"type": "string", "description": "Text content to write"},
            "append": {"type": "boolean", "description": "(Optional) Whether to use append mode"},
            "leading_newline": {"type": "boolean", "description": "(Optional) Whether to add a leading newline"},
            "trailing_newline": {"type": "boolean", "description": "(Optional) Whether to add a trailing newline"},
            "sudo": {"type": "boolean", "description": "(Optional) Whether to use sudo privileges"},
        },
        required=["file", "content"],
    )
    async def file_write(
        self,
        file: str,
        content: str,
        append: bool | None = False,
        leading_newline: bool | None = False,
        trailing_newline: bool | None = False,
        sudo: bool | None = False,
    ) -> ToolResult:
        """Write content to file

        Args:
            file: Absolute path of the file to write to
            content: Text content to write
            append: (Optional) Whether to use append mode
            leading_newline: (Optional) Whether to add a leading newline
            trailing_newline: (Optional) Whether to add a trailing newline
            sudo: (Optional) Whether to use sudo privileges

        Returns:
            Write result
        """
        # Prepare content
        final_content = content

        # Dedup consecutive identical lines at the start of the file
        # (common LLM artifact: repeating the title/header line)
        if not append:
            final_content = _dedup_leading_lines(final_content)
            final_content = _sanitize_written_content(file, final_content)

        if leading_newline:
            final_content = "\n" + final_content
        if trailing_newline:
            final_content = final_content + "\n"

        # Check for content regression + overwrite loops before writing
        write_warnings: list[str] = []
        if not append:
            regression_warning = self._check_content_regression(file, final_content)
            if regression_warning:
                write_warnings.append(regression_warning)
        repetitive_warning = self._check_repetitive_overwrites(file, append=bool(append))
        if repetitive_warning:
            write_warnings.append(repetitive_warning)

        # Block write if enforcement triggered
        if any(w.startswith("ERROR") for w in write_warnings):
            return ToolResult(output="\n".join(write_warnings))

        # Directly call sandbox's file_write method, pass all parameters
        result = await self.sandbox.file_write(
            file=file,
            content=final_content,
            append=append,
            leading_newline=False,  # Already handled in final_content
            trailing_newline=False,  # Already handled in final_content
            sudo=sudo,
        )
        if result.success:
            self._recently_written[file] = time.monotonic()
            self._prune_recent_writes()
            # Surface write warnings in tool result so the LLM can self-correct.
            if write_warnings:
                warning_block = "\n\n".join(write_warnings)
                if result.message:
                    result.message = f"{result.message}\n\n{warning_block}"
                else:
                    result.message = warning_block
        return result

    @tool(
        name="file_str_replace",
        description="Replace specified string in a file. Use for updating specific content in files or fixing errors in code.",
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to perform replacement on"},
            "old_str": {"type": "string", "description": "Original string to be replaced"},
            "new_str": {"type": "string", "description": "New string to replace with"},
            "sudo": {"type": "boolean", "description": "(Optional) Whether to use sudo privileges"},
        },
        required=["file", "old_str", "new_str"],
    )
    async def file_str_replace(self, file: str, old_str: str, new_str: str, sudo: bool | None = False) -> ToolResult:
        """Replace specified string in file

        Args:
            file: Absolute path of the file to perform replacement on
            old_str: Original string to be replaced
            new_str: New string to replace with
            sudo: (Optional) Whether to use sudo privileges

        Returns:
            Replacement result
        """
        # Directly call sandbox's file_replace method
        return await self.sandbox.file_replace(file=file, old_str=old_str, new_str=new_str, sudo=sudo)

    @tool(
        name="file_find_in_content",
        description="Search for matching text within file content. Use for finding specific content or patterns in files.",
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to search within"},
            "regex": {"type": "string", "description": "Regular expression pattern to match"},
            "sudo": {"type": "boolean", "description": "(Optional) Whether to use sudo privileges"},
        },
        required=["file", "regex"],
    )
    async def file_find_in_content(self, file: str, regex: str, sudo: bool | None = False) -> ToolResult:
        """Search for matching text in file content

        Args:
            file: Absolute path of the file to search
            regex: Regular expression pattern for matching
            sudo: (Optional) Whether to use sudo privileges

        Returns:
            Search results
        """
        # Directly call sandbox's file_search method
        return await self.sandbox.file_search(file=file, regex=regex, sudo=sudo)

    @tool(
        name="file_find_by_name",
        description="Find files by name pattern in specified directory. Use for locating files with specific naming patterns.",
        parameters={
            "path": {"type": "string", "description": "Absolute path of directory to search"},
            "glob": {"type": "string", "description": "Filename pattern using glob syntax wildcards"},
        },
        required=["path", "glob"],
    )
    async def file_find_by_name(self, path: str, glob: str) -> ToolResult:
        """Find files by name pattern in specified directory

        Args:
            path: Absolute path of directory to search
            glob: Filename pattern using glob syntax wildcards

        Returns:
            Search results
        """
        # Directly call sandbox's file_find method
        return await self.sandbox.file_find(path=path, glob_pattern=glob)

    @tool(
        name="file_view",
        description=(
            "View and understand visual content (images, PDFs, charts, documents). "
            "Use this for analyzing images, reading PDF documents, understanding charts and graphs. "
            "Returns structured information about the visual content for further analysis."
        ),
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to view"},
            "page_range": {"type": "string", "description": "(Optional) Page range for PDFs (e.g., '1-5' or '1,3,5')"},
            "extract_text": {
                "type": "boolean",
                "description": "(Optional) Whether to extract text content from documents",
            },
            "analyze_charts": {
                "type": "boolean",
                "description": "(Optional) Whether to analyze charts/graphs in the file",
            },
        },
        required=["file"],
    )
    async def file_view(
        self,
        file: str,
        page_range: str | None = None,
        extract_text: bool = True,
        analyze_charts: bool = True,
    ) -> ToolResult:
        """View and understand visual content.

        Supports images, PDFs, and data files. Returns structured information
        about the content including:
        - File metadata (type, size, dimensions for images)
        - Extracted text content (for documents)
        - Base64 encoded content (for images, to pass to vision models)
        - Chart/graph analysis hints

        Args:
            file: Absolute path of the file to view
            page_range: Page range for PDFs (e.g., '1-5')
            extract_text: Whether to extract text content
            analyze_charts: Whether to analyze charts/graphs

        Returns:
            Structured view result with content and metadata
        """
        file_path = Path(file)
        extension = file_path.suffix.lower()

        # Get file metadata
        try:
            stat_result = await self.sandbox.file_stat(file)
            if not stat_result.success:
                return ToolResult(
                    success=False,
                    message=f"File not found or inaccessible: {file}",
                )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error accessing file: {e!s}",
            )

        # Detect content type
        content_type, _ = mimetypes.guess_type(file)
        if content_type is None:
            content_type = "application/octet-stream"

        result_data = {
            "file_path": file,
            "file_name": file_path.name,
            "extension": extension,
            "content_type": content_type,
            "file_type": self._categorize_file_type(extension),
        }

        # Handle different file types
        if extension in IMAGE_EXTENSIONS:
            return await self._view_image(file, result_data)
        if extension == ".pdf":
            return await self._view_pdf(file, page_range, extract_text, result_data)
        if extension in DATA_EXTENSIONS:
            return await self._view_data_file(file, analyze_charts, result_data)
        if extension in DOCUMENT_EXTENSIONS:
            return await self._view_document(file, extract_text, result_data)
        # Try to read as text
        return await self._view_text_file(file, result_data)

    def _categorize_file_type(self, extension: str) -> str:
        """Categorize file type from extension."""
        if extension in IMAGE_EXTENSIONS:
            return "image"
        if extension == ".pdf":
            return "pdf"
        if extension in DATA_EXTENSIONS:
            return "data"
        if extension in DOCUMENT_EXTENSIONS:
            return "document"
        return "text"

    async def _view_image(self, file: str, result_data: dict) -> ToolResult:
        """View an image file."""
        try:
            # Read file as binary
            read_result = await self.sandbox.file_read_binary(file)
            if not read_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to read image: {read_result.message}",
                )

            # Encode as base64
            if hasattr(read_result, "data") and read_result.data:
                binary_data = read_result.data
            else:
                # Fallback: try to read the content
                binary_data = read_result.result if isinstance(read_result.result, bytes) else b""

            if binary_data:
                base64_content = base64.b64encode(binary_data).decode("utf-8")
                result_data["base64_content"] = base64_content
                result_data["size_bytes"] = len(binary_data)

            result_text = (
                f"**Image File:** {result_data['file_name']}\n"
                f"**Type:** {result_data['content_type']}\n"
                f"**Size:** {result_data.get('size_bytes', 'unknown')} bytes\n\n"
                "Image content is available in base64 format for vision analysis. "
                "To understand the image content, pass it to a vision-capable model."
            )

            return ToolResult(
                success=True,
                message=result_text,
                data=result_data,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error viewing image: {e!s}",
            )

    async def _view_pdf(self, file: str, page_range: str | None, extract_text: bool, result_data: dict) -> ToolResult:
        """View a PDF file."""
        try:
            # Parse page range
            pages_to_extract = None
            if page_range:
                pages_to_extract = self._parse_page_range(page_range)

            result_data["page_range"] = page_range

            # Try to extract text using sandbox
            if extract_text:
                # Use shell command to extract text with pdftotext if available
                safe_file = shlex.quote(file)
                extract_cmd = f"pdftotext {safe_file} -"
                if pages_to_extract:
                    first_page = min(pages_to_extract)
                    last_page = max(pages_to_extract)
                    extract_cmd = f"pdftotext -f {first_page} -l {last_page} {safe_file} -"

                if self._session_id:
                    text_result = await self.sandbox.exec_command(self._session_id, "/", extract_cmd)
                    if text_result.success:
                        output = text_result.data if isinstance(text_result.data, str) else (text_result.message or "")
                        result_data["extracted_text"] = output[:10000]  # Limit text length

            # Get page count
            if self._session_id:
                page_count_cmd = f"pdfinfo {shlex.quote(file)} | grep 'Pages:' | awk '{{print $2}}'"
                page_result = await self.sandbox.exec_command(self._session_id, "/", page_count_cmd)
                if page_result.success:
                    output = page_result.data if isinstance(page_result.data, str) else (page_result.message or "")
                    if output.strip().isdigit():
                        result_data["page_count"] = int(output.strip())

            result_text = (
                f"**PDF Document:** {result_data['file_name']}\n**Pages:** {result_data.get('page_count', 'unknown')}\n"
            )

            if extract_text and result_data.get("extracted_text"):
                text_preview = result_data["extracted_text"][:1000]
                result_text += f"\n**Text Preview:**\n{text_preview}..."

            return ToolResult(
                success=True,
                message=result_text,
                data=result_data,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error viewing PDF: {e!s}",
            )

    async def _view_data_file(self, file: str, analyze_charts: bool, result_data: dict) -> ToolResult:
        """View a data file (CSV, JSON, etc.)."""
        try:
            # Read the file content
            read_result = await self.sandbox.file_read(file=file)
            if not read_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to read data file: {read_result.message}",
                )

            content = read_result.data or ""
            result_data["content_preview"] = content[:5000] if len(content) > 5000 else content

            extension = result_data["extension"]

            # Analyze based on type
            if extension == ".csv":
                result_data["data_type"] = "tabular"
                # Count rows and columns
                lines = content.strip().split("\n")
                result_data["row_count"] = len(lines)
                if lines:
                    result_data["column_count"] = len(lines[0].split(","))
                    result_data["headers"] = lines[0].split(",")

            elif extension == ".json":
                import json

                try:
                    parsed = json.loads(content)
                    result_data["data_type"] = "json"
                    if isinstance(parsed, list):
                        result_data["record_count"] = len(parsed)
                    elif isinstance(parsed, dict):
                        result_data["top_keys"] = list(parsed.keys())[:10]
                except json.JSONDecodeError:
                    result_data["data_type"] = "invalid_json"

            result_text = (
                f"**Data File:** {result_data['file_name']}\n**Type:** {result_data.get('data_type', extension)}\n"
            )

            if "row_count" in result_data:
                result_text += f"**Rows:** {result_data['row_count']}\n"
                result_text += f"**Columns:** {result_data.get('column_count', 'unknown')}\n"
                if result_data.get("headers"):
                    result_text += f"**Headers:** {', '.join(result_data['headers'][:5])}...\n"

            result_text += f"\n**Preview:**\n{result_data['content_preview'][:500]}..."

            return ToolResult(
                success=True,
                message=result_text,
                data=result_data,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error viewing data file: {e!s}",
            )

    async def _view_document(self, file: str, extract_text: bool, result_data: dict) -> ToolResult:
        """View a document file (Word, Excel, etc.)."""
        try:
            result_text = (
                f"**Document:** {result_data['file_name']}\n"
                f"**Type:** {result_data['content_type']}\n\n"
                "Document viewing requires conversion. Use appropriate tools to extract content."
            )

            return ToolResult(
                success=True,
                message=result_text,
                data=result_data,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error viewing document: {e!s}",
            )

    async def _view_text_file(self, file: str, result_data: dict) -> ToolResult:
        """View a text file."""
        try:
            read_result = await self.sandbox.file_read(file=file)
            if not read_result.success:
                return ToolResult(
                    success=False,
                    message=f"Failed to read file: {read_result.message}",
                )

            content = read_result.data or ""
            result_data["content_preview"] = content[:5000]
            result_data["line_count"] = content.count("\n") + 1

            result_text = (
                f"**Text File:** {result_data['file_name']}\n"
                f"**Lines:** {result_data['line_count']}\n\n"
                f"**Content:**\n{result_data['content_preview'][:1000]}..."
            )

            return ToolResult(
                success=True,
                message=result_text,
                data=result_data,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error viewing text file: {e!s}",
            )

    def _parse_page_range(self, page_range: str, max_page: int = 10000) -> list[int]:
        """Parse page range string into list of page numbers.

        Args:
            page_range: Page range string (e.g., '1-5' or '1,3,5')
            max_page: Maximum allowed page number (default: 10000)

        Returns:
            Sorted list of unique page numbers within bounds
        """
        pages: list[int] = []
        parts = page_range.replace(" ", "").split(",")

        for part in parts:
            if "-" in part:
                start_str, end_str = part.split("-", 1)
                with contextlib.suppress(ValueError):
                    start_val = max(1, min(int(start_str), max_page))
                    end_val = max(1, min(int(end_str), max_page))
                    pages.extend(range(start_val, end_val + 1))
            else:
                with contextlib.suppress(ValueError):
                    page_num = int(part)
                    if 1 <= page_num <= max_page:
                        pages.append(page_num)

        return sorted(set(pages))
