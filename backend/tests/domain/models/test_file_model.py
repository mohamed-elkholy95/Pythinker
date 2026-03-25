"""Tests for FileInfo domain model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.file import FileInfo


# ---------------------------------------------------------------------------
# Required field — filename
# ---------------------------------------------------------------------------

def test_file_info_requires_filename():
    """Constructing FileInfo without filename raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        FileInfo()  # type: ignore[call-arg]
    errors = exc_info.value.errors()
    field_names = [e["loc"][0] for e in errors]
    assert "filename" in field_names


def test_file_info_minimal_construction():
    """FileInfo can be constructed with only the required filename."""
    fi = FileInfo(filename="report.pdf")
    assert fi.filename == "report.pdf"


def test_file_info_filename_stored_verbatim():
    """filename is stored exactly as given — no normalisation."""
    fi = FileInfo(filename="My Report (Final) v2.docx")
    assert fi.filename == "My Report (Final) v2.docx"


# ---------------------------------------------------------------------------
# Optional field defaults — all None
# ---------------------------------------------------------------------------

def test_file_info_default_file_id_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.file_id is None


def test_file_info_default_file_path_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.file_path is None


def test_file_info_default_content_type_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.content_type is None


def test_file_info_default_size_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.size is None


def test_file_info_default_upload_date_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.upload_date is None


def test_file_info_default_metadata_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.metadata is None


def test_file_info_default_user_id_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.user_id is None


def test_file_info_default_file_url_is_none():
    fi = FileInfo(filename="f.txt")
    assert fi.file_url is None


# ---------------------------------------------------------------------------
# Setting optional fields
# ---------------------------------------------------------------------------

def test_file_info_with_file_id():
    fi = FileInfo(filename="img.png", file_id="file-abc-123")
    assert fi.file_id == "file-abc-123"


def test_file_info_with_file_path():
    fi = FileInfo(filename="data.csv", file_path="/uploads/2026/data.csv")
    assert fi.file_path == "/uploads/2026/data.csv"


def test_file_info_with_content_type():
    fi = FileInfo(filename="image.jpg", content_type="image/jpeg")
    assert fi.content_type == "image/jpeg"


def test_file_info_with_size():
    fi = FileInfo(filename="archive.zip", size=1_048_576)
    assert fi.size == 1_048_576


def test_file_info_with_size_zero():
    fi = FileInfo(filename="empty.txt", size=0)
    assert fi.size == 0


def test_file_info_with_upload_date():
    now = datetime.now(UTC)
    fi = FileInfo(filename="doc.pdf", upload_date=now)
    assert fi.upload_date == now


def test_file_info_with_metadata_dict():
    meta = {"source": "email", "processed": True, "page_count": 10}
    fi = FileInfo(filename="attachment.pdf", metadata=meta)
    assert fi.metadata is not None
    assert fi.metadata["source"] == "email"
    assert fi.metadata["page_count"] == 10


def test_file_info_with_empty_metadata_dict():
    fi = FileInfo(filename="f.txt", metadata={})
    assert fi.metadata == {}


def test_file_info_with_nested_metadata():
    meta: dict = {"tags": ["report", "q1"], "dims": {"w": 800, "h": 600}}
    fi = FileInfo(filename="chart.png", metadata=meta)
    assert fi.metadata is not None
    assert fi.metadata["dims"]["w"] == 800


def test_file_info_with_user_id():
    fi = FileInfo(filename="personal.txt", user_id="user-999")
    assert fi.user_id == "user-999"


def test_file_info_with_file_url():
    url = "https://storage.example.com/files/report.pdf"
    fi = FileInfo(filename="report.pdf", file_url=url)
    assert fi.file_url == url


# ---------------------------------------------------------------------------
# Full construction
# ---------------------------------------------------------------------------

def test_file_info_full_construction():
    """All fields can be set simultaneously."""
    now = datetime.now(UTC)
    fi = FileInfo(
        file_id="file-001",
        filename="full.pdf",
        file_path="/storage/full.pdf",
        content_type="application/pdf",
        size=204_800,
        upload_date=now,
        metadata={"author": "Alice", "pages": 42},
        user_id="user-007",
        file_url="https://cdn.example.com/full.pdf",
    )
    assert fi.file_id == "file-001"
    assert fi.filename == "full.pdf"
    assert fi.file_path == "/storage/full.pdf"
    assert fi.content_type == "application/pdf"
    assert fi.size == 204_800
    assert fi.upload_date == now
    assert fi.metadata is not None
    assert fi.metadata["pages"] == 42
    assert fi.user_id == "user-007"
    assert fi.file_url == "https://cdn.example.com/full.pdf"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_file_info_model_dump_minimal():
    fi = FileInfo(filename="data.json")
    data = fi.model_dump()
    assert data["filename"] == "data.json"
    assert data["file_id"] is None
    assert data["file_path"] is None
    assert data["content_type"] is None
    assert data["size"] is None
    assert data["upload_date"] is None
    assert data["metadata"] is None
    assert data["user_id"] is None
    assert data["file_url"] is None


def test_file_info_model_dump_full():
    now = datetime.now(UTC)
    fi = FileInfo(
        file_id="fid",
        filename="full.txt",
        size=42,
        upload_date=now,
        metadata={"k": "v"},
    )
    data = fi.model_dump()
    assert data["file_id"] == "fid"
    assert data["size"] == 42
    assert data["upload_date"] == now
    assert data["metadata"] == {"k": "v"}


def test_file_info_round_trip_from_dict():
    now = datetime.now(UTC)
    original = FileInfo(
        file_id="fid",
        filename="rt.pdf",
        content_type="application/pdf",
        size=1024,
        upload_date=now,
        metadata={"key": "value"},
        user_id="uid",
        file_url="https://example.com/rt.pdf",
    )
    data = original.model_dump()
    restored = FileInfo.model_validate(data)
    assert restored.filename == original.filename
    assert restored.file_id == original.file_id
    assert restored.size == original.size
    assert restored.metadata == original.metadata
    assert restored.file_url == original.file_url


def test_file_info_model_dump_json_returns_string():
    fi = FileInfo(filename="test.txt")
    json_str = fi.model_dump_json()
    assert isinstance(json_str, str)
    assert "test.txt" in json_str


def test_file_info_round_trip_via_json():
    fi = FileInfo(filename="rt.csv", file_id="fid-42", size=999)
    json_str = fi.model_dump_json()
    restored = FileInfo.model_validate_json(json_str)
    assert restored.filename == "rt.csv"
    assert restored.file_id == "fid-42"
    assert restored.size == 999
