"""Tests for BraveSearchEngine multi-key support."""

from app.infrastructure.external.key_pool import RotationStrategy
from app.infrastructure.external.search.brave_search import BraveSearchEngine


class TestBraveMultiKey:
    """Test Brave search with APIKeyPool."""

    async def test_brave_uses_key_pool(self, mock_redis):
        """Brave should use APIKeyPool for multi-key rotation."""
        engine = BraveSearchEngine(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=mock_redis,
        )

        assert engine._key_pool is not None
        assert len(engine._key_pool.keys) == 3
        assert engine._key_pool.strategy == RotationStrategy.FAILOVER

    async def test_brave_respects_retry_limit(self, mocker):
        """Test retry limit prevents infinite recursion."""
        # Use None for Redis to simplify the test (in-memory mode)
        engine = BraveSearchEngine(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=None,
        )

        # Mock HTTP client to always return 429
        mock_response = mocker.MagicMock()
        mock_response.status_code = 429
        mock_client = mocker.AsyncMock()
        mock_client.get = mocker.AsyncMock(return_value=mock_response)
        mocker.patch.object(engine, "_get_client", return_value=mock_client)

        result = await engine.search("test query")

        assert result.success is False
        assert "exhausted after" in result.message
        assert mock_client.get.call_count == 3

    async def test_brave_works_without_redis(self):
        """Test in-memory mode without Redis."""
        engine = BraveSearchEngine(
            api_key="test-key-1",
            fallback_api_keys=["test-key-2"],
            redis_client=None,
        )

        key = await engine.api_key
        assert key == "test-key-1"
        assert engine._key_pool._redis is None

    async def test_brave_single_key_initialization(self):
        """Test initialization with only primary key (no fallbacks)."""
        engine = BraveSearchEngine(
            api_key="primary-key",
            redis_client=None,
        )

        assert len(engine._key_pool.keys) == 1
        assert engine._max_retries == 1
        key = await engine.api_key
        assert key == "primary-key"

    async def test_brave_filters_empty_keys(self):
        """Test that empty/None fallback keys are filtered out."""
        engine = BraveSearchEngine(
            api_key="key1",
            fallback_api_keys=["key2", None, "", "  ", "key3"],
            redis_client=None,
        )

        # Should only have 3 valid keys (key1, key2, key3)
        assert len(engine._key_pool.keys) == 3

    async def test_brave_key_rotation_on_401(self, mocker):
        """Test that 401 error triggers key rotation."""
        engine = BraveSearchEngine(
            api_key="key1",
            fallback_api_keys=["key2"],
            redis_client=None,
        )

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = mocker.MagicMock()
            if call_count == 1:
                # First call with key1: return 401
                mock_resp.status_code = 401
            else:
                # Second call with key2: return success
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "web": {"results": [{"title": "Test", "url": "http://test.com", "description": "Test result"}], "total_count": 1}
                }
            return mock_resp

        mock_client = mocker.AsyncMock()
        mock_client.get = mock_get
        mocker.patch.object(engine, "_get_client", return_value=mock_client)

        result = await engine.search("test query")

        # Should succeed with second key
        assert result.success is True
        assert call_count == 2

    async def test_brave_ttl_is_24_hours(self, mocker):
        """Test that Brave uses 24-hour TTL (86400 seconds)."""
        engine = BraveSearchEngine(
            api_key="key1",
            redis_client=None,
        )

        # Mock response to trigger rotation
        mock_response = mocker.MagicMock()
        mock_response.status_code = 429
        mock_client = mocker.AsyncMock()
        mock_client.get = mocker.AsyncMock(return_value=mock_response)
        mocker.patch.object(engine, "_get_client", return_value=mock_client)

        # Spy on mark_exhausted
        mark_exhausted_spy = mocker.spy(engine._key_pool, "mark_exhausted")

        await engine.search("test query")

        # Verify TTL is 86400 (24 hours)
        mark_exhausted_spy.assert_called_once()
        call_args = mark_exhausted_spy.call_args
        assert call_args.kwargs["ttl_seconds"] == 86400
