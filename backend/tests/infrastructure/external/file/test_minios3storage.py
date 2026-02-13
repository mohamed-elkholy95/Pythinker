"""Regression tests for MinIO file upload metadata/header handling."""

import io
from types import SimpleNamespace

import pytest

from app.infrastructure.external.file import minios3storage
from app.infrastructure.external.file.minios3storage import MinIOFileStorage


class _FakePutResult:
    def __init__(self, etag: str = "test-etag") -> None:
        self.etag = etag


class _FakeMinIOClient:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        file_data: io.BytesIO,
        *,
        length: int,
        content_type: str,
        metadata: dict[str, str],
    ) -> _FakePutResult:
        self.put_calls.append(
            {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "length": length,
                "content_type": content_type,
                "metadata": dict(metadata),
                "body": file_data.read(),
            }
        )
        return _FakePutResult()


class _FakeMinIOStorage:
    def __init__(self, client: _FakeMinIOClient) -> None:
        self.client = client


@pytest.fixture
def storage_and_client(monkeypatch: pytest.MonkeyPatch) -> tuple[MinIOFileStorage, _FakeMinIOClient]:
    monkeypatch.setattr(
        minios3storage,
        "get_settings",
        lambda: SimpleNamespace(
            minio_bucket_name="pythinker",
            minio_presigned_expiry_seconds=3600,
        ),
    )

    fake_client = _FakeMinIOClient()
    storage = MinIOFileStorage(_FakeMinIOStorage(fake_client))
    return storage, fake_client


@pytest.mark.asyncio
async def test_upload_file_does_not_duplicate_content_type_header(
    storage_and_client: tuple[MinIOFileStorage, _FakeMinIOClient],
) -> None:
    storage, fake_client = storage_and_client

    await storage.upload_file(
        io.BytesIO(b"hello"),
        "report.md",
        "anonymous",
        content_type="text/markdown",
    )

    assert len(fake_client.put_calls) == 1
    call = fake_client.put_calls[0]
    metadata = {str(k).lower(): str(v) for k, v in dict(call["metadata"]).items()}

    assert call["content_type"] == "text/markdown"
    assert metadata["user-id"] == "anonymous"
    assert metadata["original-filename"] == "report.md"
    assert "content-type" not in metadata


@pytest.mark.asyncio
async def test_upload_file_filters_reserved_s3_metadata_keys(
    storage_and_client: tuple[MinIOFileStorage, _FakeMinIOClient],
) -> None:
    storage, fake_client = storage_and_client

    await storage.upload_file(
        io.BytesIO(b"hello"),
        "report.md",
        "anonymous",
        content_type="text/markdown",
        metadata={
            "content-type": "text/plain",
            "HOST": "minio:9000",
            "x-amz-meta-project": "alpha",
            "custom-key": 123,
        },
    )

    call = fake_client.put_calls[0]
    metadata = {str(k).lower(): str(v) for k, v in dict(call["metadata"]).items()}

    assert "content-type" not in metadata
    assert "host" not in metadata
    assert metadata["project"] == "alpha"
    assert metadata["custom-key"] == "123"
