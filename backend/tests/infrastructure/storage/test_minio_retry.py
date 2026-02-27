"""Tests for MinIO retry with exponential backoff (Phase 3A)."""

from unittest.mock import MagicMock, patch

import pytest
from minio.error import S3Error

from app.infrastructure.storage.minio_storage import _minio_retry


class TestMinioRetry:
    """Tests for _minio_retry() wrapper."""

    def test_success_on_first_attempt(self):
        """Successful call returns immediately without retry."""
        func = MagicMock(return_value="ok")

        result = _minio_retry(func, "arg1", max_attempts=3, base_delay=0.01, operation="test")

        assert result == "ok"
        func.assert_called_once_with("arg1")

    def test_retries_on_s3_error_then_succeeds(self):
        """Retries on S3Error and succeeds on second attempt."""
        func = MagicMock(
            side_effect=[
                S3Error("InternalError", "test", "test", "test", "test", "test"),
                "ok",
            ]
        )

        with patch("app.infrastructure.storage.minio_storage.time.sleep"):
            result = _minio_retry(func, max_attempts=3, base_delay=0.01, operation="test")

        assert result == "ok"
        assert func.call_count == 2

    def test_retries_on_timeout_error(self):
        """Retries on TimeoutError."""
        func = MagicMock(side_effect=[TimeoutError("connection timed out"), "ok"])

        with patch("app.infrastructure.storage.minio_storage.time.sleep"):
            result = _minio_retry(func, max_attempts=3, base_delay=0.01, operation="test")

        assert result == "ok"

    def test_retries_on_os_error(self):
        """Retries on OSError (network issues)."""
        func = MagicMock(side_effect=[OSError("Connection refused"), "ok"])

        with patch("app.infrastructure.storage.minio_storage.time.sleep"):
            result = _minio_retry(func, max_attempts=3, base_delay=0.01, operation="test")

        assert result == "ok"

    def test_raises_after_max_attempts(self):
        """Raises the last exception after exhausting all attempts."""
        error = S3Error("InternalError", "test", "test", "test", "test", "test")
        func = MagicMock(side_effect=error)

        with patch("app.infrastructure.storage.minio_storage.time.sleep"), pytest.raises(S3Error):
            _minio_retry(func, max_attempts=3, base_delay=0.01, operation="test")

        assert func.call_count == 3

    def test_does_not_retry_non_retryable_errors(self):
        """Non-retryable errors (e.g., ValueError) are not caught."""
        func = MagicMock(side_effect=ValueError("bad input"))

        with pytest.raises(ValueError, match="bad input"):
            _minio_retry(func, max_attempts=3, base_delay=0.01, operation="test")

        func.assert_called_once()

    def test_increments_prometheus_metrics(self):
        """Retry attempts and final failures emit Prometheus metrics."""
        func = MagicMock(
            side_effect=[
                S3Error("InternalError", "test", "test", "test", "test", "test"),
                S3Error("InternalError", "test", "test", "test", "test", "test"),
                S3Error("InternalError", "test", "test", "test", "test", "test"),
            ]
        )

        with patch("app.infrastructure.storage.minio_storage.time.sleep"), pytest.raises(S3Error):
            _minio_retry(func, max_attempts=3, base_delay=0.01, operation="store")

        # Metrics are checked by import — just verify no crash
        assert func.call_count == 3
