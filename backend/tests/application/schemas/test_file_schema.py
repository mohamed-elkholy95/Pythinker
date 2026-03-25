from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.application.schemas.file import FileViewResponse


class TestFileViewResponse:
    def test_construction_with_both_fields(self) -> None:
        resp = FileViewResponse(content="print('hello')", file="main.py")
        assert resp.content == "print('hello')"
        assert resp.file == "main.py"

    def test_empty_content(self) -> None:
        resp = FileViewResponse(content="", file="empty.txt")
        assert resp.content == ""
        assert resp.file == "empty.txt"

    def test_empty_file_path(self) -> None:
        resp = FileViewResponse(content="data", file="")
        assert resp.file == ""

    def test_multiline_content(self) -> None:
        source = "line1\nline2\nline3\n"
        resp = FileViewResponse(content=source, file="script.py")
        assert resp.content == source

    def test_file_with_path_separator(self) -> None:
        resp = FileViewResponse(content="body", file="/home/user/project/src/main.py")
        assert resp.file == "/home/user/project/src/main.py"

    def test_missing_content_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FileViewResponse(file="main.py")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("content",) for e in errors)

    def test_missing_file_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FileViewResponse(content="some code")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("file",) for e in errors)

    def test_both_fields_missing_raises(self) -> None:
        with pytest.raises(ValidationError):
            FileViewResponse()  # type: ignore[call-arg]

    def test_serialization(self) -> None:
        resp = FileViewResponse(content="x = 1", file="vars.py")
        data = resp.model_dump()
        assert data == {"content": "x = 1", "file": "vars.py"}

    def test_json_round_trip(self) -> None:
        resp = FileViewResponse(content="y = 2", file="calc.py")
        json_str = resp.model_dump_json()
        restored = FileViewResponse.model_validate_json(json_str)
        assert restored.content == resp.content
        assert restored.file == resp.file

    def test_large_content(self) -> None:
        large = "a" * 100_000
        resp = FileViewResponse(content=large, file="big.txt")
        assert len(resp.content) == 100_000

    def test_unicode_content(self) -> None:
        resp = FileViewResponse(content="# مرحبا بالعالم\nprint('hello')", file="i18n.py")
        assert "مرحبا" in resp.content
