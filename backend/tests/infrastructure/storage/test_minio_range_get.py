"""Tests for MinIO range GET (Phase 3C)."""

from unittest.mock import MagicMock

import pytest

from app.infrastructure.storage.minio_storage import MinIOStorage


class TestRangeGet:
    """Tests for MinIOStorage.get_object_range()."""

    @pytest.mark.asyncio
    async def test_range_get_returns_byte_slice(self):
        """Range GET returns only the requested byte range."""
        storage = MinIOStorage.__new__(MinIOStorage)
        storage._settings = MagicMock()
        storage._settings.minio_retry_max_attempts = 1
        storage._settings.minio_retry_base_delay = 0.01
        storage._client = MagicMock()

        mock_response = MagicMock()
        mock_response.read.return_value = b"partial data"
        mock_response.close = MagicMock()
        mock_response.release_conn = MagicMock()
        storage._client.get_object.return_value = mock_response

        result = await storage.get_object_range("test-bucket", "key.bin", offset=100, length=50)

        assert result == b"partial data"
        storage._client.get_object.assert_called_once_with("test-bucket", "key.bin", offset=100, length=50)
