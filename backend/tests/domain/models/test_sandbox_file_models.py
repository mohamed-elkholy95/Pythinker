"""Tests for sandbox file operation domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.sandbox.file import (
    FileFindResult,
    FileReadResult,
    FileReplaceResult,
    FileSearchResult,
    FileUploadResult,
    FileWriteResult,
)


class TestFileReadResult:
    def test_required_fields(self) -> None:
        r = FileReadResult(content="hello world", file="/app/main.py")
        assert r.content == "hello world"
        assert r.file == "/app/main.py"

    def test_missing_content_raises(self) -> None:
        with pytest.raises(ValidationError):
            FileReadResult(file="/app/main.py")  # type: ignore[call-arg]


class TestFileWriteResult:
    def test_required_file(self) -> None:
        r = FileWriteResult(file="/app/out.txt")
        assert r.bytes_written is None

    def test_with_bytes_written(self) -> None:
        r = FileWriteResult(file="/app/out.txt", bytes_written=42)
        assert r.bytes_written == 42


class TestFileReplaceResult:
    def test_defaults(self) -> None:
        r = FileReplaceResult(file="/app/f.py")
        assert r.replaced_count == 0

    def test_with_count(self) -> None:
        r = FileReplaceResult(file="/app/f.py", replaced_count=5)
        assert r.replaced_count == 5


class TestFileSearchResult:
    def test_defaults(self) -> None:
        r = FileSearchResult(file="/app/f.py")
        assert r.matches == []
        assert r.line_numbers == []

    def test_with_matches(self) -> None:
        r = FileSearchResult(
            file="/app/f.py", matches=["line1", "line2"], line_numbers=[10, 20]
        )
        assert len(r.matches) == 2
        assert r.line_numbers == [10, 20]


class TestFileFindResult:
    def test_defaults(self) -> None:
        r = FileFindResult(path="/app")
        assert r.files == []

    def test_with_files(self) -> None:
        r = FileFindResult(path="/app", files=["a.py", "b.py"])
        assert len(r.files) == 2


class TestFileUploadResult:
    def test_required_fields(self) -> None:
        r = FileUploadResult(file_path="/tmp/upload.txt", file_size=1024, success=True)
        assert r.success is True
        assert r.file_size == 1024

    def test_failed_upload(self) -> None:
        r = FileUploadResult(file_path="/tmp/fail.txt", file_size=0, success=False)
        assert r.success is False
