"""
File Operation Service Implementation - Async Version
"""

import logging
import os
import re
import glob
import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.models.file import (
    FileReadResult,
    FileWriteResult,
    FileReplaceResult,
    FileSearchResult,
    FileFindResult,
    FileUploadResult,
    FileDeleteResult,
    FileListEntry,
    FileListResult,
)
from app.core.exceptions import (
    AppException,
    ResourceNotFoundException,
    BadRequestException,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# Directory trees that file operations are allowed to touch.
# Path.resolve() is used so symlinks cannot bypass these boundaries.
SANDBOX_ALLOWED_DIRS: list[Path] = [
    Path("/home/ubuntu"),
    Path("/workspace"),
]


def safe_resolve(path: str, allowed_dirs: Optional[list[Path]] = None) -> str:
    """Resolve *path* to an absolute, canonical path and verify it lives under an allowed directory.

    Security guarantees:
      - Collapses ``..`` sequences and resolves symlinks via ``Path.resolve()``.
      - Rejects any result that is not equal to, or a child of, any allowed dir.
      - Logs every rejected attempt at WARNING level for audit.

    Args:
        path: The file path to validate.
        allowed_dirs: The allowed base directories.  Defaults to the module-level
            ``SANDBOX_ALLOWED_DIRS`` when ``None``.  The default is resolved at
            call time (not import time) so that monkeypatching works in tests.

    Returns the resolved path as a ``str`` on success.
    Raises ``BadRequestException`` on path-traversal attempts.
    """
    if allowed_dirs is None:
        allowed_dirs = SANDBOX_ALLOWED_DIRS
    resolved = Path(path).resolve()

    for base_dir in allowed_dirs:
        base_resolved = base_dir.resolve()
        if resolved == base_resolved or resolved.is_relative_to(base_resolved):
            return str(resolved)

    allowed_str = ", ".join(str(d) for d in allowed_dirs)
    logger.warning(
        "Path traversal blocked: input=%r resolved=%s allowed=%s",
        path,
        resolved,
        allowed_str,
    )
    raise BadRequestException(
        f"Path traversal denied: path must be within one of: {allowed_str}"
    )


class FileService:
    """File Operation Service"""

    _HOME_ALIAS_FROM = "/home/user"
    _HOME_ALIAS_TO = "/home/ubuntu"

    def _resolve_home_alias(self, path: str) -> str:
        """Translate legacy home path aliases to the sandbox user home."""
        if path == self._HOME_ALIAS_FROM:
            return self._HOME_ALIAS_TO
        if path.startswith(f"{self._HOME_ALIAS_FROM}/"):
            suffix = path[len(self._HOME_ALIAS_FROM) + 1 :]
            return f"{self._HOME_ALIAS_TO}/{suffix}"
        return path

    def _normalize_path(self, path: str) -> str:
        """Normalize and validate that *path* resolves within an allowed directory.

        Steps:
          1. Translate legacy ``/home/user`` alias to ``/home/ubuntu``.
          2. Convert relative paths to absolute (relative to cwd).
          3. Resolve symlinks and ``..`` via ``Path.resolve()``.
          4. Reject any path outside ``SANDBOX_ALLOWED_DIRS``.

        Raises ``BadRequestException`` on path-traversal attempts.
        """
        resolved = self._resolve_home_alias(path)
        if not os.path.isabs(resolved):
            resolved = os.path.abspath(resolved)
        return safe_resolve(resolved)

    async def read_file(
        self,
        file: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        sudo: bool = False,
        max_length: Optional[int] = 10000,
    ) -> FileReadResult:
        """
        Asynchronously read file content

        Args:
            file: Absolute file path
            start_line: Starting line (0-based)
            end_line: Ending line (not included)
            sudo: Whether to use sudo privileges
        """
        file = self._normalize_path(file)
        if sudo and not settings.ALLOW_SUDO:
            raise BadRequestException("sudo is not allowed in this sandbox")
        # Check if file exists
        if not os.path.exists(file) and not sudo:
            logger.info("File read miss: %s", file)
            raise ResourceNotFoundException(f"File does not exist: {file}")

        try:
            content = ""

            # Read with sudo
            if sudo:
                command = f"sudo cat '{file}'"
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    raise BadRequestException(f"Failed to read file: {stderr.decode()}")

                content = stdout.decode("utf-8")
            else:
                # Asynchronously read file
                def read_file_async():
                    try:
                        with open(file, "r", encoding="utf-8") as f:
                            return f.read()
                    except Exception as e:
                        raise AppException(message=f"Failed to read file: {str(e)}")

                # Execute IO operation in thread pool
                content = await asyncio.to_thread(read_file_async)

            # Process line range
            if start_line is not None or end_line is not None:
                lines = content.splitlines()
                start = start_line if start_line is not None else 0
                end = end_line if end_line is not None else len(lines)
                content = "\n".join(lines[start:end])

            if max_length is not None and max_length > 0 and len(content) > max_length:
                content = content[:max_length] + "(truncated)"

            return FileReadResult(content=content, file=file)
        except Exception as e:
            if isinstance(e, BadRequestException) or isinstance(
                e, ResourceNotFoundException
            ):
                raise e
            raise AppException(message=f"Failed to read file: {str(e)}")

    async def write_file(
        self,
        file: str,
        content: str,
        append: bool = False,
        leading_newline: bool = False,
        trailing_newline: bool = False,
        sudo: bool = False,
    ) -> FileWriteResult:
        """
        Asynchronously write file content

        Args:
            file: Absolute file path
            content: Content to write
            append: Whether to append mode
            leading_newline: Whether to add a leading newline
            trailing_newline: Whether to add a trailing newline
            sudo: Whether to use sudo privileges
        """
        try:
            file = self._normalize_path(file)
            if sudo and not settings.ALLOW_SUDO:
                raise BadRequestException("sudo is not allowed in this sandbox")
            # Prepare content
            if leading_newline:
                content = "\n" + content
            if trailing_newline:
                content = content + "\n"

            bytes_written = 0

            # Write with sudo
            if sudo:
                mode = ">>" if append else ">"
                parent_dir = os.path.dirname(file)
                if parent_dir and not os.path.exists(parent_dir):
                    mkdir_cmd = f"sudo mkdir -p '{parent_dir}'"
                    mkdir_proc = await asyncio.create_subprocess_shell(
                        mkdir_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, mkdir_err = await mkdir_proc.communicate()
                    if mkdir_proc.returncode != 0:
                        raise BadRequestException(
                            f"Failed to create directory: {mkdir_err.decode()}"
                        )
                # Create secure temporary file
                fd, temp_file = tempfile.mkstemp(prefix="file_write_", suffix=".tmp")
                try:
                    # Asynchronously write to temporary file
                    def write_temp_file():
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(content)
                        return len(content.encode("utf-8"))

                    bytes_written = await asyncio.to_thread(write_temp_file)

                    # Use sudo to write temporary file content to target file
                    command = f"sudo bash -c \"cat {temp_file} {mode} '{file}'\""
                    process = await asyncio.create_subprocess_shell(
                        command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise BadRequestException(
                            f"Failed to write file: {stderr.decode()}"
                        )
                finally:
                    # Clean up temporary file
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
            else:
                # Ensure directory exists
                parent_dir = os.path.dirname(file)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)

                # Asynchronously write file
                def write_file_async():
                    mode = "a" if append else "w"
                    with open(file, mode, encoding="utf-8") as f:
                        return f.write(content)

                bytes_written = await asyncio.to_thread(write_file_async)

            return FileWriteResult(file=file, bytes_written=bytes_written)
        except Exception as e:
            if isinstance(e, BadRequestException):
                raise e
            raise AppException(message=f"Failed to write file: {str(e)}")

    async def str_replace(
        self, file: str, old_str: str, new_str: str, sudo: bool = False
    ) -> FileReplaceResult:
        """
        Asynchronously replace string in file

        Args:
            file: Absolute file path
            old_str: Original string to be replaced
            new_str: New replacement string
            sudo: Whether to use sudo privileges
        """
        file = self._normalize_path(file)
        if sudo and not settings.ALLOW_SUDO:
            raise BadRequestException("sudo is not allowed in this sandbox")
        # First read file content
        file_result = await self.read_file(file, sudo=sudo)
        content = file_result.content

        # Calculate replacement count
        replaced_count = content.count(old_str)
        if replaced_count == 0:
            return FileReplaceResult(file=file, replaced_count=0)

        # Perform replacement
        new_content = content.replace(old_str, new_str)

        # Write back to file
        await self.write_file(file, new_content, sudo=sudo)

        return FileReplaceResult(file=file, replaced_count=replaced_count)

    async def find_in_content(
        self, file: str, regex: str, sudo: bool = False
    ) -> FileSearchResult:
        """
        Asynchronously search in file content

        Args:
            file: Absolute file path
            regex: Regular expression pattern
            sudo: Whether to use sudo privileges
        """
        file = self._normalize_path(file)
        if sudo and not settings.ALLOW_SUDO:
            raise BadRequestException("sudo is not allowed in this sandbox")
        # Read file
        file_result = await self.read_file(file, sudo=sudo)
        content = file_result.content

        # Process line by line
        lines = content.splitlines()
        matches = []
        line_numbers = []

        # Compile regular expression with length guard to prevent ReDoS
        max_regex_len = 1000
        if len(regex) > max_regex_len:
            raise BadRequestException(
                f"Regular expression too long ({len(regex)} chars, max {max_regex_len})"
            )
        try:
            pattern = re.compile(regex)
        except Exception as e:
            raise BadRequestException(f"Invalid regular expression: {str(e)}")

        # Find matches with timeout to prevent ReDoS hangs
        def process_lines():
            nonlocal matches, line_numbers
            for i, line in enumerate(lines):
                if pattern.search(line):
                    matches.append(line)
                    line_numbers.append(i)

        try:
            await asyncio.wait_for(asyncio.to_thread(process_lines), timeout=30.0)
        except asyncio.TimeoutError:
            raise BadRequestException(
                "Regex search timed out — pattern may be too complex"
            )

        return FileSearchResult(file=file, matches=matches, line_numbers=line_numbers)

    async def find_by_name(self, path: str, glob_pattern: str) -> FileFindResult:
        """
        Asynchronously find files by name pattern

        Args:
            path: Directory path to search
            glob_pattern: File name pattern (glob syntax)
        """
        path = self._normalize_path(path)
        # Check if path exists
        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Directory does not exist: {path}")

        # Asynchronously find files
        def glob_async():
            search_pattern = os.path.join(path, glob_pattern)
            return glob.glob(search_pattern, recursive=True)

        files = await asyncio.to_thread(glob_async)

        return FileFindResult(path=path, files=files)

    async def upload_file(self, path: str, file_stream: UploadFile) -> FileUploadResult:
        """
        Upload file using streaming for large files

        Args:
            path: Target file path to save uploaded file
            file_stream: File stream from FastAPI UploadFile
        """
        try:
            path = self._normalize_path(path)
            chunk_size = 8192  # 8KB chunks
            total_size = 0

            # Ensure directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)

            # Stream write directly to target file
            def write_stream_direct():
                nonlocal total_size
                with open(path, "wb") as f:
                    while True:
                        chunk = file_stream.file.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        total_size += len(chunk)

            await asyncio.to_thread(write_stream_direct)

            return FileUploadResult(file_path=path, file_size=total_size, success=True)
        except Exception as e:
            if isinstance(e, (BadRequestException, ResourceNotFoundException)):
                raise e
            raise AppException(message=f"Failed to upload file: {str(e)}")

    async def delete_file(self, path: str, sudo: bool = False) -> FileDeleteResult:
        """
        Delete a file or directory.

        Args:
            path: Target path to delete
            sudo: Whether to use sudo privileges
        """
        path = self._normalize_path(path)
        if sudo and not settings.ALLOW_SUDO:
            raise BadRequestException("sudo is not allowed in this sandbox")
        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Path does not exist: {path}")

        try:
            if sudo:
                command = f"sudo rm -rf -- '{path}'"
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await process.communicate()
                if process.returncode != 0:
                    raise BadRequestException(f"Failed to delete path: {stderr.decode()}")
            else:
                if os.path.isdir(path):
                    await asyncio.to_thread(shutil.rmtree, path)
                else:
                    await asyncio.to_thread(os.remove, path)

            return FileDeleteResult(path=path, deleted=True)
        except Exception as e:
            if isinstance(e, (BadRequestException, ResourceNotFoundException)):
                raise e
            raise AppException(message=f"Failed to delete path: {str(e)}")

    async def list_dir(self, path: str, include_hidden: bool = False) -> FileListResult:
        """
        List entries in a directory.

        Args:
            path: Directory path
            include_hidden: Whether to include dot-prefixed entries
        """
        path = self._normalize_path(path)
        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Directory does not exist: {path}")
        if not os.path.isdir(path):
            raise BadRequestException(f"Path is not a directory: {path}")

        def _list_entries() -> list[FileListEntry]:
            entries: list[FileListEntry] = []
            for entry in sorted(os.scandir(path), key=lambda item: item.name.lower()):
                if not include_hidden and entry.name.startswith("."):
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                size = 0 if is_dir else int(entry.stat(follow_symlinks=False).st_size)
                entries.append(
                    FileListEntry(
                        name=entry.name,
                        path=entry.path,
                        is_dir=is_dir,
                        size_bytes=size,
                    )
                )
            return entries

        try:
            entries = await asyncio.to_thread(_list_entries)
            return FileListResult(path=path, entries=entries)
        except Exception as e:
            if isinstance(e, (BadRequestException, ResourceNotFoundException)):
                raise e
            raise AppException(message=f"Failed to list directory: {str(e)}")

    def ensure_file(self, path: str) -> None:
        """
        Ensure file exists

        Args:
            path: Path of the file to check
        """
        try:
            path = self._normalize_path(path)
            # Check if file exists
            if not os.path.exists(path):
                raise ResourceNotFoundException(f"File does not exist: {path}")

        except Exception as e:
            if isinstance(e, (BadRequestException, ResourceNotFoundException)):
                raise e
            raise AppException(message=f"Failed to ensure file: {str(e)}")


# Service instance
file_service = FileService()
