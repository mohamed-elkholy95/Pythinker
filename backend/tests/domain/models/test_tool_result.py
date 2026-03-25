"""Tests for ToolResult generic model."""

from app.domain.models.tool_result import ToolResult


class TestToolResult:
    def test_ok(self) -> None:
        r = ToolResult.ok(message="Done", data={"count": 5})
        assert r.success is True
        assert r.message == "Done"
        assert r.data == {"count": 5}

    def test_ok_minimal(self) -> None:
        r = ToolResult.ok()
        assert r.success is True
        assert r.message is None
        assert r.data is None

    def test_error(self) -> None:
        r = ToolResult.error("Something failed")
        assert r.success is False
        assert r.message == "Something failed"

    def test_error_with_data(self) -> None:
        r = ToolResult.error("Timeout", data={"elapsed_ms": 30000})
        assert r.data == {"elapsed_ms": 30000}

    def test_suggested_filename(self) -> None:
        r = ToolResult(success=True, suggested_filename="report.md")
        assert r.suggested_filename == "report.md"

    def test_generic_type(self) -> None:
        r = ToolResult[list[str]](success=True, data=["a", "b"])
        assert r.data == ["a", "b"]
