"""Tests for FileService application service.

Covers:
- Storage/token-service unavailability raises RuntimeError
- upload_file: success and storage-level exceptions
- download_file: success and storage-level exceptions
- delete_file: returns True/False, storage-level exceptions
- get_file_info: found and not-found paths, storage-level exceptions
- enrich_with_file_url: delegates to create_signed_url and sets file_url
- create_signed_url: expire_minutes cap at 30, FileNotFoundError when file absent
- generate_upload_url: delegates to storage
- generate_download_url: delegates to storage
- create_zip_archive: single file, multiple files, duplicate filenames, failed downloads
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.file_service import FileService
from app.domain.models.file import FileInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_info(
    file_id: str = "file-123",
    filename: str = "report.pdf",
    user_id: str = "user-abc",
    file_url: str | None = None,
) -> FileInfo:
    return FileInfo(file_id=file_id, filename=filename, user_id=user_id, file_url=file_url)


def _make_service(
    storage: AsyncMock | None = None,
    token_service: MagicMock | None = None,
) -> FileService:
    return FileService(file_storage=storage, token_service=token_service)


def _make_storage() -> AsyncMock:
    return AsyncMock()


def _make_token_service(signed_url: str = "/api/v1/files/signed-download/file-123?signature=abc") -> MagicMock:
    svc = MagicMock()
    svc.create_signed_url.return_value = signed_url
    return svc


def _make_file_data(content: bytes = b"hello world") -> io.BytesIO:
    return io.BytesIO(content)


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUploadFile:
    async def test_raises_when_storage_is_none(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="File storage service not available"):
            await svc.upload_file(_make_file_data(), "file.txt", "user-1")

    async def test_returns_file_info_on_success(self) -> None:
        storage = _make_storage()
        expected = _make_file_info(file_id="f-1", filename="file.txt")
        storage.upload_file.return_value = expected

        svc = _make_service(storage=storage)
        result = await svc.upload_file(_make_file_data(), "file.txt", "user-1", "text/plain", {"key": "val"})

        assert result is expected
        storage.upload_file.assert_awaited_once()

    async def test_passes_content_type_and_metadata_to_storage(self) -> None:
        storage = _make_storage()
        storage.upload_file.return_value = _make_file_info()

        svc = _make_service(storage=storage)
        data = _make_file_data()
        await svc.upload_file(data, "doc.pdf", "user-9", "application/pdf", {"tag": "report"})

        call_args = storage.upload_file.call_args
        assert call_args.args[1] == "doc.pdf"
        assert call_args.args[2] == "user-9"
        assert call_args.args[3] == "application/pdf"
        assert call_args.args[4] == {"tag": "report"}

    async def test_propagates_storage_exception(self) -> None:
        storage = _make_storage()
        storage.upload_file.side_effect = OSError("disk full")

        svc = _make_service(storage=storage)
        with pytest.raises(OSError, match="disk full"):
            await svc.upload_file(_make_file_data(), "f.txt", "u-1")


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDownloadFile:
    async def test_raises_when_storage_is_none(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="File storage service not available"):
            await svc.download_file("file-1", "user-1")

    async def test_returns_tuple_on_success(self) -> None:
        storage = _make_storage()
        info = _make_file_info()
        data = _make_file_data()
        storage.download_file.return_value = (data, info)

        svc = _make_service(storage=storage)
        result_data, result_info = await svc.download_file("file-123", "user-abc")

        assert result_data is data
        assert result_info is info

    async def test_download_without_user_id(self) -> None:
        storage = _make_storage()
        storage.download_file.return_value = (_make_file_data(), _make_file_info())

        svc = _make_service(storage=storage)
        await svc.download_file("file-123")

        storage.download_file.assert_awaited_once_with("file-123", None)

    async def test_propagates_storage_exception(self) -> None:
        storage = _make_storage()
        storage.download_file.side_effect = PermissionError("access denied")

        svc = _make_service(storage=storage)
        with pytest.raises(PermissionError):
            await svc.download_file("file-1", "user-1")


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDeleteFile:
    async def test_raises_when_storage_is_none(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="File storage service not available"):
            await svc.delete_file("file-1", "user-1")

    async def test_returns_true_on_successful_deletion(self) -> None:
        storage = _make_storage()
        storage.delete_file.return_value = True

        svc = _make_service(storage=storage)
        result = await svc.delete_file("file-1", "user-1")

        assert result is True

    async def test_returns_false_when_file_not_found(self) -> None:
        storage = _make_storage()
        storage.delete_file.return_value = False

        svc = _make_service(storage=storage)
        result = await svc.delete_file("missing-file", "user-1")

        assert result is False

    async def test_propagates_storage_exception(self) -> None:
        storage = _make_storage()
        storage.delete_file.side_effect = RuntimeError("storage error")

        svc = _make_service(storage=storage)
        with pytest.raises(RuntimeError, match="storage error"):
            await svc.delete_file("file-1", "user-1")


# ---------------------------------------------------------------------------
# get_file_info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetFileInfo:
    async def test_raises_when_storage_is_none(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="File storage service not available"):
            await svc.get_file_info("file-1")

    async def test_returns_file_info_when_found(self) -> None:
        storage = _make_storage()
        info = _make_file_info()
        storage.get_file_info.return_value = info

        svc = _make_service(storage=storage)
        result = await svc.get_file_info("file-123", "user-abc")

        assert result is info

    async def test_returns_none_when_not_found(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = None

        svc = _make_service(storage=storage)
        result = await svc.get_file_info("no-file", "user-1")

        assert result is None

    async def test_get_file_info_without_user_id(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = _make_file_info()

        svc = _make_service(storage=storage)
        await svc.get_file_info("file-123")

        storage.get_file_info.assert_awaited_once_with("file-123", None)

    async def test_propagates_storage_exception(self) -> None:
        storage = _make_storage()
        storage.get_file_info.side_effect = ConnectionError("DB unavailable")

        svc = _make_service(storage=storage)
        with pytest.raises(ConnectionError):
            await svc.get_file_info("file-1", "user-1")


# ---------------------------------------------------------------------------
# create_signed_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateSignedUrl:
    async def test_raises_when_token_service_is_none(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = _make_file_info()

        svc = _make_service(storage=storage, token_service=None)
        with pytest.raises(RuntimeError, match="Token service not available"):
            await svc.create_signed_url("file-123", "user-abc")

    async def test_raises_file_not_found_when_file_absent(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = None

        svc = _make_service(storage=storage, token_service=_make_token_service())
        with pytest.raises(FileNotFoundError, match="File not found"):
            await svc.create_signed_url("missing-file", "user-abc")

    async def test_returns_signed_url_on_success(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = _make_file_info(file_id="f-99")
        token_svc = _make_token_service("/api/v1/files/signed-download/f-99?signature=xyz")

        svc = _make_service(storage=storage, token_service=token_svc)
        result = await svc.create_signed_url("f-99", "user-1")

        assert result == "/api/v1/files/signed-download/f-99?signature=xyz"

    async def test_caps_expire_minutes_at_30(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = _make_file_info(file_id="f-1")
        token_svc = _make_token_service()

        svc = _make_service(storage=storage, token_service=token_svc)
        await svc.create_signed_url("f-1", "user-1", expire_minutes=120)

        call_kwargs = token_svc.create_signed_url.call_args
        expire_passed = call_kwargs.kwargs.get("expire_minutes") or call_kwargs.args[1]
        assert expire_passed == 30

    async def test_expire_minutes_below_cap_is_preserved(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = _make_file_info(file_id="f-1")
        token_svc = _make_token_service()

        svc = _make_service(storage=storage, token_service=token_svc)
        await svc.create_signed_url("f-1", "user-1", expire_minutes=15)

        call_kwargs = token_svc.create_signed_url.call_args
        expire_passed = call_kwargs.kwargs.get("expire_minutes") or call_kwargs.args[1]
        assert expire_passed == 15

    async def test_exactly_30_minutes_is_not_capped(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = _make_file_info(file_id="f-1")
        token_svc = _make_token_service()

        svc = _make_service(storage=storage, token_service=token_svc)
        await svc.create_signed_url("f-1", "user-1", expire_minutes=30)

        call_kwargs = token_svc.create_signed_url.call_args
        expire_passed = call_kwargs.kwargs.get("expire_minutes") or call_kwargs.args[1]
        assert expire_passed == 30

    async def test_url_contains_file_id_path(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = _make_file_info(file_id="special-file-id")
        token_svc = _make_token_service()

        svc = _make_service(storage=storage, token_service=token_svc)
        await svc.create_signed_url("special-file-id", "user-1")

        call = token_svc.create_signed_url.call_args
        # base_url may be passed positionally or as keyword arg
        all_args = list(call.args) + list(call.kwargs.values())
        base_url_arg = next((a for a in all_args if isinstance(a, str) and "files" in a), None)
        assert base_url_arg is not None, f"No base_url-like arg found in {call}"
        assert "special-file-id" in base_url_arg


# ---------------------------------------------------------------------------
# enrich_with_file_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEnrichWithFileUrl:
    async def test_sets_file_url_on_file_info(self) -> None:
        storage = _make_storage()
        info = _make_file_info(file_id="f-55", user_id="u-1")
        storage.get_file_info.return_value = info

        token_svc = _make_token_service("/api/v1/files/signed-download/f-55?signature=tok")
        svc = _make_service(storage=storage, token_service=token_svc)

        result = await svc.enrich_with_file_url(info)

        assert result.file_url == "/api/v1/files/signed-download/f-55?signature=tok"
        assert result is info  # mutates in-place and returns same object

    async def test_propagates_error_when_token_service_missing(self) -> None:
        storage = _make_storage()
        info = _make_file_info()
        storage.get_file_info.return_value = info

        svc = _make_service(storage=storage, token_service=None)
        with pytest.raises(RuntimeError):
            await svc.enrich_with_file_url(info)

    async def test_propagates_error_when_file_not_found(self) -> None:
        storage = _make_storage()
        storage.get_file_info.return_value = None
        info = _make_file_info()

        svc = _make_service(storage=storage, token_service=_make_token_service())
        with pytest.raises(FileNotFoundError):
            await svc.enrich_with_file_url(info)


# ---------------------------------------------------------------------------
# generate_upload_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGenerateUploadUrl:
    async def test_raises_when_storage_is_none(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="File storage service not available"):
            await svc.generate_upload_url("file.txt", "user-1")

    async def test_returns_tuple_from_storage(self) -> None:
        storage = _make_storage()
        storage.generate_upload_url.return_value = ("https://s3/presign", "users/user-1/file.txt")

        svc = _make_service(storage=storage)
        url, key = await svc.generate_upload_url("file.txt", "user-1", "text/plain")

        assert url == "https://s3/presign"
        assert key == "users/user-1/file.txt"
        storage.generate_upload_url.assert_awaited_once_with("file.txt", "user-1", "text/plain")


# ---------------------------------------------------------------------------
# generate_download_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGenerateDownloadUrl:
    async def test_raises_when_storage_is_none(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="File storage service not available"):
            await svc.generate_download_url("file-1")

    async def test_returns_url_from_storage(self) -> None:
        storage = _make_storage()
        storage.generate_download_url.return_value = "https://cdn.example.com/file-1"

        svc = _make_service(storage=storage)
        result = await svc.generate_download_url("file-1", "user-1")

        assert result == "https://cdn.example.com/file-1"
        storage.generate_download_url.assert_awaited_once_with("file-1", "user-1")

    async def test_passes_none_user_id_to_storage(self) -> None:
        storage = _make_storage()
        storage.generate_download_url.return_value = "https://example.com/f"

        svc = _make_service(storage=storage)
        await svc.generate_download_url("file-1")

        storage.generate_download_url.assert_awaited_once_with("file-1", None)


# ---------------------------------------------------------------------------
# create_zip_archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateZipArchive:
    async def test_raises_when_storage_is_none(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="File storage service not available"):
            await svc.create_zip_archive(["file-1"])

    async def test_empty_file_list_produces_empty_zip(self) -> None:
        storage = _make_storage()
        svc = _make_service(storage=storage)

        zip_buf, name = await svc.create_zip_archive([])

        assert zip_buf.getbuffer().nbytes > 0
        assert name.startswith("files_")
        assert name.endswith(".zip")

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            assert zf.namelist() == []

    async def test_single_file_added_to_archive(self) -> None:
        storage = _make_storage()
        content = b"hello archive"
        info = _make_file_info(file_id="f-1", filename="hello.txt")
        storage.download_file.return_value = (io.BytesIO(content), info)

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1"], "user-1")

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            assert "hello.txt" in zf.namelist()
            assert zf.read("hello.txt") == content

    async def test_multiple_distinct_filenames(self) -> None:
        storage = _make_storage()
        storage.download_file.side_effect = [
            (io.BytesIO(b"content-a"), _make_file_info(file_id="f-1", filename="a.txt")),
            (io.BytesIO(b"content-b"), _make_file_info(file_id="f-2", filename="b.txt")),
        ]

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1", "f-2"])

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            names = zf.namelist()
            assert "a.txt" in names
            assert "b.txt" in names

    async def test_duplicate_filenames_get_numeric_suffix(self) -> None:
        storage = _make_storage()
        storage.download_file.side_effect = [
            (io.BytesIO(b"first"), _make_file_info(file_id="f-1", filename="report.pdf")),
            (io.BytesIO(b"second"), _make_file_info(file_id="f-2", filename="report.pdf")),
        ]

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1", "f-2"])

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            names = zf.namelist()
            assert "report.pdf" in names
            assert "report_1.pdf" in names
            assert len(names) == 2

    async def test_duplicate_filename_without_extension_gets_suffix(self) -> None:
        storage = _make_storage()
        storage.download_file.side_effect = [
            (io.BytesIO(b"first"), _make_file_info(file_id="f-1", filename="readme")),
            (io.BytesIO(b"second"), _make_file_info(file_id="f-2", filename="readme")),
        ]

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1", "f-2"])

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            names = zf.namelist()
            assert "readme" in names
            assert "readme_1" in names

    async def test_failed_download_is_skipped(self) -> None:
        storage = _make_storage()
        storage.download_file.side_effect = [
            Exception("network timeout"),
            (io.BytesIO(b"good content"), _make_file_info(file_id="f-2", filename="good.txt")),
        ]

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-bad", "f-2"])

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            names = zf.namelist()
            assert "good.txt" in names
            assert len(names) == 1

    async def test_all_downloads_failed_produces_empty_zip(self) -> None:
        storage = _make_storage()
        storage.download_file.side_effect = [
            Exception("error-1"),
            Exception("error-2"),
        ]

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1", "f-2"])

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            assert zf.namelist() == []

    async def test_archive_name_uses_timestamp_format(self) -> None:
        storage = _make_storage()
        storage.download_file.return_value = (
            io.BytesIO(b"data"),
            _make_file_info(filename="x.txt"),
        )

        svc = _make_service(storage=storage)
        _, name = await svc.create_zip_archive(["f-1"])

        import re

        assert re.match(r"files_\d{8}_\d{6}\.zip", name), f"Unexpected archive name: {name!r}"

    async def test_three_duplicates_get_incrementing_suffixes(self) -> None:
        storage = _make_storage()
        storage.download_file.side_effect = [
            (io.BytesIO(b"v1"), _make_file_info(file_id="f-1", filename="doc.txt")),
            (io.BytesIO(b"v2"), _make_file_info(file_id="f-2", filename="doc.txt")),
            (io.BytesIO(b"v3"), _make_file_info(file_id="f-3", filename="doc.txt")),
        ]

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1", "f-2", "f-3"])

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            names = set(zf.namelist())
            assert names == {"doc.txt", "doc_1.txt", "doc_2.txt"}

    async def test_returned_buffer_is_seeked_to_start(self) -> None:
        storage = _make_storage()
        storage.download_file.return_value = (
            io.BytesIO(b"seektest"),
            _make_file_info(filename="seek.txt"),
        )

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1"])

        assert zip_buf.tell() == 0

    async def test_zip_file_content_matches_original(self) -> None:
        storage = _make_storage()
        original = b"binary\x00\x01\x02content"
        storage.download_file.return_value = (
            io.BytesIO(original),
            _make_file_info(filename="binary.bin"),
        )

        svc = _make_service(storage=storage)
        zip_buf, _ = await svc.create_zip_archive(["f-1"])

        zip_buf.seek(0)
        with zipfile.ZipFile(zip_buf) as zf:
            assert zf.read("binary.bin") == original
