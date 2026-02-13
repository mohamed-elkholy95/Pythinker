"""Tests for AnthropicLLM multi-key support with cache-aware failover."""

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.external.key_pool import RotationStrategy

# Skip all tests if anthropic package not installed
pytest.importorskip("anthropic")


@pytest.fixture
async def redis_client():
    """Mock Redis client for testing."""
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.setex = AsyncMock()
    mock_redis.set = AsyncMock()
    return mock_redis


class TestAnthropicMultiKey:
    """Test Anthropic LLM with APIKeyPool and cache-aware FAILOVER strategy."""

    async def test_anthropic_uses_failover_strategy(self, redis_client):
        """Anthropic should use FAILOVER strategy for cache preservation."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=redis_client,
        )

        assert llm._key_pool is not None
        assert len(llm._key_pool.keys) == 3
        assert llm._key_pool.strategy == RotationStrategy.FAILOVER  # Cache-aware!

    async def test_anthropic_preserves_cache_locality(self, redis_client):
        """FAILOVER should always return primary key for cache locality."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=redis_client,
        )

        # Request key 5 times - should always be key1 (FAILOVER preserves cache)
        for _ in range(5):
            key = await llm.get_api_key()
            assert key == "key1"  # Always primary for cache hits

    async def test_anthropic_respects_retry_limit(self, redis_client, mocker):
        """Test retry limit prevents infinite recursion."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=redis_client,
        )

        # Mock _get_client to return client that always raises rate limit
        async def mock_get_client():
            mock_client = mocker.MagicMock()

            async def mock_create(**kwargs):
                # Create mock response and request
                mock_request = mocker.MagicMock()
                mock_response = mocker.MagicMock()
                mock_response.request = mock_request

                import anthropic

                raise anthropic.RateLimitError("429 rate_limit_error", response=mock_response, body=None)

            mock_client.messages.create = mock_create
            return mock_client

        mocker.patch.object(llm, "_get_client", side_effect=mock_get_client)

        # Mock mark_exhausted to prevent actual Redis calls
        mocker.patch.object(llm._key_pool, "mark_exhausted")

        with pytest.raises(RuntimeError) as exc:
            await llm.ask([{"role": "user", "content": "test"}])

        assert "exhausted after" in str(exc.value)

    async def test_anthropic_works_without_redis(self):
        """Test in-memory mode without Redis."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="test-key-1",
            fallback_api_keys=["test-key-2"],
            redis_client=None,
        )

        key = await llm.get_api_key()
        assert key == "test-key-1"  # FAILOVER always returns primary
        assert llm._key_pool._redis is None

    async def test_anthropic_single_key(self, redis_client):
        """Test with single key (no fallbacks)."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="only-key",
            redis_client=redis_client,
        )

        assert len(llm._key_pool.keys) == 1
        assert llm._max_retries == 1

        key = await llm.get_api_key()
        assert key == "only-key"

    async def test_anthropic_filters_empty_keys(self, redis_client):
        """Test that empty/None fallback keys are filtered out."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="key1",
            fallback_api_keys=["key2", "", None, "  ", "key3"],  # type: ignore
            redis_client=redis_client,
        )

        # Should have 3 valid keys (key1, key2, key3)
        assert len(llm._key_pool.keys) == 3

    async def test_anthropic_parse_rate_limit_ttl(self):
        """Test parsing rate limit TTL from error message."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(api_key="test-key")

        # Test with retry after message
        error = Exception("Error: Please retry after 120 seconds")
        ttl = llm._parse_anthropic_rate_limit(error)
        assert ttl == 120

        # Test with no match (should return default 60s)
        error = Exception("Generic error message")
        ttl = llm._parse_anthropic_rate_limit(error)
        assert ttl == 60

    async def test_anthropic_rate_limit_rotation(self, redis_client, mocker):
        """Test key rotation on rate limit error."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="key1",
            fallback_api_keys=["key2"],
            redis_client=redis_client,
        )

        # Mock _get_client to return clients that fail first, then succeed
        call_count = 0

        async def mock_get_client():
            nonlocal call_count
            call_count += 1

            mock_client = mocker.MagicMock()

            if call_count == 1:
                # First call: client raises rate limit error

                async def mock_create_fail(**kwargs):
                    import anthropic

                    mock_request = mocker.MagicMock()
                    mock_response = mocker.MagicMock()
                    mock_response.request = mock_request
                    raise anthropic.RateLimitError("429 rate_limit_error", response=mock_response, body=None)

                mock_client.messages.create = mock_create_fail
            else:
                # Second call: client succeeds
                mock_response = mocker.MagicMock()
                mock_response.content = [mocker.MagicMock(type="text", text="Hello")]
                mock_response.usage = mocker.MagicMock(
                    input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0
                )
                mock_response.stop_reason = "end_turn"

                async def mock_create_success(**kwargs):
                    return mock_response

                mock_client.messages.create = mock_create_success

            return mock_client

        mocker.patch.object(llm, "_get_client", side_effect=mock_get_client)

        # Mock mark_exhausted
        mark_exhausted_mock = mocker.patch.object(llm._key_pool, "mark_exhausted")

        # Should rotate to key2 after key1 exhausted
        result = await llm.ask([{"role": "user", "content": "test"}])

        assert result is not None
        assert call_count == 2  # Two attempts
        mark_exhausted_mock.assert_called_once()  # key1 marked exhausted

    async def test_anthropic_auth_error_rotation(self, redis_client, mocker):
        """Test key rotation on authentication error."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="invalid-key",
            fallback_api_keys=["valid-key"],
            redis_client=redis_client,
        )

        # Mock _get_client to return clients that fail first, then succeed
        call_count = 0

        async def mock_get_client():
            nonlocal call_count
            call_count += 1

            mock_client = mocker.MagicMock()

            if call_count == 1:
                # First call: client raises auth error

                async def mock_create_fail(**kwargs):
                    import anthropic

                    mock_request = mocker.MagicMock()
                    mock_response = mocker.MagicMock()
                    mock_response.request = mock_request
                    raise anthropic.AuthenticationError("401 invalid_api_key", response=mock_response, body=None)

                mock_client.messages.create = mock_create_fail
            else:
                # Second call: client succeeds
                mock_response = mocker.MagicMock()
                mock_response.content = [mocker.MagicMock(type="text", text="Hello")]
                mock_response.usage = mocker.MagicMock(
                    input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0
                )
                mock_response.stop_reason = "end_turn"

                async def mock_create_success(**kwargs):
                    return mock_response

                mock_client.messages.create = mock_create_success

            return mock_client

        mocker.patch.object(llm, "_get_client", side_effect=mock_get_client)

        # Mock mark_invalid
        mark_invalid_mock = mocker.patch.object(llm._key_pool, "mark_invalid")

        # Should rotate to valid-key after invalid-key rejected
        result = await llm.ask([{"role": "user", "content": "test"}])

        assert result is not None
        assert call_count == 2  # Two attempts
        mark_invalid_mock.assert_called_once()  # invalid-key marked invalid

    async def test_anthropic_stream_rate_limit_rotation(self, redis_client, mocker):
        """Test key rotation on rate limit during streaming."""
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(
            api_key="key1",
            fallback_api_keys=["key2"],
            redis_client=redis_client,
        )

        # Mock _get_client to return streaming clients that fail first, then succeed
        call_count = 0

        async def mock_get_client():
            nonlocal call_count
            call_count += 1

            mock_client = mocker.MagicMock()

            if call_count == 1:
                # First call: stream raises rate limit

                class MockStreamFail:
                    async def __aenter__(self):
                        import anthropic

                        mock_request = mocker.MagicMock()
                        mock_response = mocker.MagicMock()
                        mock_response.request = mock_request
                        raise anthropic.RateLimitError("429 rate_limit_error", response=mock_response, body=None)

                    async def __aexit__(self, *args):
                        pass

                mock_client.messages.stream.return_value = MockStreamFail()
            else:
                # Second call: stream succeeds

                class MockStreamSuccess:
                    def __init__(self):
                        # text_stream should be an async generator, not a method
                        self.text_stream = self._text_stream_generator()

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        pass

                    async def _text_stream_generator(self):
                        yield "Hello"
                        yield " "
                        yield "World"

                    def get_final_message(self):
                        msg = mocker.MagicMock()
                        msg.stop_reason = "end_turn"
                        return msg

                mock_client.messages.stream.return_value = MockStreamSuccess()

            return mock_client

        mocker.patch.object(llm, "_get_client", side_effect=mock_get_client)

        # Mock mark_exhausted
        mark_exhausted_mock = mocker.patch.object(llm._key_pool, "mark_exhausted")

        # Mock _record_stream_usage to prevent actual usage recording
        mocker.patch.object(llm, "_record_stream_usage")

        # Collect stream chunks
        chunks = [chunk async for chunk in llm.ask_stream([{"role": "user", "content": "test"}])]

        assert "".join(chunks) == "Hello World"
        assert call_count == 2  # Two attempts
        mark_exhausted_mock.assert_called_once()  # key1 marked exhausted
