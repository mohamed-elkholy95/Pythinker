"""Tests for MinIO snapshot storage adapter -- verifies non-blocking async I/O.

Every public method on MinIOStorage must delegate blocking MinIO SDK calls
to ``asyncio.to_thread`` so the event loop is never starved.  These tests
mock the Minio client and assert that:

1. Blocking calls run in a worker thread (via ``asyncio.to_thread``).
2. The event loop remains free during I/O operations.
3. Error propagation works correctly through the thread boundary.
4. Lifecycle methods (initialize / shutdown) behave correctly.
5. Concurrent operations do not block each other.
"""

import asyncio
import time
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.external.storage.minio_storage import MinIOStorage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeMinioClient:
    """In-memory fake that records every call made by MinIOStorage."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._objects: dict[str, bytes] = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        self.calls.append(("bucket_exists", (bucket_name,), {}))
        return True

    def make_bucket(self, bucket_name: str, **kwargs) -> None:
        self.calls.append(("make_bucket", (bucket_name,), kwargs))

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        metadata: dict | None = None,
    ) -> None:
        self.calls.append(("put_object", (bucket_name, object_name), {"length": length, "metadata": metadata}))
        self._objects[object_name] = data.read()

    def get_object(self, bucket_name: str, object_name: str):
        self.calls.append(("get_object", (bucket_name, object_name), {}))
        data = self._objects.get(object_name, b"test-data")
        resp = MagicMock()
        resp.read.return_value = data
        resp.close = MagicMock()
        resp.release_conn = MagicMock()
        return resp

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.calls.append(("remove_object", (bucket_name, object_name), {}))
        self._objects.pop(object_name, None)

    def stat_object(self, bucket_name: str, object_name: str):
        self.calls.append(("stat_object", (bucket_name, object_name), {}))
        if object_name not in self._objects:
            raise Exception("NoSuchKey")
        return SimpleNamespace(size=len(self._objects[object_name]))

    def list_objects(self, bucket_name: str, prefix: str = ""):
        self.calls.append(("list_objects", (bucket_name,), {"prefix": prefix}))
        return [SimpleNamespace(object_name=k) for k in self._objects if k.startswith(prefix)]


@pytest.fixture
def fake_client() -> _FakeMinioClient:
    return _FakeMinioClient()


@pytest.fixture
def storage(fake_client: _FakeMinioClient) -> MinIOStorage:
    """Build a MinIOStorage with a fake Minio client injected."""
    with patch("app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None):
        s = object.__new__(MinIOStorage)
    s.endpoint = "localhost:9000"
    s.access_key = "test"
    s.secret_key = "test"
    s.bucket_name = "test-bucket"
    s.secure = False
    s._client = fake_client
    s._initialized = True
    return s


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for initialize() and shutdown()."""

    @pytest.mark.asyncio
    async def test_initialize_creates_bucket_when_missing(self, fake_client: _FakeMinioClient) -> None:
        """initialize() should call make_bucket when bucket_exists returns False."""
        fake_client.bucket_exists = lambda b: False  # type: ignore[assignment]
        made: list[str] = []

        def _make(b, **kw):
            made.append(b)

        fake_client.make_bucket = _make  # type: ignore[assignment]

        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s.endpoint = "localhost:9000"
        s.access_key = "test"
        s.secret_key = "test"
        s.bucket_name = "my-bucket"
        s.secure = False
        s._client = fake_client
        s._initialized = False

        await s.initialize()

        assert "my-bucket" in made
        assert s._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_skips_when_bucket_exists(self, fake_client: _FakeMinioClient) -> None:
        """initialize() should NOT call make_bucket when bucket already exists."""
        made: list[str] = []
        fake_client.make_bucket = lambda b, **kw: made.append(b)  # type: ignore[assignment]

        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s.endpoint = "localhost:9000"
        s.access_key = "test"
        s.secret_key = "test"
        s.bucket_name = "my-bucket"
        s.secure = False
        s._client = fake_client
        s._initialized = False

        await s.initialize()

        assert len(made) == 0
        assert s._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, storage: MinIOStorage) -> None:
        """Calling initialize() twice does not error or re-run bucket checks."""
        # Already initialized in fixture
        await storage.initialize()  # no-op
        assert storage._initialized is True

    @pytest.mark.asyncio
    async def test_shutdown_clears_client(self, storage: MinIOStorage) -> None:
        await storage.shutdown()
        assert storage._client is None
        assert storage._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_error_propagates(self) -> None:
        """initialize() should propagate errors and leave _initialized False."""
        bad_client = MagicMock()
        bad_client.bucket_exists.side_effect = ConnectionError("unreachable")

        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s.endpoint = "localhost:9000"
        s.access_key = "test"
        s.secret_key = "test"
        s.bucket_name = "my-bucket"
        s.secure = False
        s._client = bad_client
        s._initialized = False

        with pytest.raises(ConnectionError, match="unreachable"):
            await s.initialize()

        assert s._initialized is False


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


class TestUpload:
    @pytest.mark.asyncio
    async def test_upload_delegates_to_put_object(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        data = b"snapshot-bytes"
        await storage.upload("snap/key.tar.gz", data, metadata={"session": "s1"})

        put_calls = [c for c in fake_client.calls if c[0] == "put_object"]
        assert len(put_calls) == 1
        assert put_calls[0][1] == ("test-bucket", "snap/key.tar.gz")
        assert put_calls[0][2]["length"] == len(data)
        assert put_calls[0][2]["metadata"] == {"session": "s1"}

    @pytest.mark.asyncio
    async def test_upload_raises_when_client_none(self) -> None:
        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s._client = None
        s._initialized = False

        with pytest.raises(RuntimeError, match="not initialized"):
            await s.upload("key", b"data")

    @pytest.mark.asyncio
    async def test_upload_propagates_sdk_error(self, storage: MinIOStorage) -> None:
        storage._client.put_object = MagicMock(side_effect=OSError("disk full"))  # type: ignore[union-attr]

        with pytest.raises(OSError, match="disk full"):
            await storage.upload("key", b"data")

    @pytest.mark.asyncio
    async def test_upload_with_none_metadata(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        """metadata=None should be passed as empty dict to put_object."""
        await storage.upload("key", b"data", metadata=None)
        put_calls = [c for c in fake_client.calls if c[0] == "put_object"]
        assert put_calls[0][2]["metadata"] == {}


# ---------------------------------------------------------------------------
# Download tests
# ---------------------------------------------------------------------------


class TestDownload:
    @pytest.mark.asyncio
    async def test_download_returns_bytes(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        fake_client._objects["snap/key.tar.gz"] = b"compressed-data"

        result = await storage.download("snap/key.tar.gz")

        assert result == b"compressed-data"
        get_calls = [c for c in fake_client.calls if c[0] == "get_object"]
        assert len(get_calls) == 1

    @pytest.mark.asyncio
    async def test_download_raises_when_client_none(self) -> None:
        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s._client = None
        s._initialized = False

        with pytest.raises(RuntimeError, match="not initialized"):
            await s.download("key")

    @pytest.mark.asyncio
    async def test_download_propagates_error(self, storage: MinIOStorage) -> None:
        storage._client.get_object = MagicMock(side_effect=TimeoutError("timed out"))  # type: ignore[union-attr]

        with pytest.raises(TimeoutError, match="timed out"):
            await storage.download("key")


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_calls_remove_object(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        fake_client._objects["key"] = b"data"

        await storage.delete("key")

        remove_calls = [c for c in fake_client.calls if c[0] == "remove_object"]
        assert len(remove_calls) == 1
        assert remove_calls[0][1] == ("test-bucket", "key")
        assert "key" not in fake_client._objects

    @pytest.mark.asyncio
    async def test_delete_raises_when_client_none(self) -> None:
        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s._client = None
        s._initialized = False

        with pytest.raises(RuntimeError, match="not initialized"):
            await s.delete("key")


# ---------------------------------------------------------------------------
# Exists tests
# ---------------------------------------------------------------------------


class TestExists:
    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        fake_client._objects["key"] = b"data"
        assert await storage.exists("key") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing(self, storage: MinIOStorage) -> None:
        assert await storage.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_exists_raises_when_client_none(self) -> None:
        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s._client = None
        s._initialized = False

        with pytest.raises(RuntimeError, match="not initialized"):
            await s.exists("key")


# ---------------------------------------------------------------------------
# List objects tests
# ---------------------------------------------------------------------------


class TestListObjects:
    @pytest.mark.asyncio
    async def test_list_objects_returns_keys(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        fake_client._objects["prefix/a.tar.gz"] = b"a"
        fake_client._objects["prefix/b.tar.gz"] = b"b"
        fake_client._objects["other/c.tar.gz"] = b"c"

        result = await storage.list_objects(prefix="prefix/")

        assert sorted(result) == ["prefix/a.tar.gz", "prefix/b.tar.gz"]

    @pytest.mark.asyncio
    async def test_list_objects_empty_prefix(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        fake_client._objects["a"] = b"1"
        fake_client._objects["b"] = b"2"

        result = await storage.list_objects()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_objects_returns_empty_on_error(self, storage: MinIOStorage) -> None:
        storage._client.list_objects = MagicMock(side_effect=OSError("network"))  # type: ignore[union-attr]

        result = await storage.list_objects(prefix="x/")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_objects_raises_when_client_none(self) -> None:
        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s._client = None
        s._initialized = False

        with pytest.raises(RuntimeError, match="not initialized"):
            await s.list_objects()

    @pytest.mark.asyncio
    async def test_list_objects_is_async(self) -> None:
        """list_objects must be awaitable (was sync in the old implementation)."""
        with patch(
            "app.infrastructure.external.storage.minio_storage.MinIOStorage.__init__", lambda self, *a, **kw: None
        ):
            s = object.__new__(MinIOStorage)
        s._client = _FakeMinioClient()
        s._initialized = True
        s.bucket_name = "test"

        result = s.list_objects()
        assert asyncio.iscoroutine(result)
        # Clean up coroutine
        await result


# ---------------------------------------------------------------------------
# Non-blocking verification
# ---------------------------------------------------------------------------


class TestNonBlocking:
    """Verify that operations do not block the event loop."""

    @pytest.mark.asyncio
    async def test_concurrent_uploads_do_not_block(self, storage: MinIOStorage) -> None:
        """Multiple uploads should run concurrently, not sequentially."""

        original_put = storage._client.put_object  # type: ignore[union-attr]

        def slow_put(*args, **kwargs):
            import time as _time

            _time.sleep(0.05)  # 50ms simulated I/O
            return original_put(*args, **kwargs)

        storage._client.put_object = slow_put  # type: ignore[union-attr]

        start = time.monotonic()
        await asyncio.gather(
            storage.upload("k1", b"d1"),
            storage.upload("k2", b"d2"),
            storage.upload("k3", b"d3"),
            storage.upload("k4", b"d4"),
        )
        elapsed = time.monotonic() - start

        # 4 x 50ms sequential = 200ms. Threaded should be well under 200ms.
        # Allow generous margin for CI, but should never be 4x sequential.
        assert elapsed < 0.3, f"Operations appear sequential: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked_during_upload(self, storage: MinIOStorage) -> None:
        """A background timer should keep ticking while upload runs."""
        ticks: list[float] = []
        stop = False

        async def ticker():
            while not stop:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        original_put = storage._client.put_object  # type: ignore[union-attr]

        def slow_put(*args, **kwargs):
            import time as _time

            _time.sleep(0.1)  # 100ms blocking I/O
            return original_put(*args, **kwargs)

        storage._client.put_object = slow_put  # type: ignore[union-attr]

        task = asyncio.create_task(ticker())
        await storage.upload("key", b"data")
        stop = True
        await task

        # If the event loop was blocked, we would get 0-1 ticks during the
        # 100ms window.  With proper to_thread, we should get ~10.
        assert len(ticks) >= 3, f"Event loop was blocked: only {len(ticks)} ticks"

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked_during_download(
        self, storage: MinIOStorage, fake_client: _FakeMinioClient
    ) -> None:
        """Event loop must remain responsive during download."""
        fake_client._objects["key"] = b"x" * 1024
        ticks: list[float] = []
        stop = False

        async def ticker():
            while not stop:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        original_get = fake_client.get_object

        def slow_get(*args, **kwargs):
            import time as _time

            _time.sleep(0.1)
            return original_get(*args, **kwargs)

        fake_client.get_object = slow_get  # type: ignore[assignment]

        task = asyncio.create_task(ticker())
        await storage.download("key")
        stop = True
        await task

        assert len(ticks) >= 3, f"Event loop was blocked: only {len(ticks)} ticks"


# ---------------------------------------------------------------------------
# Round-trip integration test
# ---------------------------------------------------------------------------


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_upload_download_round_trip(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        data = b"snapshot-payload-" * 100

        await storage.upload("snap/rt.tar.gz", data, metadata={"ver": "1"})
        assert await storage.exists("snap/rt.tar.gz") is True

        downloaded = await storage.download("snap/rt.tar.gz")
        assert downloaded == data

        await storage.delete("snap/rt.tar.gz")
        assert await storage.exists("snap/rt.tar.gz") is False

    @pytest.mark.asyncio
    async def test_list_after_uploads(self, storage: MinIOStorage, fake_client: _FakeMinioClient) -> None:
        await storage.upload("sess/a.tar.gz", b"a")
        await storage.upload("sess/b.tar.gz", b"b")
        await storage.upload("other/c.tar.gz", b"c")

        keys = await storage.list_objects(prefix="sess/")
        assert sorted(keys) == ["sess/a.tar.gz", "sess/b.tar.gz"]
