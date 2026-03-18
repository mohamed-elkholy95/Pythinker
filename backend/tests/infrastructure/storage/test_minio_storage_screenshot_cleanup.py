"""Tests for precise MinIO screenshot object deletion (record-level cleanup)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.infrastructure.storage.minio_storage import MinIOStorage


@pytest.fixture
def storage() -> MinIOStorage:
    """Create a MinIOStorage with a mock client and settings."""
    s = MinIOStorage.__new__(MinIOStorage)
    s._client = MagicMock()
    s._settings = SimpleNamespace(
        minio_screenshots_bucket="screenshots",
        minio_thumbnails_bucket="thumbnails",
    )
    return s


class TestDeleteScreenshotObjects:
    """Tests for _delete_objects_by_key_sync (record-level key deletion)."""

    def test_deletes_exact_keys_in_correct_buckets(self, storage: MinIOStorage) -> None:
        """Full-size keys go to screenshots bucket, thumbnails go to thumbnails bucket."""
        storage._client.remove_objects.return_value = []

        count = storage._delete_objects_by_key_sync(
            object_keys=["s1/0001.jpg", "s1/0002.jpg"],
            thumbnail_keys=["s1/thumb_0001.webp"],
        )

        assert count == 3
        assert storage._client.remove_objects.call_count == 2

        # First call: screenshots bucket
        first_call = storage._client.remove_objects.call_args_list[0]
        assert first_call[0][0] == "screenshots"
        delete_objects = first_call[0][1]
        assert len(delete_objects) == 2

        # Second call: thumbnails bucket
        second_call = storage._client.remove_objects.call_args_list[1]
        assert second_call[0][0] == "thumbnails"
        delete_objects = second_call[0][1]
        assert len(delete_objects) == 1

    def test_skips_empty_keys(self, storage: MinIOStorage) -> None:
        """Empty or None keys are filtered out before deletion."""
        storage._client.remove_objects.return_value = []

        count = storage._delete_objects_by_key_sync(
            object_keys=["s1/0001.jpg", "", ""],
            thumbnail_keys=["", ""],
        )

        # Only 1 valid key
        assert count == 1
        # Only screenshots bucket called (no valid thumbnail keys)
        storage._client.remove_objects.assert_called_once()

    def test_deduplicates_keys(self, storage: MinIOStorage) -> None:
        """Duplicate keys are deduplicated before deletion."""
        storage._client.remove_objects.return_value = []

        count = storage._delete_objects_by_key_sync(
            object_keys=["s1/0001.jpg", "s1/0001.jpg", "s1/0001.jpg"],
            thumbnail_keys=["s1/thumb.webp", "s1/thumb.webp"],
        )

        # 1 unique screenshot + 1 unique thumbnail
        assert count == 2
        first_call = storage._client.remove_objects.call_args_list[0]
        delete_objects = first_call[0][1]
        assert len(delete_objects) == 1  # deduplicated

    def test_empty_lists_noop(self, storage: MinIOStorage) -> None:
        """Empty key lists result in no MinIO calls."""
        count = storage._delete_objects_by_key_sync([], [])

        assert count == 0
        storage._client.remove_objects.assert_not_called()

    def test_idempotent_on_already_gone(self, storage: MinIOStorage) -> None:
        """Already-deleted objects don't cause errors (MinIO remove_objects is idempotent)."""
        storage._client.remove_objects.return_value = []

        count = storage._delete_objects_by_key_sync(
            object_keys=["nonexistent/0001.jpg"],
            thumbnail_keys=[],
        )

        assert count == 1
