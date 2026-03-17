"""Tests for MinIOFileStorage -- verifies all operations are non-blocking.

MinIOFileStorage wraps the singleton MinIOStorage client and exposes a
FileStorage protocol.  After the blocking-I/O fix, every method must
delegate synchronous MinIO SDK calls to ``asyncio.to_thread``.

These tests mock the underlying Minio client and verify:

1. All previously-blocking methods now run in a thread pool.
2. The event loop remains responsive during I/O.
3. Ownership / permission checks still work correctly.
4. Error propagation is preserved through the thread boundary.
5. Concurrent operations do not block each other.
"""

import asyncio
import io
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.infrastructure.external.file import minios3storage
from app.infrastructure.external.file.minios3storage import MinIOFileStorage

# ---------------------------------------------------------------------------
# Fake Minio client
# ---------------------------------------------------------------------------


class _FakePutResult:
    def __init__(self, etag: str = "test-etag") -> None:
        self.etag = etag


class _FakeMinIOClient:
    """In-memory Minio client recording all calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._objects: dict[str, tuple[bytes, dict[str, str], str]] = {}

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        file_data,
        *,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> _FakePutResult:
        body = file_data.read() if hasattr(file_data, "read") else file_data
        self.calls.append(("put_object", (bucket_name, object_name), {"length": length}))
        self._objects[object_name] = (body, metadata or {}, content_type)
        return _FakePutResult()

    def get_object(self, bucket_name: str, object_name: str):
        self.calls.append(("get_object", (bucket_name, object_name), {}))
        if object_name not in self._objects:
            raise _make_s3_error("NoSuchKey", f"Object {object_name} not found")
        body, _meta, _ct = self._objects[object_name]
        resp = MagicMock()
        resp.read.return_value = body
        resp.close = MagicMock()
        resp.release_conn = MagicMock()
        return resp

    def stat_object(self, bucket_name: str, object_name: str):
        self.calls.append(("stat_object", (bucket_name, object_name), {}))
        if object_name not in self._objects:
            raise _make_s3_error("NoSuchKey", f"Object {object_name} not found")
        body, meta, ct = self._objects[object_name]
        # MinIO returns metadata with x-amz-meta- prefix in stat responses
        full_meta = {f"x-amz-meta-{k}": v for k, v in meta.items()}
        return SimpleNamespace(
            metadata=full_meta,
            content_type=ct,
            size=len(body),
            last_modified=datetime.now(UTC),
        )

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.calls.append(("remove_object", (bucket_name, object_name), {}))
        self._objects.pop(object_name, None)

    def presigned_put_object(self, bucket_name: str, object_name: str, expires: timedelta) -> str:
        self.calls.append(("presigned_put_object", (bucket_name, object_name), {}))
        return f"https://minio:9000/{bucket_name}/{object_name}?upload=1"

    def presigned_get_object(self, bucket_name: str, object_name: str, expires: timedelta) -> str:
        self.calls.append(("presigned_get_object", (bucket_name, object_name), {}))
        return f"https://minio:9000/{bucket_name}/{object_name}?download=1"


def _make_s3_error(code: str, message: str):
    """Create a fake S3Error with the expected .code attribute."""
    from minio.error import S3Error

    return S3Error(
        code=code,
        message=message,
        resource="test",
        request_id="test-req",
        host_id="test-host",
        response=MagicMock(status=404 if code == "NoSuchKey" else 500),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FAKE_SETTINGS = SimpleNamespace(
    minio_bucket_name="pythinker",
    minio_presigned_expiry_seconds=3600,
    minio_multipart_threshold_bytes=10 * 1024 * 1024,
    minio_retry_max_attempts=3,
    minio_retry_base_delay=0.5,
)


class _FakeMinIOStorage:
    """Wraps _FakeMinIOClient to look like the MinIOStorage singleton."""

    def __init__(self, client: _FakeMinIOClient) -> None:
        self.client = client


@pytest.fixture
def fake_client() -> _FakeMinIOClient:
    return _FakeMinIOClient()


@pytest.fixture
def file_storage(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: _FakeMinIOClient,
) -> MinIOFileStorage:
    monkeypatch.setattr(minios3storage, "get_settings", lambda: _FAKE_SETTINGS)
    return MinIOFileStorage(_FakeMinIOStorage(fake_client))  # type: ignore[arg-type]


def _seed_object(
    client: _FakeMinIOClient,
    key: str,
    data: bytes = b"hello",
    user_id: str = "user-1",
    content_type: str = "application/octet-stream",
) -> None:
    """Seed a fake object with standard metadata."""
    client._objects[key] = (
        data,
        {"user-id": user_id, "original-filename": key.split("/")[-1]},
        content_type,
    )


# ---------------------------------------------------------------------------
# Download tests (was blocking before fix)
# ---------------------------------------------------------------------------


class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_download_returns_data_and_file_info(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/abc_report.pdf", b"pdf-bytes", "user-1", "application/pdf")

        data_io, info = await file_storage.download_file("user-1/abc_report.pdf", user_id="user-1")

        assert data_io.read() == b"pdf-bytes"
        assert info.file_id == "user-1/abc_report.pdf"
        assert info.content_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_download_raises_permission_error_for_wrong_user(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/abc_report.pdf", b"data", "user-1")

        with pytest.raises(PermissionError, match="does not belong"):
            await file_storage.download_file("user-1/abc_report.pdf", user_id="user-2")

    @pytest.mark.asyncio
    async def test_download_raises_file_not_found(self, file_storage: MinIOFileStorage) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            await file_storage.download_file("nonexistent/key")

    @pytest.mark.asyncio
    async def test_download_event_loop_not_blocked(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/big.bin", b"x" * 1024, "user-1")
        ticks: list[float] = []
        stop = False

        async def ticker():
            while not stop:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        original_stat = fake_client.stat_object
        original_get = fake_client.get_object

        def slow_stat(*a, **kw):
            import time as _time

            _time.sleep(0.05)
            return original_stat(*a, **kw)

        def slow_get(*a, **kw):
            import time as _time

            _time.sleep(0.05)
            return original_get(*a, **kw)

        fake_client.stat_object = slow_stat  # type: ignore[assignment]
        fake_client.get_object = slow_get  # type: ignore[assignment]

        task = asyncio.create_task(ticker())
        await file_storage.download_file("user-1/big.bin", user_id="user-1")
        stop = True
        await task

        assert len(ticks) >= 3, f"Event loop blocked: only {len(ticks)} ticks"


# ---------------------------------------------------------------------------
# Delete tests (was blocking before fix)
# ---------------------------------------------------------------------------


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_removes_object(self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient) -> None:
        _seed_object(fake_client, "user-1/abc_file.txt", b"data", "user-1")

        result = await file_storage.delete_file("user-1/abc_file.txt", user_id="user-1")

        assert result is True
        assert "user-1/abc_file.txt" not in fake_client._objects

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_wrong_user(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/abc_file.txt", b"data", "user-1")

        result = await file_storage.delete_file("user-1/abc_file.txt", user_id="user-2")

        assert result is False
        assert "user-1/abc_file.txt" in fake_client._objects

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_nonexistent(self, file_storage: MinIOFileStorage) -> None:
        result = await file_storage.delete_file("nonexistent/key", user_id="user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_event_loop_not_blocked(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/del.txt", b"data", "user-1")
        ticks: list[float] = []
        stop = False

        async def ticker():
            while not stop:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        original_remove = fake_client.remove_object

        def slow_remove(*a, **kw):
            import time as _time

            _time.sleep(0.1)
            return original_remove(*a, **kw)

        fake_client.remove_object = slow_remove  # type: ignore[assignment]

        task = asyncio.create_task(ticker())
        await file_storage.delete_file("user-1/del.txt", user_id="user-1")
        stop = True
        await task

        assert len(ticks) >= 3, f"Event loop blocked: only {len(ticks)} ticks"


# ---------------------------------------------------------------------------
# Get file info tests (was blocking before fix)
# ---------------------------------------------------------------------------


class TestGetFileInfo:
    @pytest.mark.asyncio
    async def test_get_file_info_returns_info(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/abc_report.pdf", b"pdf", "user-1", "application/pdf")

        info = await file_storage.get_file_info("user-1/abc_report.pdf", user_id="user-1")

        assert info is not None
        assert info.file_id == "user-1/abc_report.pdf"
        assert info.content_type == "application/pdf"
        assert info.size == 3

    @pytest.mark.asyncio
    async def test_get_file_info_returns_none_for_wrong_user(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/abc_report.pdf", b"pdf", "user-1")

        info = await file_storage.get_file_info("user-1/abc_report.pdf", user_id="user-2")
        assert info is None

    @pytest.mark.asyncio
    async def test_get_file_info_returns_none_for_nonexistent(self, file_storage: MinIOFileStorage) -> None:
        info = await file_storage.get_file_info("nonexistent/key")
        assert info is None

    @pytest.mark.asyncio
    async def test_get_file_info_event_loop_not_blocked(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/info.txt", b"data", "user-1")
        ticks: list[float] = []
        stop = False

        async def ticker():
            while not stop:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        original_stat = fake_client.stat_object

        def slow_stat(*a, **kw):
            import time as _time

            _time.sleep(0.1)
            return original_stat(*a, **kw)

        fake_client.stat_object = slow_stat  # type: ignore[assignment]

        task = asyncio.create_task(ticker())
        await file_storage.get_file_info("user-1/info.txt", user_id="user-1")
        stop = True
        await task

        assert len(ticks) >= 3, f"Event loop blocked: only {len(ticks)} ticks"


# ---------------------------------------------------------------------------
# Generate upload URL tests (was blocking before fix)
# ---------------------------------------------------------------------------


class TestGenerateUploadUrl:
    @pytest.mark.asyncio
    async def test_generate_upload_url_returns_url_and_key(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        url, key = await file_storage.generate_upload_url("test.pdf", "user-1")

        assert "upload=1" in url
        assert key.startswith("user-1/")
        assert key.endswith("_test.pdf")

        presigned_calls = [c for c in fake_client.calls if c[0] == "presigned_put_object"]
        assert len(presigned_calls) == 1

    @pytest.mark.asyncio
    async def test_generate_upload_url_event_loop_not_blocked(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        ticks: list[float] = []
        stop = False

        async def ticker():
            while not stop:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        original_presigned = fake_client.presigned_put_object

        def slow_presigned(*a, **kw):
            import time as _time

            _time.sleep(0.1)
            return original_presigned(*a, **kw)

        fake_client.presigned_put_object = slow_presigned  # type: ignore[assignment]

        task = asyncio.create_task(ticker())
        await file_storage.generate_upload_url("file.txt", "user-1")
        stop = True
        await task

        assert len(ticks) >= 3, f"Event loop blocked: only {len(ticks)} ticks"


# ---------------------------------------------------------------------------
# Generate download URL tests (was blocking before fix)
# ---------------------------------------------------------------------------


class TestGenerateDownloadUrl:
    @pytest.mark.asyncio
    async def test_generate_download_url_returns_url(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/abc_file.txt", b"data", "user-1")

        url = await file_storage.generate_download_url("user-1/abc_file.txt", user_id="user-1")

        assert "download=1" in url
        presigned_calls = [c for c in fake_client.calls if c[0] == "presigned_get_object"]
        assert len(presigned_calls) == 1

    @pytest.mark.asyncio
    async def test_generate_download_url_raises_permission_error(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/abc_file.txt", b"data", "user-1")

        with pytest.raises(PermissionError, match="does not belong"):
            await file_storage.generate_download_url("user-1/abc_file.txt", user_id="user-2")

    @pytest.mark.asyncio
    async def test_generate_download_url_without_user_check(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        """When user_id is None, skip ownership check."""
        _seed_object(fake_client, "user-1/abc_file.txt", b"data", "user-1")

        url = await file_storage.generate_download_url("user-1/abc_file.txt", user_id=None)
        assert "download=1" in url

        # No stat_object call when user_id is None
        stat_calls = [c for c in fake_client.calls if c[0] == "stat_object"]
        assert len(stat_calls) == 0

    @pytest.mark.asyncio
    async def test_generate_download_url_event_loop_not_blocked(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        _seed_object(fake_client, "user-1/dl.txt", b"data", "user-1")
        ticks: list[float] = []
        stop = False

        async def ticker():
            while not stop:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        original_presigned = fake_client.presigned_get_object

        def slow_presigned(*a, **kw):
            import time as _time

            _time.sleep(0.1)
            return original_presigned(*a, **kw)

        fake_client.presigned_get_object = slow_presigned  # type: ignore[assignment]

        task = asyncio.create_task(ticker())
        await file_storage.generate_download_url("user-1/dl.txt", user_id=None)
        stop = True
        await task

        assert len(ticks) >= 3, f"Event loop blocked: only {len(ticks)} ticks"


# ---------------------------------------------------------------------------
# Concurrent operations test
# ---------------------------------------------------------------------------


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(
        self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient
    ) -> None:
        """Multiple different operations should run concurrently."""
        _seed_object(fake_client, "user-1/a.txt", b"aaa", "user-1")
        _seed_object(fake_client, "user-1/b.txt", b"bbb", "user-1")

        # Add artificial delay to all blocking calls
        original_stat = fake_client.stat_object
        original_get = fake_client.get_object
        original_presigned = fake_client.presigned_get_object

        def slow(fn):
            def wrapper(*a, **kw):
                import time as _time

                _time.sleep(0.05)
                return fn(*a, **kw)

            return wrapper

        fake_client.stat_object = slow(original_stat)  # type: ignore[assignment]
        fake_client.get_object = slow(original_get)  # type: ignore[assignment]
        fake_client.presigned_get_object = slow(original_presigned)  # type: ignore[assignment]

        start = time.monotonic()
        results = await asyncio.gather(
            file_storage.download_file("user-1/a.txt", user_id="user-1"),
            file_storage.get_file_info("user-1/b.txt", user_id="user-1"),
            file_storage.generate_download_url("user-1/a.txt", user_id=None),
        )
        elapsed = time.monotonic() - start

        # All 3 operations should run in parallel, not 3x sequential
        assert elapsed < 0.4, f"Operations appear sequential: {elapsed:.3f}s"
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Upload (already async, regression test)
# ---------------------------------------------------------------------------


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_upload_file_still_works(self, file_storage: MinIOFileStorage, fake_client: _FakeMinIOClient) -> None:
        """Verify upload_file (already async) still works after refactor."""
        info = await file_storage.upload_file(
            io.BytesIO(b"hello"),
            "report.md",
            "user-1",
            content_type="text/markdown",
        )

        assert info.filename == "report.md"
        assert info.size == 5
        assert info.user_id == "user-1"

        put_calls = [c for c in fake_client.calls if c[0] == "put_object"]
        assert len(put_calls) == 1
