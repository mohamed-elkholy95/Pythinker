from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.interfaces.schemas.screenshot import ScreenshotListResponse, ScreenshotMetadataResponse


def _make_metadata(**overrides: object) -> ScreenshotMetadataResponse:
    """Return a valid ScreenshotMetadataResponse with sensible defaults."""
    defaults: dict[str, object] = {
        "id": "scr-001",
        "session_id": "sess-abc",
        "sequence_number": 1,
        "timestamp": 1711000000.0,
        "trigger": "tool_call",
        "size_bytes": 204800,
        "has_thumbnail": True,
    }
    defaults.update(overrides)
    return ScreenshotMetadataResponse(**defaults)  # type: ignore[arg-type]


class TestScreenshotMetadataResponse:
    def test_required_fields_only(self) -> None:
        meta = _make_metadata()
        assert meta.id == "scr-001"
        assert meta.session_id == "sess-abc"
        assert meta.sequence_number == 1
        assert meta.timestamp == 1711000000.0
        assert meta.trigger == "tool_call"
        assert meta.size_bytes == 204800
        assert meta.has_thumbnail is True

    def test_optional_tool_fields_default_to_none(self) -> None:
        meta = _make_metadata()
        assert meta.tool_call_id is None
        assert meta.tool_name is None
        assert meta.function_name is None
        assert meta.action_type is None

    def test_optional_tool_fields_can_be_set(self) -> None:
        meta = _make_metadata(
            tool_call_id="tc-999",
            tool_name="browser_navigate",
            function_name="navigate",
            action_type="navigate",
        )
        assert meta.tool_call_id == "tc-999"
        assert meta.tool_name == "browser_navigate"
        assert meta.function_name == "navigate"
        assert meta.action_type == "navigate"

    def test_has_thumbnail_false(self) -> None:
        meta = _make_metadata(has_thumbnail=False)
        assert meta.has_thumbnail is False

    def test_sequence_number_zero(self) -> None:
        meta = _make_metadata(sequence_number=0)
        assert meta.sequence_number == 0

    def test_large_size_bytes(self) -> None:
        meta = _make_metadata(size_bytes=10_000_000)
        assert meta.size_bytes == 10_000_000

    def test_missing_required_id_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ScreenshotMetadataResponse(
                session_id="sess-abc",
                sequence_number=1,
                timestamp=1711000000.0,
                trigger="manual",
                size_bytes=100,
                has_thumbnail=False,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("id",) for e in errors)

    def test_missing_required_session_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotMetadataResponse(
                id="scr-001",
                sequence_number=1,
                timestamp=1711000000.0,
                trigger="manual",
                size_bytes=100,
                has_thumbnail=False,
            )

    def test_missing_required_trigger_raises(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotMetadataResponse(
                id="scr-001",
                session_id="sess-abc",
                sequence_number=1,
                timestamp=1711000000.0,
                size_bytes=100,
                has_thumbnail=False,
            )

    def test_serialization_contains_all_fields(self) -> None:
        meta = _make_metadata(tool_call_id="tc-1")
        data = meta.model_dump()
        assert "id" in data
        assert "session_id" in data
        assert "sequence_number" in data
        assert "timestamp" in data
        assert "trigger" in data
        assert "size_bytes" in data
        assert "has_thumbnail" in data
        assert data["tool_call_id"] == "tc-1"

    def test_partial_optional_fields(self) -> None:
        meta = _make_metadata(tool_name="file_read")
        assert meta.tool_name == "file_read"
        assert meta.tool_call_id is None
        assert meta.function_name is None
        assert meta.action_type is None


class TestScreenshotListResponse:
    def test_empty_list(self) -> None:
        resp = ScreenshotListResponse(screenshots=[], total=0)
        assert resp.screenshots == []
        assert resp.total == 0

    def test_single_screenshot(self) -> None:
        meta = _make_metadata()
        resp = ScreenshotListResponse(screenshots=[meta], total=1)
        assert len(resp.screenshots) == 1
        assert resp.total == 1
        assert resp.screenshots[0].id == "scr-001"

    def test_multiple_screenshots(self) -> None:
        screenshots = [_make_metadata(id=f"scr-{i}", sequence_number=i) for i in range(5)]
        resp = ScreenshotListResponse(screenshots=screenshots, total=5)
        assert len(resp.screenshots) == 5
        assert resp.total == 5

    def test_total_can_differ_from_list_length(self) -> None:
        # total represents the overall count (pagination), not just this page
        meta = _make_metadata()
        resp = ScreenshotListResponse(screenshots=[meta], total=100)
        assert len(resp.screenshots) == 1
        assert resp.total == 100

    def test_missing_screenshots_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotListResponse(total=0)  # type: ignore[call-arg]

    def test_missing_total_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotListResponse(screenshots=[])  # type: ignore[call-arg]

    def test_serialization(self) -> None:
        meta = _make_metadata()
        resp = ScreenshotListResponse(screenshots=[meta], total=1)
        data = resp.model_dump()
        assert "screenshots" in data
        assert "total" in data
        assert isinstance(data["screenshots"], list)
        assert data["total"] == 1
